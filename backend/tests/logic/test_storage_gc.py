"""The deletion queue: the triggers that fill it and the cleanup that drains it."""

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.storage import PostgresStorage, S3Storage, gc_wake_event
from app.crud.user_avatar import user_avatar as crud_avatar
from app.logic import storage_gc
from app.models.stored_object import StorageDeletion, StoredObject
from app.models.user import User
from app.models.user_avatar import UserAvatar
from tests.fixtures.storage import SessionsStub, storage_in_use, stored_bytes


async def _queued(db: AsyncSession) -> list[str]:
    return list((await db.execute(select(col(StorageDeletion.key)))).scalars())


async def _in_postgres(db: AsyncSession, key: str) -> bool:
    row = await db.execute(select(StoredObject).where(col(StoredObject.key) == key))
    return row.first() is not None


async def _avatar(db: AsyncSession, user: User) -> UserAvatar:
    return await crud_avatar.upsert(
        db, user_id=user.id, data=b"face", content_type="image/webp", etag="e" * 64
    )


class TestTriggers:
    async def test_deleting_a_row_queues_its_file(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Test a deleted row's key is queued and its Postgres bytes go at once."""
        avatar = await _avatar(db_session, test_user)
        key = avatar.storage_key

        await crud_avatar.delete_by_user(db_session, user_id=test_user.id)

        assert await _queued(db_session) == [key]
        assert not await _in_postgres(db_session, key)

    async def test_replacing_the_key_queues_the_old_file(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Test an upload over an existing avatar queues only the old file."""
        old_key = (await _avatar(db_session, test_user)).storage_key
        new_key = (await _avatar(db_session, test_user)).storage_key

        assert await _queued(db_session) == [old_key]
        assert await stored_bytes(db_session, new_key) == b"face"

    async def test_other_updates_queue_nothing(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Test changing another column leaves the file alone."""
        await _avatar(db_session, test_user)
        await db_session.execute(
            update(UserAvatar)
            .where(col(UserAvatar.user_id) == test_user.id)
            .values(etag="f" * 64)
        )
        assert await _queued(db_session) == []

    async def test_a_cascade_queues_the_file(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Test deleting the user (ON DELETE CASCADE) still queues the avatar."""
        key = (await _avatar(db_session, test_user)).storage_key

        await db_session.execute(delete(User).where(col(User.id) == test_user.id))

        assert await _queued(db_session) == [key]


class TestDrain:
    async def test_drain_deletes_objects_and_queue_rows(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test drain deletes every queued object and empties the queue."""
        keys = [f"avatars/{uuid.uuid4().hex}" for _ in range(3)]
        for key in keys:
            await moto_storage.put(db_session, key, b"x", "image/webp")
            db_session.add(StorageDeletion(key=key))
        # The same key queued twice (a replace, then a delete) is fine.
        db_session.add(StorageDeletion(key=keys[0]))
        await db_session.flush()

        with storage_in_use(moto_storage):
            assert await storage_gc.drain(db_session) == 4

        for key in keys:
            assert await moto_storage.get(db_session, key) is None
        assert await _queued(db_session) == []

    async def test_drain_of_an_empty_queue(self, db_session: AsyncSession) -> None:
        """Test drain with nothing queued does nothing."""
        assert await storage_gc.drain(db_session) == 0

    async def test_drain_all_works_in_batches(self, db_session: AsyncSession) -> None:
        """Test drain_all keeps going until a batch comes back short."""
        for _ in range(5):
            db_session.add(StorageDeletion(key=f"avatars/{uuid.uuid4().hex}"))
        await db_session.flush()

        with (
            patch.object(storage_gc, "async_session", SessionsStub(db_session)),
            patch.object(storage_gc, "_BATCH", 2),
            patch.object(storage_gc, "get_storage", return_value=PostgresStorage()),
        ):
            assert await storage_gc.drain_all() == 5
        assert await _queued(db_session) == []


class TestLoop:
    async def test_wakes_drains_and_survives_errors(self) -> None:
        """Test the loop drains when woken and keeps running after a failure."""
        calls: list[int] = []
        second_run = asyncio.Event()

        async def fake_drain_all() -> int:
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("bucket unreachable")
            second_run.set()
            return 3

        wake = gc_wake_event()
        with patch.object(
            storage_gc, "drain_all", AsyncMock(side_effect=fake_drain_all)
        ):
            task = asyncio.create_task(storage_gc.run_storage_gc())
            try:
                wake.set()
                await asyncio.sleep(0.05)
                wake.set()
                await asyncio.wait_for(second_run.wait(), timeout=2)
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        assert len(calls) == 2

    async def test_runs_on_the_interval_without_a_wake(self) -> None:
        """Test the loop drains after STORAGE_GC_INTERVAL_SECONDS on its own."""
        ran = asyncio.Event()

        async def fake_drain_all() -> int:
            ran.set()
            return 0

        gc_wake_event().clear()
        with (
            patch.object(
                storage_gc, "drain_all", AsyncMock(side_effect=fake_drain_all)
            ),
            patch.object(storage_gc.settings, "STORAGE_GC_INTERVAL_SECONDS", 0.01),
        ):
            task = asyncio.create_task(storage_gc.run_storage_gc())
            try:
                await asyncio.wait_for(ran.wait(), timeout=2)
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
