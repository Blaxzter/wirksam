import datetime as dt
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col

from app.crud.base import CRUDBase
from app.models.booking import Booking
from app.models.duty_slot import DutySlot
from app.schemas.booking import BookingCreate, BookingUpdate


class CRUDBooking(CRUDBase[Booking, BookingCreate, BookingUpdate]):
    async def get_by_slot_and_user(
        self,
        db: AsyncSession,
        *,
        duty_slot_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Booking | None:
        query = select(Booking).where(
            col(Booking.duty_slot_id) == duty_slot_id,
            col(Booking.user_id) == user_id,
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_confirmed_count(
        self,
        db: AsyncSession,
        *,
        duty_slot_id: uuid.UUID,
    ) -> int:
        query = (
            select(func.count())
            .select_from(Booking)
            .where(
                col(Booking.duty_slot_id) == duty_slot_id,
                col(Booking.status) == "confirmed",
            )
        )
        result = await db.execute(query)
        return result.scalar_one()

    async def get_multi_by_user(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        status: str | None = None,
        with_slot: bool = False,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> list[Booking]:
        query = select(Booking).where(col(Booking.user_id) == user_id)
        if status:
            query = query.where(col(Booking.status) == status)
        if date_from or date_to:
            query = query.outerjoin(DutySlot, col(Booking.duty_slot_id) == col(DutySlot.id))
            if date_from:
                query = query.where(
                    or_(
                        col(DutySlot.date) >= date_from,
                        col(Booking.cancelled_slot_date) >= date_from,
                    )
                )
            if date_to:
                query = query.where(
                    or_(
                        col(DutySlot.date) <= date_to,
                        col(Booking.cancelled_slot_date) <= date_to,
                    )
                )
        if with_slot:
            query = query.options(
                selectinload(Booking.duty_slot).selectinload(DutySlot.event)  # type: ignore[arg-type]
            )
        query = query.order_by(col(Booking.created_at).desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def count_by_user(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        status: str | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> int:
        query = (
            select(func.count())
            .select_from(Booking)
            .where(col(Booking.user_id) == user_id)
        )
        if status:
            query = query.where(col(Booking.status) == status)
        if date_from or date_to:
            query = query.outerjoin(DutySlot, col(Booking.duty_slot_id) == col(DutySlot.id))
            if date_from:
                query = query.where(
                    or_(
                        col(DutySlot.date) >= date_from,
                        col(Booking.cancelled_slot_date) >= date_from,
                    )
                )
            if date_to:
                query = query.where(
                    or_(
                        col(DutySlot.date) <= date_to,
                        col(Booking.cancelled_slot_date) <= date_to,
                    )
                )
        result = await db.execute(query)
        return result.scalar_one()

    async def get_multi_by_slot(
        self,
        db: AsyncSession,
        *,
        duty_slot_id: uuid.UUID,
        status: str | None = None,
        with_user: bool = False,
    ) -> list[Booking]:
        query = select(Booking).where(col(Booking.duty_slot_id) == duty_slot_id)
        if status:
            query = query.where(col(Booking.status) == status)
        if with_user:
            query = query.options(selectinload(Booking.user))  # type: ignore[arg-type]
        result = await db.execute(query)
        return list(result.scalars().all())


    async def cancel_bookings_for_slots(
        self,
        db: AsyncSession,
        *,
        slot_ids: list[uuid.UUID],
        event_name: str | None = None,
        cancellation_reason: str | None = None,
    ) -> int:
        """Cancel all confirmed bookings for the given slot IDs.

        Stores snapshot info from the slot so cancelled bookings remain
        meaningful after the slot is deleted (duty_slot_id becomes NULL).
        Returns the number of bookings cancelled.
        """
        if not slot_ids:
            return 0

        # Load confirmed bookings with their slot info
        query = (
            select(Booking)
            .where(
                col(Booking.duty_slot_id).in_(slot_ids),
                col(Booking.status) == "confirmed",
            )
            .options(selectinload(Booking.duty_slot))  # type: ignore[arg-type]
        )
        result = await db.execute(query)
        bookings = list(result.scalars().all())

        for b in bookings:
            slot: DutySlot | None = b.duty_slot
            if slot is None:
                continue
            b.status = "cancelled"
            b.cancellation_reason = cancellation_reason
            b.cancelled_slot_title = slot.title
            b.cancelled_slot_date = slot.date
            b.cancelled_slot_start_time = slot.start_time
            b.cancelled_slot_end_time = slot.end_time
            b.cancelled_event_name = event_name
            db.add(b)

        if bookings:
            await db.flush()

        return len(bookings)

    async def count_confirmed_for_slots(
        self,
        db: AsyncSession,
        *,
        slot_ids: list[uuid.UUID],
    ) -> int:
        """Count confirmed bookings across multiple slots."""
        if not slot_ids:
            return 0
        query = (
            select(func.count())
            .select_from(Booking)
            .where(
                col(Booking.duty_slot_id).in_(slot_ids),
                col(Booking.status) == "confirmed",
            )
        )
        result = await db.execute(query)
        return result.scalar_one()


booking = CRUDBooking(Booking)
