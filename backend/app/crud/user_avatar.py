import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.storage import drain_after_commit, get_storage, new_key
from app.models.user_avatar import UserAvatar


class CRUDUserAvatar:
    async def get_by_user(
        self, db: AsyncSession, *, user_id: uuid.UUID
    ) -> UserAvatar | None:
        result = await db.execute(
            select(UserAvatar).where(col(UserAvatar.user_id) == user_id)
        )
        return result.scalars().first()

    async def upsert(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        data: bytes,
        content_type: str,
        etag: str,
    ) -> UserAvatar:
        """Store ``data`` as the user's avatar.

        Always under a new key: replacing an avatar queues the old file for
        deletion (a trigger on the table, see ``app.logic.storage_gc``).
        """
        storage_key = new_key("avatars")
        await get_storage().put(db, storage_key, data, content_type)
        existing = await self.get_by_user(db, user_id=user_id)
        if existing:
            existing.storage_key = storage_key
            drain_after_commit(db)
            existing.content_type = content_type
            existing.etag = etag
            db.add(existing)
            await db.flush()
            return existing
        avatar = UserAvatar(
            user_id=user_id,
            storage_key=storage_key,
            content_type=content_type,
            etag=etag,
        )
        db.add(avatar)
        await db.flush()
        return avatar

    async def delete_by_user(self, db: AsyncSession, *, user_id: uuid.UUID) -> bool:
        existing = await self.get_by_user(db, user_id=user_id)
        if not existing:
            return False
        await db.delete(existing)
        await db.flush()
        drain_after_commit(db)
        return True


user_avatar = CRUDUserAvatar()
