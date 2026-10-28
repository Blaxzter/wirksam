"""The two storage backends, the switch between them and the commit hook."""

import datetime as dt
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core import storage as storage_module
from app.core.config import Settings
from app.core.storage import (
    PostgresStorage,
    S3Storage,
    Storage,
    drain_after_commit,
    gc_wake_event,
    get_storage,
    make_s3_client,
    new_key,
    use_storage,
)
from app.models.stored_object import StoredObject


@pytest.fixture(params=["postgres", "s3"])
def backend(request: pytest.FixtureRequest, moto_storage: S3Storage) -> Storage:
    return PostgresStorage() if request.param == "postgres" else moto_storage


async def _legacy_row(db: AsyncSession, key: str, data: bytes) -> None:
    """A file written before the switch to S3: only in ``stored_objects``."""
    await PostgresStorage().put(db, key, data, "image/webp")


class TestBothBackends:
    async def test_put_get_copy_delete(
        self, db_session: AsyncSession, backend: Storage
    ) -> None:
        """Test a file can be written, read, copied and deleted."""
        key, copy = new_key("avatars"), new_key("avatars")
        await backend.put(db_session, key, b"bytes", "image/webp")

        assert await backend.get(db_session, key) == b"bytes"
        assert await backend.copy(db_session, key, copy) is True
        assert await backend.get(db_session, copy) == b"bytes"

        await backend.delete(db_session, [key])
        assert await backend.get(db_session, key) is None
        assert await backend.get(db_session, copy) == b"bytes"

    async def test_missing_keys(
        self, db_session: AsyncSession, backend: Storage
    ) -> None:
        """Test a missing key reads as None, copies as False and deletes quietly."""
        missing = new_key("team-documents")
        assert await backend.get(db_session, missing) is None
        assert await backend.copy(db_session, missing, new_key("avatars")) is False
        await backend.delete(db_session, [missing])
        await backend.delete(db_session, [])

    async def test_open_knows_the_size(
        self, db_session: AsyncSession, backend: Storage
    ) -> None:
        """Test an opened file reports its size and yields its bytes."""
        key = new_key("team-documents")
        await backend.put(db_session, key, b"%PDF-1.7", "application/pdf")

        opened = await backend.open(db_session, key)

        assert opened is not None
        assert opened.size == len(b"%PDF-1.7")
        assert b"".join([c async for c in opened.chunks]) == b"%PDF-1.7"
        assert await backend.open(db_session, new_key("avatars")) is None


