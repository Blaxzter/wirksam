import uuid
from collections.abc import Sequence

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.base import CRUDBase
from app.models.notification import PushSubscription
from app.schemas.notification import PushSubscriptionCreate


class _PushSubUpdate(BaseModel):
    pass


class CRUDPushSubscription(
    CRUDBase[PushSubscription, PushSubscriptionCreate, _PushSubUpdate]
):
    async def get_by_user(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> Sequence[PushSubscription]:
        query = select(PushSubscription).where(col(PushSubscription.user_id) == user_id)
        result = await db.execute(query)
        return result.scalars().all()

    async def get_by_endpoint(
        self,
        db: AsyncSession,
        *,
        endpoint: str,
    ) -> PushSubscription | None:
        query = select(PushSubscription).where(
            col(PushSubscription.endpoint) == endpoint
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def create_or_update(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        obj_in: PushSubscriptionCreate,
    ) -> PushSubscription:
        existing = await self.get_by_endpoint(db, endpoint=obj_in.endpoint)
        if existing:
            existing.user_id = user_id
            existing.p256dh_key = obj_in.p256dh_key
            existing.auth_key = obj_in.auth_key
            existing.user_agent = obj_in.user_agent
            db.add(existing)
            await db.flush()
            await db.refresh(existing)
            return existing

        sub = PushSubscription(
            user_id=user_id,
            endpoint=obj_in.endpoint,
            p256dh_key=obj_in.p256dh_key,
            auth_key=obj_in.auth_key,
            user_agent=obj_in.user_agent,
        )
        db.add(sub)
        await db.flush()
        await db.refresh(sub)
        return sub

    async def remove_by_endpoint(
        self,
        db: AsyncSession,
        *,
        endpoint: str,
    ) -> bool:
        existing = await self.get_by_endpoint(db, endpoint=endpoint)
        if existing:
            await db.delete(existing)
            await db.flush()
            return True
        return False


push_subscription = CRUDPushSubscription(PushSubscription)
