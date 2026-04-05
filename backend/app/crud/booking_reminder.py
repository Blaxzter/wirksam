import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.base import CRUDBase
from app.models.booking_reminder import BookingReminder
from app.schemas.booking_reminder import (
    AllowedChannel,
    BookingReminderCreate,
    ReminderOffsetEntry,
)


class CRUDBookingReminder(
    CRUDBase[BookingReminder, BookingReminderCreate, BookingReminderCreate]
):
    async def create_reminder(
        self,
        db: AsyncSession,
        *,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        duty_slot_id: uuid.UUID,
        offset_minutes: int,
        slot_start: dt.datetime,
        channels: Sequence[AllowedChannel] | None = None,
    ) -> BookingReminder:
        """Create a single reminder for a booking."""
        remind_at = slot_start - dt.timedelta(minutes=offset_minutes)
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

        # Don't create reminders that are already in the past
        if remind_at <= now:
            # Still create it but mark as expired immediately
            status = "expired"
        else:
            status = "pending"

        reminder = BookingReminder(
            booking_id=booking_id,
            user_id=user_id,
            duty_slot_id=duty_slot_id,
            remind_at=remind_at,
            offset_minutes=offset_minutes,
            status=status,
            channels=list(channels) if channels else ["push"],
        )
        db.add(reminder)
        await db.flush()
        await db.refresh(reminder)
        return reminder

    async def create_from_defaults(
        self,
        db: AsyncSession,
        *,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        duty_slot_id: uuid.UUID,
        slot_start: dt.datetime,
        defaults: Sequence[ReminderOffsetEntry],
    ) -> list[BookingReminder]:
        """Create reminders from structured defaults."""
        reminders: list[BookingReminder] = []
        for entry in defaults:
            offset = entry.offset_minutes
            channels = entry.channels
            reminder = await self.create_reminder(
                db,
                booking_id=booking_id,
                user_id=user_id,
                duty_slot_id=duty_slot_id,
                offset_minutes=offset,
                slot_start=slot_start,
                channels=channels,
            )
            reminders.append(reminder)
        return reminders

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
        result = await db.execute(
            update(BookingReminder)
            .where(
                col(BookingReminder.booking_id) == booking_id,
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
        """Mark pending reminders for past slots as expired."""
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
