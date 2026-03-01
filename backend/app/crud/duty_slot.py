from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.base import CRUDBase
from app.models.duty_slot import DutySlot
from app.schemas.duty_slot import DutySlotCreate, DutySlotUpdate

DutySlotSortField = Literal["title", "date", "start_time", "category", "created_at"]


class CRUDDutySlot(CRUDBase[DutySlot, DutySlotCreate, DutySlotUpdate]):
    async def get_multi_filtered(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        event_id: str | None = None,
        category: str | None = None,
        search: str | None = None,
        sort_by: DutySlotSortField = "date",
        sort_dir: Literal["asc", "desc"] = "asc",
    ) -> list[DutySlot]:
        query = select(DutySlot)
        if event_id:
            query = query.where(col(DutySlot.event_id) == event_id)
        if category:
            query = query.where(col(DutySlot.category) == category)
        if search:
            query = query.where(
                col(DutySlot.title).ilike(f"%{search}%")
                | col(DutySlot.description).ilike(f"%{search}%")
            )
        order_col = getattr(DutySlot, sort_by)
        query = query.order_by(col(order_col).asc() if sort_dir == "asc" else col(order_col).desc())
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_count_filtered(
        self,
        db: AsyncSession,
        *,
        event_id: str | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> int:
        query = select(func.count()).select_from(DutySlot)
        if event_id:
            query = query.where(col(DutySlot.event_id) == event_id)
        if category:
            query = query.where(col(DutySlot.category) == category)
        if search:
            query = query.where(
                col(DutySlot.title).ilike(f"%{search}%")
                | col(DutySlot.description).ilike(f"%{search}%")
            )
        result = await db.execute(query)
        return result.scalar_one()


duty_slot = CRUDDutySlot(DutySlot)
