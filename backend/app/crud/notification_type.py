from collections.abc import Sequence

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.base import CRUDBase
from app.logic.notifications.registry import NotificationTypeDict
from app.models.notification import NotificationType


class _Empty(BaseModel):
    pass


class CRUDNotificationType(CRUDBase[NotificationType, _Empty, _Empty]):
    async def get_by_code(self, db: AsyncSession, code: str) -> NotificationType | None:
        query = select(NotificationType).where(col(NotificationType.code) == code)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_all_active(
        self,
        db: AsyncSession,
        *,
        include_admin_only: bool = False,
    ) -> Sequence[NotificationType]:
        query = select(NotificationType).where(col(NotificationType.is_active) == True)  # noqa: E712
        if not include_admin_only:
            query = query.where(col(NotificationType.is_admin_only) == False)  # noqa: E712
        query = query.order_by(col(NotificationType.category), col(NotificationType.code))
        result = await db.execute(query)
        return result.scalars().all()

    async def upsert_from_registry(
        self,
        db: AsyncSession,
        *,
        types: list[NotificationTypeDict],
    ) -> int:
        """Upsert notification types from the code-level registry.

        Returns the number of types upserted.
        """
        count = 0
        for type_data in types:
            existing = await self.get_by_code(db, type_data["code"])
            if existing:
                for key, value in type_data.items():
                    if key != "code":
                        setattr(existing, key, value)
                db.add(existing)
            else:
                db_obj = NotificationType(**type_data)
                db.add(db_obj)
            count += 1
        await db.flush()
        return count


notification_type = CRUDNotificationType(NotificationType)
