import datetime as dt
import uuid
from collections.abc import Collection, Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.base import CRUDBase
from app.logic import clock
from app.models.booking import Booking
from app.models.booking_reminder import BookingReminder
from app.models.event import Event
from app.models.shift import Shift
from app.models.task import Task
from app.schemas.booking_reminder import (
    AllowedChannel,
    BookingReminderCreate,
    ReminderOffsetEntry,
)


def _fires_at(
    slot_start: dt.datetime, offset_minutes: int, zone: str | None
) -> tuple[dt.datetime, str]:
    """``(remind_at, status)``: when a reminder fires, and whether it still can.

    ``slot_start`` is on the wall clock of the shift's event, and ``remind_at``
    is in UTC, because that's what the poller compares it with. Compared
    directly, a reminder fires late by the zone's offset. ``zone`` ``None`` is
    the setting, for a task without an event.
    """
    remind_at = clock.wall_clock_to_utc(slot_start, zone) - dt.timedelta(
        minutes=offset_minutes
    )
    return remind_at, "pending" if remind_at > clock.utc_now() else "expired"


class CRUDBookingReminder(
    CRUDBase[BookingReminder, BookingReminderCreate, BookingReminderCreate]
):
    async def create_reminder(
        self,
        db: AsyncSession,
        *,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        shift_id: uuid.UUID,
        offset_minutes: int,
        slot_start: dt.datetime,
        zone: str | None = None,
        channels: Sequence[AllowedChannel] | None = None,
    ) -> BookingReminder:
        """Create a single reminder for a booking, in the shift's event's zone.

        One already in the past is still created, but expired at once.
        """
        remind_at, status = _fires_at(slot_start, offset_minutes, zone)

        reminder = BookingReminder(
            booking_id=booking_id,
            user_id=user_id,
            shift_id=shift_id,
            remind_at=remind_at,
            offset_minutes=offset_minutes,
            status=status,
            channels=list(channels) if channels else ["push"],
        )
        db.add(reminder)
        await db.flush()
        await db.refresh(reminder)
        return reminder

    async def replace_for_booking(
        self,
        db: AsyncSession,
        *,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        shift_id: uuid.UUID,
        entries: Sequence[ReminderOffsetEntry],
        slot_start: dt.datetime,
        zone: str | None,
    ) -> list[BookingReminder]:
        """Make ``entries`` the booking's reminders; returns the rows written.

        For a booking that may have had reminders before: one booked again
        after a cancel, a guest switching reminders off and on. Cancelling
        leaves its rows behind (:meth:`cancel_by_booking`), and a new row for
        the same offset would break ``uq_reminder_booking_offset``. So every
        row not sent yet is deleted first. A sent one stays, and its offset is
        skipped: a reminder that went out is never sent twice. ``entries=[]``
        only deletes. ``slot_start`` and ``zone`` as for :meth:`create_reminder`.
        """
        sent = await db.execute(
            select(col(BookingReminder.offset_minutes)).where(
                col(BookingReminder.booking_id) == booking_id,
                col(BookingReminder.status) == "sent",
            )
        )
        written_offsets = set(sent.scalars().all())
        await db.execute(
            delete(BookingReminder).where(
                col(BookingReminder.booking_id) == booking_id,
                col(BookingReminder.status) != "sent",
            )
        )
        reminders: list[BookingReminder] = []
        for entry in entries:
            if entry.offset_minutes in written_offsets:
                continue
            written_offsets.add(entry.offset_minutes)
            reminders.append(
                await self.create_reminder(
                    db,
                    booking_id=booking_id,
                    user_id=user_id,
                    shift_id=shift_id,
                    offset_minutes=entry.offset_minutes,
                    slot_start=slot_start,
                    zone=zone,
                    channels=entry.channels,
                )
            )
        return reminders

    async def reschedule(
        self,
        db: AsyncSession,
        *,
        shift_ids: Sequence[uuid.UUID] | None = None,
        task_id: uuid.UUID | None = None,
        event_id: uuid.UUID | None = None,
    ) -> int:
        """Work out again when the reminders on these shifts fire. Returns how
        many changed. Call it whenever the moment a shift starts has changed:
        its date or start, or the zone of its event.

        Reminders of confirmed bookings not sent yet. Sent ones stay as they
        are. An expired one never reached anybody, so it comes back if its new
        moment is still ahead (a shift moved by mistake and moved back keeps its
        reminders); a pending one whose new moment has gone expires, as one
        created in the past does. Cancelled ones stay cancelled.

        Reads the shift's columns rather than the entity, so a bulk update
        earlier in the transaction is seen whatever the identity map holds.
        """
        query = (
            select(
                BookingReminder,
                col(Shift.date),
                col(Shift.start_time),
                col(Event.timezone),
            )
            .join(Shift, col(Shift.id) == col(BookingReminder.shift_id))
            .join(Booking, col(Booking.id) == col(BookingReminder.booking_id))
            .join(Task, col(Task.id) == col(Shift.task_id))
            .outerjoin(Event, col(Event.id) == col(Task.event_id))
            .where(
                col(BookingReminder.status).in_(["pending", "expired"]),
                col(Booking.status) == "confirmed",
            )
        )
        if shift_ids is not None:
            query = query.where(col(Shift.id).in_(list(shift_ids)))
        if task_id is not None:
            query = query.where(col(Task.id) == task_id)
        if event_id is not None:
            query = query.where(col(Task.event_id) == event_id)

        changed = 0
        for reminder, date, start, zone in (await db.execute(query)).all():
            slot_start = dt.datetime.combine(date, start or dt.time())
            remind_at, status = _fires_at(slot_start, reminder.offset_minutes, zone)
            if remind_at != reminder.remind_at or status != reminder.status:
                reminder.remind_at = remind_at
                reminder.status = status
                db.add(reminder)
                changed += 1
        if changed:
            await db.flush()
        return changed

    async def get_by_booking(
        self,
        db: AsyncSession,
        *,
        booking_id: uuid.UUID,
    ) -> list[BookingReminder]:
        """Get all reminders for a booking."""
        query = (
            select(BookingReminder)
            .where(col(BookingReminder.booking_id) == booking_id)
            .order_by(col(BookingReminder.offset_minutes))
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def cancel_by_booking(
        self,
        db: AsyncSession,
        *,
        booking_id: uuid.UUID,
    ) -> int:
        """Cancel all pending reminders for a booking. Returns count."""
        return await self.cancel_by_bookings(db, booking_ids=[booking_id])

    async def cancel_by_bookings(
        self,
        db: AsyncSession,
        *,
        booking_ids: Collection[uuid.UUID],
    ) -> int:
        """Cancel all pending reminders of these bookings, in one statement.
        Returns count."""
        result = await db.execute(
            update(BookingReminder)
            .where(
                col(BookingReminder.booking_id).in_(booking_ids),
                col(BookingReminder.status) == "pending",
            )
            .values(status="cancelled")
        )
        return result.rowcount  # type: ignore[return-value]

    async def fetch_due_reminders(
        self,
        db: AsyncSession,
        *,
        limit: int = 50,
    ) -> list[BookingReminder]:
        """Fetch due reminders with FOR UPDATE SKIP LOCKED for multi-worker safety."""
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        query = (
            select(BookingReminder)
            .where(
                col(BookingReminder.status) == "pending",
                col(BookingReminder.remind_at) <= now,
            )
            .order_by(col(BookingReminder.remind_at))
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_pending(
        self,
        db: AsyncSession,
        *,
        reminder_id: uuid.UUID,
    ) -> BookingReminder | None:
        """The reminder as it stands now, if it is still pending; None once it
        was sent, cancelled, expired or deleted. Read fresh, never from the
        session's identity map, because the poller acts on what it reads."""
        result = await db.execute(
            select(BookingReminder)
            .where(
                col(BookingReminder.id) == reminder_id,
                col(BookingReminder.status) == "pending",
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def mark_sent(
        self,
        db: AsyncSession,
        *,
        reminder_id: uuid.UUID,
    ) -> None:
        """Mark a reminder as sent."""
        await db.execute(
            update(BookingReminder)
            .where(col(BookingReminder.id) == reminder_id)
            .values(
                status="sent",
                updated_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
            )
        )

    async def expire_past_pending(
        self,
        db: AsyncSession,
    ) -> int:
        """Mark pending reminders for past shifts as expired."""
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        # A reminder is stale if remind_at is more than 1 hour in the past
        # and still pending (missed by the poller somehow)
        cutoff = now - dt.timedelta(hours=1)
        result = await db.execute(
            update(BookingReminder)
            .where(
                col(BookingReminder.status) == "pending",
                col(BookingReminder.remind_at) < cutoff,
            )
            .values(status="expired")
        )
        return result.rowcount  # type: ignore[return-value]

    async def cleanup_old(
        self,
        db: AsyncSession,
        *,
        days: int = 30,
    ) -> int:
        """Delete sent/cancelled/expired reminders older than N days."""
        cutoff = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(
            days=days
        )
        result = await db.execute(
            delete(BookingReminder).where(
                col(BookingReminder.status).in_(["sent", "cancelled", "expired"]),
                col(BookingReminder.updated_at) < cutoff,
            )
        )
        return result.rowcount  # type: ignore[return-value]

    async def reassign_user(
        self, db: AsyncSession, *, from_user: uuid.UUID, to_user: uuid.UUID
    ) -> None:
        """Hand one person's reminders to another, as their bookings moved.
        Each booking keeps its own rows, offsets and status."""
        await db.execute(
            update(BookingReminder)
            .where(col(BookingReminder.user_id) == from_user)
            .values(user_id=to_user)
        )

    async def count_by_booking(
        self,
        db: AsyncSession,
        *,
        booking_id: uuid.UUID,
    ) -> int:
        """Count active (pending) reminders for a booking."""
        result = await db.execute(
            select(func.count())
            .select_from(BookingReminder)
            .where(
                col(BookingReminder.booking_id) == booking_id,
                col(BookingReminder.status) == "pending",
            )
        )
        return result.scalar_one()


booking_reminder = CRUDBookingReminder(BookingReminder)
