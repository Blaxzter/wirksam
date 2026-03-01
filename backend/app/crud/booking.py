import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.base import CRUDBase
from app.models.booking import Booking
from app.schemas.booking import BookingCreate, BookingUpdate


class CRUDBooking(CRUDBase[Booking, BookingCreate, BookingUpdate]):
    async def get_by_slot_and_user(
        self, db: AsyncSession, *, duty_slot_id: uuid.UUID, user_id: uuid.UUID,
    ) -> Booking | None:
        query = select(Booking).where(
            col(Booking.duty_slot_id) == duty_slot_id, col(Booking.user_id) == user_id,
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_confirmed_count(
        self, db: AsyncSession, *, duty_slot_id: uuid.UUID,
    ) -> int:
        query = (
            select(func.count()).select_from(Booking)
            .where(col(Booking.duty_slot_id) == duty_slot_id, col(Booking.status) == "confirmed")
        )
        result = await db.execute(query)
        return result.scalar_one()

    async def get_multi_by_user(
        self, db: AsyncSession, *, user_id: uuid.UUID, skip: int = 0, limit: int = 100, status: str | None = None,
    ) -> list[Booking]:
        query = select(Booking).where(col(Booking.user_id) == user_id)
        if status:
            query = query.where(col(Booking.status) == status)
        query = query.order_by(col(Booking.created_at).desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def count_by_user(
        self, db: AsyncSession, *, user_id: uuid.UUID, status: str | None = None,
    ) -> int:
        query = select(func.count()).select_from(Booking).where(col(Booking.user_id) == user_id)
        if status:
            query = query.where(col(Booking.status) == status)
        result = await db.execute(query)
        return result.scalar_one()

    async def get_multi_by_slot(
        self, db: AsyncSession, *, duty_slot_id: uuid.UUID, status: str | None = None,
    ) -> list[Booking]:
        query = select(Booking).where(col(Booking.duty_slot_id) == duty_slot_id)
        if status:
            query = query.where(col(Booking.status) == status)
        result = await db.execute(query)
        return list(result.scalars().all())


booking = CRUDBooking(Booking)
