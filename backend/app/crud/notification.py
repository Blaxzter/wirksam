import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.base import CRUDBase
from app.models.notification import Notification


class _NotificationCreate(BaseModel):
    recipient_id: uuid.UUID
    notification_type_code: str
    title: str
    body: str
    data: dict[str, str | int | None] | None = None
    channels_sent: list[str] = []
    channels_failed: list[str] = []


class _NotificationUpdate(BaseModel):
    is_read: bool | None = None
    read_at: datetime | None = None
    channels_sent: list[str] | None = None
    channels_failed: list[str] | None = None


class CRUDNotification(CRUDBase[Notification, _NotificationCreate, _NotificationUpdate]):
    async def get_multi_by_recipient(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
        unread_only: bool = False,
    ) -> Sequence[Notification]:
        query = select(Notification).where(col(Notification.recipient_id) == user_id)
        if unread_only:
            query = query.where(col(Notification.is_read) == False)  # noqa: E712
        query = query.order_by(col(Notification.created_at).desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()

    async def count_by_recipient(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        unread_only: bool = False,
    ) -> int:
        query = (
            select(func.count())
            .select_from(Notification)
            .where(col(Notification.recipient_id) == user_id)
        )
        if unread_only:
            query = query.where(col(Notification.is_read) == False)  # noqa: E712
        result = await db.execute(query)
        return result.scalar_one()

    async def get_unread_count(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> int:
        return await self.count_by_recipient(db, user_id=user_id, unread_only=True)

    async def mark_as_read(
        self,
        db: AsyncSession,
        *,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Notification | None:
        query = select(Notification).where(
            col(Notification.id) == notification_id,
            col(Notification.recipient_id) == user_id,
        )
        result = await db.execute(query)
        notif = result.scalar_one_or_none()
        if notif and not notif.is_read:
            notif.is_read = True
            notif.read_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.add(notif)
            await db.flush()
            await db.refresh(notif)
        return notif

    async def mark_all_as_read(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> int:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        stmt = (
            update(Notification)
            .where(
                col(Notification.recipient_id) == user_id,
                col(Notification.is_read) == False,  # noqa: E712
            )
            .values(is_read=True, read_at=now)
        )
        result = await db.execute(stmt)
        await db.flush()
        return result.rowcount  # type: ignore[return-value]

    async def create_notification(
        self,
        db: AsyncSession,
        *,
        recipient_id: uuid.UUID,
        notification_type_code: str,
        title: str,
        body: str,
        data: dict[str, str | int | None] | None = None,
        channels_sent: list[str] | None = None,
        channels_failed: list[str] | None = None,
    ) -> Notification:
        notif = Notification(
            recipient_id=recipient_id,
            notification_type_code=notification_type_code,
            title=title,
            body=body,
            data=data,
            channels_sent=channels_sent or [],
            channels_failed=channels_failed or [],
        )
        db.add(notif)
        await db.flush()
        await db.refresh(notif)
        return notif


notification = CRUDNotification(Notification)
