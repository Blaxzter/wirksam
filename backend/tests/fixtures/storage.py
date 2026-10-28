"""The storage backend the suite runs against.

``TEST_STORAGE_BACKEND=s3`` runs every test with ``S3Storage`` on a moto
bucket, in process; unset (the default) uses ``PostgresStorage``, whatever
``STORAGE_BACKEND`` in .env says (.env.example picks the Garage container,
which the suite must not depend on). CI runs the suite both ways.
"""

import os
import uuid
from collections.abc import AsyncGenerator, Generator, Iterator
from contextlib import (
    AbstractAsyncContextManager,
    asynccontextmanager,
    contextmanager,
)
from typing import cast

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import storage as storage_module
from app.core.storage import (
    FileKind,
    PostgresStorage,
    S3Storage,
    Storage,
    get_storage,
    new_key,
    use_storage,
)

TEST_BUCKET = "wirksam-test"


def make_moto_storage(bucket: str = TEST_BUCKET) -> S3Storage:
    """An ``S3Storage`` on a fresh moto bucket; call inside ``mock_aws``."""
    import boto3

    client = boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "s3",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    client.create_bucket(Bucket=bucket)
    return S3Storage(client, bucket)


@pytest.fixture(scope="session", autouse=True)
def storage_backend() -> Iterator[Storage]:
    if os.environ.get("TEST_STORAGE_BACKEND") != "s3":
        storage = PostgresStorage()
        with storage_in_use(storage):
            yield storage
        return
    from moto import mock_aws

    with mock_aws():
        storage = make_moto_storage()
        use_storage(storage)
        try:
            yield storage
        finally:
            use_storage(None)


@pytest.fixture
def streamed() -> Iterator[None]:
    """Serve files through the API, whatever the suite runs on.

    For tests of the streamed response itself (its headers, a missing file):
    under ``TEST_STORAGE_BACKEND=s3`` the routes would answer with a redirect.
    """
    with storage_in_use(PostgresStorage()):
        yield


@pytest.fixture
def moto_storage(storage_backend: Storage) -> Iterator[S3Storage]:
    """An ``S3Storage`` on its own empty moto bucket, whatever the suite runs on.

    Under ``TEST_STORAGE_BACKEND=s3`` the session's mock is already active and
    a second ``mock_aws`` would reset it on exit, so this adds a bucket to it.
    """
    if isinstance(storage_backend, S3Storage):
        bucket = f"test-{uuid.uuid4().hex}"
        storage_backend.client.create_bucket(Bucket=bucket)
        yield S3Storage(storage_backend.client, bucket)
        return
    from moto import mock_aws

    with mock_aws():
        yield make_moto_storage()


async def stored_bytes(db: AsyncSession, key: str) -> bytes | None:
    """The bytes stored under ``key``, from whichever backend is in use."""
    return await get_storage().get(db, key)


async def fetch_file(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET a file endpoint, following a redirect to a signed bucket link.

    The link is fetched for real; moto checks it, as the bucket would.
    """
    r = await client.get(url)
    if r.status_code != 302:
        return r
    import requests

    followed = requests.get(r.headers["location"], timeout=10)
    return httpx.Response(
        followed.status_code,
        content=followed.content,
        headers=dict(followed.headers),
    )


async def drop_file(db: AsyncSession, key: str) -> None:
    """Delete a file behind its row's back, as a lost bucket object would be."""
    await get_storage().delete(db, [key])


async def put_file(
    db: AsyncSession, kind: FileKind, data: bytes, content_type: str = "image/webp"
) -> str:
    """Store ``data`` under a new key of ``kind`` and return the key."""
    key = new_key(kind)
    await get_storage().put(db, key, data, content_type)
    return key


class SessionsStub:
    """Stands in for ``app.core.db.async_session`` in code that opens its own
    sessions: each one is the test's ``db_session``, so its rollback still
    cleans up. ``begin()`` flushes on the way out instead of committing."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @asynccontextmanager
    async def _session(self, *, flush: bool) -> AsyncGenerator[AsyncSession]:
        yield self.db
        if flush:
            await self.db.flush()

    def __call__(self) -> AbstractAsyncContextManager[AsyncSession]:
        return self._session(flush=False)

    def begin(self) -> AbstractAsyncContextManager[AsyncSession]:
        return self._session(flush=True)

    def as_maker(self) -> "async_sessionmaker[AsyncSession]":
        return cast("async_sessionmaker[AsyncSession]", self)


@contextmanager
def storage_in_use(storage: Storage) -> Generator[None]:
    """Make ``storage`` the backend for a block, then restore the previous one."""
    previous = storage_module._override  # pyright: ignore[reportPrivateUsage]
    use_storage(storage)
    try:
        yield
    finally:
        use_storage(previous)
