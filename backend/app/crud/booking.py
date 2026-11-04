import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col

from app.crud.base import CRUDBase
from app.logic.work_hours import shift_ends_at
from app.models.booking import Booking
from app.models.booking_reminder import BookingReminder
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingUpdate


@dataclass(frozen=True)
class CancelledBooking:
    """A booking that ended with its shift, for telling the person about it."""

    booking_id: uuid.UUID
    user_id: uuid.UUID
    shift_title: str
    shift_date: dt.date


class CRUDBooking(CRUDBase[Booking, BookingCreate, BookingUpdate]):
    async def get_by_shift_and_user(
        self,
        db: AsyncSession,
        *,
        shift_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Booking | None:
        query = select(Booking).where(
            col(Booking.shift_id) == shift_id,
            col(Booking.user_id) == user_id,
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_confirmed_count(
        self,
        db: AsyncSession,
        *,
        shift_id: uuid.UUID,
    ) -> int:
        query = (
            select(func.count())
            .select_from(Booking)
            .where(
                col(Booking.shift_id) == shift_id,
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
        with_shift: bool = False,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        event_id: uuid.UUID | None = None,
    ) -> list[Booking]:
        query = select(Booking).where(col(Booking.user_id) == user_id)
        if status:
            query = query.where(col(Booking.status) == status)
        if date_from or date_to:
            query = query.outerjoin(Shift, col(Booking.shift_id) == col(Shift.id))
            if date_from:
                query = query.where(
                    or_(
                        col(Shift.date) >= date_from,
                        col(Booking.cancelled_shift_date) >= date_from,
                    )
                )
            if date_to:
                query = query.where(
                    or_(
                        col(Shift.date) <= date_to,
                        col(Booking.cancelled_shift_date) <= date_to,
                    )
                )
        if event_id is not None:
            query = query.where(
                col(Booking.shift_id).in_(
                    select(col(Shift.id))
                    .join(Task, col(Shift.task_id) == col(Task.id))
                    .where(col(Task.event_id) == event_id)
                )
            )
        if with_shift:
            query = query.options(
                selectinload(Booking.shift)  # type: ignore[arg-type]
                .selectinload(Shift.task)  # type: ignore[arg-type]
                .selectinload(Task.event)  # type: ignore[arg-type]
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
        event_id: uuid.UUID | None = None,
    ) -> int:
        query = (
            select(func.count())
            .select_from(Booking)
            .where(col(Booking.user_id) == user_id)
        )
        if status:
            query = query.where(col(Booking.status) == status)
        if date_from or date_to:
            query = query.outerjoin(Shift, col(Booking.shift_id) == col(Shift.id))
            if date_from:
                query = query.where(
                    or_(
                        col(Shift.date) >= date_from,
                        col(Booking.cancelled_shift_date) >= date_from,
                    )
                )
            if date_to:
                query = query.where(
                    or_(
                        col(Shift.date) <= date_to,
                        col(Booking.cancelled_shift_date) <= date_to,
                    )
                )
        if event_id is not None:
            query = query.where(
                col(Booking.shift_id).in_(
                    select(col(Shift.id))
                    .join(Task, col(Shift.task_id) == col(Task.id))
                    .where(col(Task.event_id) == event_id)
                )
            )
        result = await db.execute(query)
        return result.scalar_one()

    async def get_multi_by_shift(
        self,
        db: AsyncSession,
        *,
        shift_id: uuid.UUID,
        status: str | None = None,
        with_user: bool = False,
    ) -> list[Booking]:
        query = select(Booking).where(col(Booking.shift_id) == shift_id)
        if status:
            query = query.where(col(Booking.status) == status)
        if with_user:
            query = query.options(selectinload(Booking.user))  # type: ignore[arg-type]
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_confirmed_by_task(
        self,
        db: AsyncSession,
        *,
        task_id: uuid.UUID,
    ) -> list[Booking]:
        """Get all confirmed bookings for every shift belonging to a task, with user data."""
        query = (
            select(Booking)
            .join(Shift, col(Booking.shift_id) == col(Shift.id))
            .where(col(Shift.task_id) == task_id)
            .where(col(Booking.status) == "confirmed")
            .options(selectinload(Booking.user))  # type: ignore[arg-type]
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def cancel_bookings_for_shifts(
        self,
        db: AsyncSession,
        *,
        slot_ids: list[uuid.UUID],
        task_name: str | None = None,
        cancellation_reason: str | None = None,
    ) -> list[CancelledBooking]:
        """Cancel all confirmed bookings for the given shift IDs.

        Stores snapshot info from the shift so cancelled bookings remain
        meaningful after the shift is deleted (shift_id becomes NULL).
        Returns what was cancelled, for ``dispatch_booking_cancelled_by_admin``.
        """
        if not slot_ids:
            return []

        # Load confirmed bookings with their shift info
        query = (
            select(Booking)
            .where(
                col(Booking.shift_id).in_(slot_ids),
                col(Booking.status) == "confirmed",
            )
            .options(selectinload(Booking.shift))  # type: ignore[arg-type]
        )
        result = await db.execute(query)
        bookings = list(result.scalars().all())

        cancelled: list[CancelledBooking] = []
        for b in bookings:
            shift: Shift | None = b.shift
            if shift is None:
                continue
            b.status = "cancelled"
            b.cancellation_reason = cancellation_reason
            b.cancelled_shift_title = shift.title
            b.cancelled_shift_date = shift.date
            b.cancelled_shift_start_time = shift.start_time
            b.cancelled_shift_end_time = shift.end_time
            b.cancelled_task_name = task_name
            db.add(b)
            cancelled.append(
                CancelledBooking(
                    booking_id=b.id,
                    user_id=b.user_id,
                    shift_title=shift.title,
                    shift_date=shift.date,
                )
            )

        if bookings:
            await db.flush()

        return cancelled

    async def cancel_unfinished_bookings_in_event(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        event_id: uuid.UUID,
        now: dt.datetime,
    ) -> int:
        """Cancel someone's confirmed bookings on the event's unfinished shifts.

        For a person who leaves (or is removed from) the event: they keep no
        place on future rotas and do not go on earning hours or vouchers.
        Bookings on shifts already over stay, because that work happened.
        ``now`` is the event wall clock; "over" is ``shift_ends_at``. The
        snapshot fields are written as in :meth:`cancel_bookings_for_shifts`,
        and pending reminders are cancelled with the booking. Returns how many
        bookings were cancelled.
        """
        result = await db.execute(
            select(Booking, Shift, col(Task.name))
            .join(Shift, col(Shift.id) == col(Booking.shift_id))
            .join(Task, col(Task.id) == col(Shift.task_id))
            .where(
                col(Booking.user_id) == user_id,
                col(Booking.status) == "confirmed",
                col(Task.event_id) == event_id,
                # Shifts that end the day before yesterday or earlier are over
                # whatever their times; the rest is decided below.
                col(Shift.date) >= now.date() - dt.timedelta(days=1),
            )
        )
        cancelled: list[uuid.UUID] = []
        for b, shift, task_name in result.all():
            if shift_ends_at(shift.date, shift.start_time, shift.end_time) <= now:
                continue
            b.status = "cancelled"
            b.cancelled_shift_title = shift.title
            b.cancelled_shift_date = shift.date
            b.cancelled_shift_start_time = shift.start_time
            b.cancelled_shift_end_time = shift.end_time
            b.cancelled_task_name = task_name
            db.add(b)
            cancelled.append(b.id)
        if cancelled:
            await db.execute(
                update(BookingReminder)
                .where(
                    col(BookingReminder.booking_id).in_(cancelled),
                    col(BookingReminder.status) == "pending",
                )
                .values(status="cancelled")
            )
            await db.flush()
        return len(cancelled)

    async def confirmed_shift_times(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        task_ids: list[uuid.UUID],
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[tuple[uuid.UUID, dt.date, dt.time | None, dt.time | None]]:
        """``(task_id, date, start, end)`` of someone's confirmed shifts.

        For "is this person on a shift of this task right now": the caller
        narrows the dates (``logic.vouchers.redeem_window_dates``) and decides
        with ``logic.vouchers.redeem_window``. Being on a shift is about the
        booking standing, not about whether it later counts as worked.
        """
        if not task_ids:
            return []
        result = await db.execute(
            select(
                col(Shift.task_id),
                col(Shift.date),
                col(Shift.start_time),
                col(Shift.end_time),
            )
            .join(Booking, col(Booking.shift_id) == col(Shift.id))
            .where(
                col(Booking.user_id) == user_id,
                col(Booking.status) == "confirmed",
                col(Shift.task_id).in_(task_ids),
                col(Shift.date) >= date_from,
                col(Shift.date) <= date_to,
            )
        )
        return [(t, d, s, e) for t, d, s, e in result.all()]

    async def confirmed_bookers(
        self,
        db: AsyncSession,
        *,
        slot_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[tuple[uuid.UUID, str | None]]]:
        """``{shift_id: [(user_id, name), ...]}`` of confirmed bookings,
        earliest booking first, for a page of shifts in one query.

        Shifts nobody has booked are missing from the result. Who may read
        the names is the caller's business (see ``GET /shifts/``).
        """
        if not slot_ids:
            return {}
        result = await db.execute(
            select(col(Booking.shift_id), col(User.id), col(User.name))
            .join(User, col(User.id) == col(Booking.user_id))
            .where(
                col(Booking.shift_id).in_(slot_ids),
                col(Booking.status) == "confirmed",
            )
            .order_by(col(Booking.created_at), col(Booking.id))
        )
        out: dict[uuid.UUID, list[tuple[uuid.UUID, str | None]]] = {}
        for shift_id, user_id, name in result.all():
            if shift_id is not None:  # matched by IN above; for the checker
                out.setdefault(shift_id, []).append((user_id, name))
        return out

    async def count_confirmed_for_shifts(
        self,
        db: AsyncSession,
        *,
        slot_ids: list[uuid.UUID],
    ) -> int:
        """Count confirmed bookings across multiple shifts."""
        if not slot_ids:
            return 0
        query = (
            select(func.count())
            .select_from(Booking)
            .where(
                col(Booking.shift_id).in_(slot_ids),
                col(Booking.status) == "confirmed",
            )
        )
        result = await db.execute(query)
        return result.scalar_one()


booking = CRUDBooking(Booking)