class TestS3Storage:
    async def test_open_streams_in_pieces(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test a large object is passed on in chunks, not read whole."""
        key = new_key("venue-plans")
        data = bytes(range(256)) * 1024  # 256 KiB
        await moto_storage.put(db_session, key, data, "image/webp")

        opened = await moto_storage.open(db_session, key)

        assert opened is not None
        chunks = [c async for c in opened.chunks]
        assert len(chunks) > 1
        assert b"".join(chunks) == data

    async def test_reads_files_not_yet_moved_from_postgres(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test a file still in stored_objects is served from there."""
        key = new_key("venue-plans")
        await _legacy_row(db_session, key, b"old")

        assert await moto_storage.get(db_session, key) == b"old"

    async def test_copy_of_a_legacy_file_lands_in_the_bucket(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test copying a file still in Postgres writes the copy to the bucket."""
        key, copy = new_key("venue-plans"), new_key("venue-templates")
        await _legacy_row(db_session, key, b"old")

        assert await moto_storage.copy(db_session, key, copy) is True
        assert await PostgresStorage().get(db_session, copy) is None
        assert await moto_storage.get(db_session, copy) == b"old"

    async def test_delete_removes_a_legacy_file_too(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test deleting a key also deletes its stored_objects row."""
        key = new_key("avatars")
        await _legacy_row(db_session, key, b"old")

        await moto_storage.delete(db_session, [key])

        rows = await db_session.execute(
            select(StoredObject).where(col(StoredObject.key) == key)
        )
        assert rows.first() is None

    async def test_failed_delete_raises(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test an error from DeleteObjects raises so the keys stay queued."""
        with (
            patch.object(
                moto_storage.client,
                "delete_objects",
                return_value={"Errors": [{"Key": "x", "Code": "AccessDenied"}]},
            ),
            pytest.raises(RuntimeError, match="1 keys"),
        ):
            await moto_storage.delete(db_session, ["x"])

    async def test_copy_reraises_other_errors(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test a copy error other than a missing key is not swallowed."""
        error = moto_storage.client.exceptions.ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "no"}}, "CopyObject"
        )
        with (
            patch.object(moto_storage.client, "copy_object", side_effect=error),
            pytest.raises(moto_storage.client.exceptions.ClientError),
        ):
            await moto_storage.copy(db_session, "a", "b")

    async def test_list_keys_by_age(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test list_keys returns only objects written before the cutoff."""
        key = new_key("avatars")
        await moto_storage.put(db_session, key, b"x", "image/webp")
        now = dt.datetime.now(dt.UTC)

        assert key in await moto_storage.list_keys(
            older_than=now + dt.timedelta(minutes=5)
        )
        assert key not in await moto_storage.list_keys(
            older_than=now - dt.timedelta(minutes=5)
        )


class TestConfiguration:
    def test_postgres_is_the_default(self) -> None:
        """Test the configured backend without S3 settings is Postgres."""
        storage_module._configured.cache_clear()  # pyright: ignore[reportPrivateUsage]
        try:
            with patch.object(storage_module.settings, "STORAGE_BACKEND", "postgres"):
                assert isinstance(
                    storage_module._configured(),  # pyright: ignore[reportPrivateUsage]
                    PostgresStorage,
                )
        finally:
            storage_module._configured.cache_clear()  # pyright: ignore[reportPrivateUsage]

    def test_s3_backend_from_settings(self) -> None:
        """Test STORAGE_BACKEND=s3 builds an S3Storage on the configured bucket."""
        storage_module._configured.cache_clear()  # pyright: ignore[reportPrivateUsage]
        try:
            with (
                patch.object(storage_module.settings, "STORAGE_BACKEND", "s3"),
                patch.object(storage_module.settings, "S3_BUCKET", "files"),
                patch.object(storage_module.settings, "S3_ENDPOINT_URL", None),
            ):
                configured = storage_module._configured()  # pyright: ignore[reportPrivateUsage]
            assert isinstance(configured, S3Storage)
            assert configured.bucket == "files"
            assert configured.signer is configured.client
        finally:
            storage_module._configured.cache_clear()  # pyright: ignore[reportPrivateUsage]

    def test_links_are_signed_for_the_public_endpoint(self) -> None:
        """Test S3_PUBLIC_ENDPOINT_URL gives links their own signing client."""
        storage_module._configured.cache_clear()  # pyright: ignore[reportPrivateUsage]
        try:
            with (
                patch.object(storage_module.settings, "STORAGE_BACKEND", "s3"),
                patch.object(storage_module.settings, "S3_BUCKET", "files"),
                patch.object(
                    storage_module.settings, "S3_ENDPOINT_URL", "http://garage:3900"
                ),
                patch.object(
                    storage_module.settings,
                    "S3_PUBLIC_ENDPOINT_URL",
                    "https://files.example.org",
                ),
            ):
                configured = storage_module._configured()  # pyright: ignore[reportPrivateUsage]
            assert isinstance(configured, S3Storage)
            assert configured.client.meta.endpoint_url == "http://garage:3900"
            assert configured.signer.meta.endpoint_url == "https://files.example.org"
        finally:
            storage_module._configured.cache_clear()  # pyright: ignore[reportPrivateUsage]

    def test_client_uses_path_style_and_the_endpoint(self) -> None:
        """Test the client addresses Garage-style endpoints by path."""
        with patch.object(
            storage_module.settings, "S3_ENDPOINT_URL", "http://garage:3900"
        ):
            client = make_s3_client()
        assert client.meta.endpoint_url == "http://garage:3900"
        # botocore's Config sets its options as attributes the stubs do not list.
        s3_config: object = getattr(client.meta.config, "s3")  # noqa: B009
        assert s3_config == {"addressing_style": "path"}

    def test_use_storage_overrides_and_resets(self) -> None:
        """Test use_storage swaps the backend and None restores it."""
        # The suite may itself run on an override (TEST_STORAGE_BACKEND=s3).
        previous = storage_module._override  # pyright: ignore[reportPrivateUsage]
        replacement = PostgresStorage()
        try:
            use_storage(replacement)
            assert get_storage() is replacement
            use_storage(None)
            assert get_storage() is storage_module._configured()  # pyright: ignore[reportPrivateUsage]
        finally:
            use_storage(previous)

    def test_s3_without_bucket_does_not_boot(self) -> None:
        """Test STORAGE_BACKEND=s3 without S3_BUCKET fails at startup."""
        with pytest.raises(ValidationError, match="S3_BUCKET"):
            Settings(STORAGE_BACKEND="s3", S3_BUCKET=None)  # type: ignore[call-arg]


class TestDrainAfterCommit:
    async def test_commit_wakes_the_cleanup(self, db_session: AsyncSession) -> None:
        """Test a commit after drain_after_commit sets the wake event."""
        wake = gc_wake_event()
        wake.clear()
        drain_after_commit(db_session)
        await db_session.commit()
        assert wake.is_set()
        wake.clear()

    async def test_commit_without_the_flag_does_not(
        self, db_session: AsyncSession
    ) -> None:
        """Test an ordinary commit leaves the cleanup asleep."""
        wake = gc_wake_event()
        wake.clear()
        await db_session.commit()
        assert not wake.is_set()

    def test_rollback_drops_the_flag(self) -> None:
        """Test a rolled-back transaction does not wake the cleanup later."""
        from sqlalchemy.orm import Session

        session = Session()
        session.info["storage_gc_wake"] = True
        storage_module._after_rollback(session)  # pyright: ignore[reportPrivateUsage]
        assert "storage_gc_wake" not in session.info

    def test_commit_outside_an_event_loop_is_ignored(self) -> None:
        """Test a sync commit (no running loop) does not try to wake anything."""
        from sqlalchemy.orm import Session

        session = Session()
        session.info["storage_gc_wake"] = True
        storage_module._after_commit(session)  # pyright: ignore[reportPrivateUsage]
        assert "storage_gc_wake" not in session.info
