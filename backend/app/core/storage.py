"""Where uploaded files live: Postgres or an S3-compatible bucket.

Every route and logic module that reads or writes the bytes of an upload goes
through ``get_storage()``; the rows that own a file (``user_avatars``,
``venue_plan_images``, ``venue_template_images``, ``event_team_documents``)
hold only its ``storage_key``. ``STORAGE_BACKEND`` picks the backend:

* ``PostgresStorage`` writes ``stored_objects`` rows through the request's own
  session, so a file and its owner row commit or roll back together.
* ``S3Storage`` talks to a bucket through boto3, in a worker thread. A key it
  cannot find there is looked up in ``stored_objects``: that is a file the
  copy script (``app.scripts.move_files_to_s3``) has not moved yet, so the
  switch can happen before the copy rather than after a downtime. It can also
  sign a short-lived link to an object (``link``), so a browser fetches the
  bytes from the bucket and not through the API.

Deleting is not done here by the callers: database triggers queue the key of
every file row that goes away, and ``app.logic.storage_gc`` drains the queue
with ``delete``. See ``docs/STORAGE.md``.

Keys are never reused. A replaced file gets a new key, so the old object can
be deleted on its own schedule without racing the new one.
"""

import asyncio
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Literal

import anyio.to_thread
import sqlalchemy as sa
from sqlalchemy import delete, event, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlmodel import col

from app.core.config import settings
from app.models.stored_object import StoredObject

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
    from mypy_boto3_s3.type_defs import GetObjectOutputTypeDef

FileKind = Literal["avatars", "venue-plans", "venue-templates", "team-documents"]

# DeleteObjects takes at most this many keys per call.
_S3_DELETE_BATCH = 1000
# A bucket object is passed on to the client in pieces of this size, so a
# multi-megabyte plan or document is never held in memory whole.
_S3_CHUNK = 64 * 1024


def new_key(kind: FileKind) -> str:
    """A fresh, unguessable key for one file, grouped by what it is."""
    return f"{kind}/{uuid.uuid4().hex}"


@dataclass(frozen=True)
class StoredFile:
    """An opened file: its size (None when unknown) and its bytes, in chunks."""

    size: int | None
    chunks: AsyncIterator[bytes]


async def _single(data: bytes) -> AsyncIterator[bytes]:
    yield data


def _whole(data: bytes) -> StoredFile:
    return StoredFile(len(data), _single(data))


class Storage(ABC):
    """Put, read, copy and delete files by key.

    ``db`` is the caller's session. The Postgres backend works inside it; the
    S3 backend only uses it to reach files not yet moved out of Postgres.
    """

    @abstractmethod
    async def put(
        self, db: AsyncSession, key: str, data: bytes, content_type: str
    ) -> None:
        """Store ``data`` under the new key ``key``."""

    @abstractmethod
    async def open(self, db: AsyncSession, key: str) -> StoredFile | None:
        """The file under ``key`` to stream out, or None when there is none.

        Whether it exists is settled here, before the first chunk, so a route
        can still answer 404 instead of a broken 200.
        """

    async def link(
        self, db: AsyncSession, key: str, *, expires_in: int, cache_control: str
    ) -> str | None:
        """A signed URL a browser can fetch ``key`` from for ``expires_in`` seconds.

        None when this store cannot hand one out and the file has to be
        streamed. The bucket answers with ``cache_control``. Whether the file
        exists is not checked; a link to a missing one gets the store's 404.
        """
        return None

    async def get(self, db: AsyncSession, key: str) -> bytes | None:
        """The bytes under ``key``, or None when there is no such file."""
        opened = await self.open(db, key)
        if opened is None:
            return None
        return b"".join([chunk async for chunk in opened.chunks])

    @abstractmethod
    async def copy(self, db: AsyncSession, source: str, target: str) -> bool:
        """Copy ``source`` to the new key ``target``. False when it is missing."""

    @abstractmethod
    async def delete(self, db: AsyncSession, keys: Sequence[str]) -> None:
        """Delete these keys. Keys that do not exist are not an error."""


class PostgresStorage(Storage):
    async def put(
        self, db: AsyncSession, key: str, data: bytes, content_type: str
    ) -> None:
        db.add(StoredObject(key=key, data=data, content_type=content_type))
        await db.flush()

    async def get(self, db: AsyncSession, key: str) -> bytes | None:
        result = await db.execute(
            select(col(StoredObject.data)).where(col(StoredObject.key) == key)
        )
        data = result.scalar_one_or_none()
        return bytes(data) if data is not None else None

    async def open(self, db: AsyncSession, key: str) -> StoredFile | None:
        # bytea arrives whole anyway; there is nothing to stream.
        data = await self.get(db, key)
        return _whole(data) if data is not None else None

    async def copy(self, db: AsyncSession, source: str, target: str) -> bool:
        # INSERT ... SELECT, so the bytes never pass through Python.
        result = await db.execute(
            insert(StoredObject).from_select(
                ["key", "data", "content_type", "created_at"],
                select(
                    sa.literal(target, sa.String(255)),
                    col(StoredObject.data),
                    col(StoredObject.content_type),
                    sa.func.timezone("UTC", sa.func.now()),
                ).where(col(StoredObject.key) == source),
            )
        )
        return bool(getattr(result, "rowcount", 0))

    async def delete(self, db: AsyncSession, keys: Sequence[str]) -> None:
        if keys:
            await db.execute(
                delete(StoredObject).where(col(StoredObject.key).in_(list(keys)))
            )


class S3Storage(Storage):
    """An S3-compatible bucket. It is private: a browser gets at an object
    only through a link the API signed after its access check, or through
    the API itself, which streams it in 64 KiB pieces.

    ``signer`` signs those links. It is a client for the endpoint as the
    browser sees it, which inside a Docker stack is not the one the backend
    talks to; signing is local, it never makes a request.
    """

    def __init__(
        self, client: "S3Client", bucket: str, *, signer: "S3Client | None" = None
    ) -> None:
        self.client = client
        self.bucket = bucket
        self.signer = signer or client
        # Files from before the switch, until the copy script has moved them.
        self.legacy = PostgresStorage()

    async def put(
        self, db: AsyncSession, key: str, data: bytes, content_type: str
    ) -> None:
        await anyio.to_thread.run_sync(
            lambda: self.client.put_object(
                Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
            )
        )

    async def open(self, db: AsyncSession, key: str) -> StoredFile | None:
        def start() -> "GetObjectOutputTypeDef | None":
            try:
                return self.client.get_object(Bucket=self.bucket, Key=key)
            except self.client.exceptions.NoSuchKey:
                return None

        response = await anyio.to_thread.run_sync(start)
        if response is None:
            return await self.legacy.open(db, key)
        body = response["Body"]

        async def chunks() -> AsyncIterator[bytes]:
            try:
                while chunk := await anyio.to_thread.run_sync(body.read, _S3_CHUNK):
                    yield chunk
            finally:
                # Also when the client hangs up halfway: hand the connection back.
                body.close()

        return StoredFile(response.get("ContentLength"), chunks())

    async def link(
        self, db: AsyncSession, key: str, *, expires_in: int, cache_control: str
    ) -> str | None:
        legacy = await db.execute(
            select(col(StoredObject.key)).where(col(StoredObject.key) == key)
        )
        if legacy.first() is not None:
            # Not moved yet: the bucket does not have it, so stream it instead.
            return None
        return self.signer.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseCacheControl": cache_control,
            },
            ExpiresIn=expires_in,
        )

    async def allow_browser_reads(self) -> None:
        """Let a page read a signed link with ``fetch``, not only ``<img>``.

        The origin is ``*`` because the browser sends ``Origin: null`` after
        following the API's redirect to another host, and every link is
        signed anyway: the rule grants nothing a link does not.
        """
        await anyio.to_thread.run_sync(
            lambda: self.client.put_bucket_cors(
                Bucket=self.bucket,
                CORSConfiguration={
                    "CORSRules": [
                        {
                            "AllowedOrigins": ["*"],
                            "AllowedMethods": ["GET", "HEAD"],
                            "MaxAgeSeconds": 3600,
                        }
                    ]
                },
            )
        )

    async def copy(self, db: AsyncSession, source: str, target: str) -> bool:
        def server_side() -> bool:
            try:
                self.client.copy_object(
                    Bucket=self.bucket,
                    Key=target,
                    CopySource={"Bucket": self.bucket, "Key": source},
                )
            except self.client.exceptions.ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
                    return False
                raise
            return True

        if await anyio.to_thread.run_sync(server_side):
            return True
        # Not in the bucket yet: copy the Postgres original into the bucket.
        row = (
            await db.execute(
                select(StoredObject).where(col(StoredObject.key) == source)
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        await self.put(db, target, bytes(row.data), row.content_type)
        return True

    async def delete(self, db: AsyncSession, keys: Sequence[str]) -> None:
        if not keys:
            return
        await self.legacy.delete(db, keys)

        def remove() -> None:
            for start in range(0, len(keys), _S3_DELETE_BATCH):
                batch = keys[start : start + _S3_DELETE_BATCH]
                response = self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
                )
                # A missing key is not reported; anything listed here is a
                # real failure, and raising keeps the keys queued for a retry.
                errors = response.get("Errors", [])
                if errors:
                    raise RuntimeError(f"S3 delete failed for {len(errors)} keys")

        await anyio.to_thread.run_sync(remove)

    async def list_keys(self, *, older_than: datetime) -> list[str]:
        """Every key in the bucket last written before ``older_than`` (aware)."""

        def scan() -> list[str]:
            keys: list[str] = []
            pages = self.client.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket
            )
            for page in pages:
                for obj in page.get("Contents", []):
                    key, modified = obj.get("Key"), obj.get("LastModified")
                    if (
                        key is not None
                        and modified is not None
                        and modified < older_than
                    ):
                        keys.append(key)
            return keys

        return await anyio.to_thread.run_sync(scan)


def make_s3_client(endpoint_url: str | None = None) -> "S3Client":
    """A client for ``endpoint_url``, by default ``S3_ENDPOINT_URL``."""
    import boto3
    from botocore.config import Config

    # boto3-stubs types only the s3 overload; the others are unknown to pyright.
    return boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "s3",
        endpoint_url=endpoint_url or settings.S3_ENDPOINT_URL,
        region_name=settings.S3_REGION,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        config=Config(
            signature_version="s3v4",
            # Garage and MinIO serve buckets under the path, not a subdomain.
            s3={"addressing_style": "path"},
            # boto3's default checksums on every request are newer than some
            # S3-compatible stores; send them only where S3 requires them.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


_override: Storage | None = None


@lru_cache(maxsize=1)
def _configured() -> Storage:
    if settings.STORAGE_BACKEND == "s3":
        assert settings.S3_BUCKET  # enforced by Settings
        client = make_s3_client()
        signer = (
            make_s3_client(settings.S3_PUBLIC_ENDPOINT_URL)
            if settings.S3_PUBLIC_ENDPOINT_URL
            else client
        )
        return S3Storage(client, settings.S3_BUCKET, signer=signer)
    return PostgresStorage()


def get_storage() -> Storage:
    """The storage backend this process uses."""
    return _override if _override is not None else _configured()


def use_storage(storage: Storage | None) -> None:
    """Swap the backend (tests); ``None`` goes back to the configured one."""
    global _override
    _override = storage


# ── Waking the cleanup ────────────────────────────────────────────────────────

_WAKE_FLAG = "storage_gc_wake"
# Set by a commit that queued deletions; ``app.logic.storage_gc`` waits on it.
# Created lazily so it binds to the running event loop, not the import-time one.
_wake: asyncio.Event | None = None


def gc_wake_event() -> asyncio.Event:
    global _wake
    if _wake is None:
        _wake = asyncio.Event()
    return _wake


def drain_after_commit(db: AsyncSession) -> None:
    """Have the deletion queue worked once ``db`` commits (nothing on rollback).

    For a deletion the caller knows about. Cascades are not announced and wait
    for the next scheduled run.
    """
    db.sync_session.info[_WAKE_FLAG] = True


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:  # pyright: ignore[reportUnusedFunction]
    if session.info.pop(_WAKE_FLAG, False):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        gc_wake_event().set()


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:  # pyright: ignore[reportUnusedFunction]
    session.info.pop(_WAKE_FLAG, None)
