"""Unit tests for BookingReminder CRUD operations."""

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.models.booking import Booking
from app.models.shift import Shift
from app.models.user import User


@pytest.mark.asyncio
class TestCRUDBookingReminder:
    """Test suite for BookingReminder CRUD operations."""

    async def test_create_reminder_future(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ):
        """Test creating a reminder for a future shift."""
        slot_start = dt.datetime(2030, 6, 1, 10, 0)
        reminder = await crud_reminder.create_reminder(
            db_session,
            booking_id=test_booking.id,
            user_id=test_user.id,
            shift_id=test_shift.id,
            offset_minutes=30,
            slot_start=slot_start,
        )

        assert reminder.offset_minutes == 30
        assert reminder.status == "pending"
        assert reminder.channels == ["push"]

    async def test_create_reminder_past_is_expired(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ):
        """Test creating a reminder for a past shift marks it expired."""
        slot_start = dt.datetime(2020, 1, 1, 10, 0)
        reminder = await crud_reminder.create_reminder(
            db_session,
            booking_id=test_booking.id,
            user_id=test_user.id,
            shift_id=test_shift.id,
            offset_minutes=30,
            slot_start=slot_start,
        )

        assert reminder.status == "expired"

    @pytest.mark.parametrize(
        ("slot_start", "remind_at"),
        [
            # 15 minutes before 10:00 in Berlin is 08:45 UTC in winter, 07:45 in
            # summer. Stored as 09:45, it fired 45 minutes after the shift began.
            (dt.datetime(2030, 1, 15, 10, 0), dt.datetime(2030, 1, 15, 8, 45)),
            (dt.datetime(2030, 7, 15, 10, 0), dt.datetime(2030, 7, 15, 7, 45)),
        ],
    )
    async def test_remind_at_is_stored_in_utc(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
        slot_start: dt.datetime,
        remind_at: dt.datetime,
    ):
        """The poller compares ``remind_at`` with UTC, so that's how it's stored."""
        monkeypatch.setattr(settings, "EVENT_TIMEZONE", "Europe/Berlin")
        reminder = await crud_reminder.create_reminder(
            db_session,
            booking_id=test_booking.id,
            user_id=test_user.id,
            shift_id=test_shift.id,
            offset_minutes=15,
            slot_start=slot_start,
        )

        assert reminder.remind_at == remind_at

    async def test_create_reminder_with_channels(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ):
        """Test creating a reminder with custom channels."""
        slot_start = dt.datetime(2030, 6, 1, 10, 0)
        reminder = await crud_reminder.create_reminder(
            db_session,
            booking_id=test_booking.id,
            user_id=test_user.id,
            shift_id=test_shift.id,
            offset_minutes=60,
            slot_start=slot_start,
            channels=["email", "push"],
        )

        assert reminder.channels == ["email", "push"]

    async def test_get_by_booking(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ):
        """Test getting reminders for a booking."""
        slot_start = dt.datetime(2030, 6, 1, 10, 0)
        await crud_reminder.create_reminder(
            db_session,
            booking_id=test_booking.id,
            user_id=test_user.id,
            shift_id=test_shift.id,
            offset_minutes=30,
            slot_start=slot_start,
        )
        await crud_reminder.create_reminder(
            db_session,
            booking_id=test_booking.id,
            user_id=test_user.id,
            shift_id=test_shift.id,
            offset_minutes=60,
            slot_start=slot_start,
        )

        reminders = await crud_reminder.get_by_booking(
            db_session, booking_id=test_booking.id
        )
        assert len(reminders) == 2
        # Should be ordered by offset_minutes
        assert reminders[0].offset_minutes <= reminders[1].offset_minutes

    async def test_count_by_booking(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ):
        """Test counting pending reminders for a booking."""
        slot_start = dt.datetime(2030, 6, 1, 10, 0)
        await crud_reminder.create_reminder(
            db_session,
            booking_id=test_booking.id,
            user_id=test_user.id,
            shift_id=test_shift.id,
            offset_minutes=30,
            slot_start=slot_start,
        )

        count = await crud_reminder.count_by_booking(
            db_session, booking_id=test_booking.id
        )
        assert count == 1

    async def test_cancel_by_booking(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ):
        """Test cancelling all pending reminders for a booking."""
        slot_start = dt.datetime(2030, 6, 1, 10, 0)
        await crud_reminder.create_reminder(
            db_session,
            booking_id=test_booking.id,
            user_id=test_user.id,
            shift_id=test_shift.id,
            offset_minutes=30,
            slot_start=slot_start,
        )
        await crud_reminder.create_reminder(
            db_session,
            booking_id=test_booking.id,
            user_id=test_user.id,
            shift_id=test_shift.id,
            offset_minutes=60,
            slot_start=slot_start,
        )

        cancelled = await crud_reminder.cancel_by_booking(
            db_session, booking_id=test_booking.id
        )
        assert cancelled == 2

        count = await crud_reminder.count_by_booking(
            db_session, booking_id=test_booking.id
        )
        assert count == 0

    async def test_mark_sent(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ):
        """Test marking a reminder as sent."""
        slot_start = dt.datetime(2030, 6, 1, 10, 0)
        reminder = await crud_reminder.create_reminder(
            db_session,
            booking_id=test_booking.id,
            user_id=test_user.id,
            shift_id=test_shift.id,
            offset_minutes=30,
            slot_start=slot_start,
        )

        await crud_reminder.mark_sent(db_session, reminder_id=reminder.id)

        # Re-fetch to check status
        reminders = await crud_reminder.get_by_booking(
            db_session, booking_id=test_booking.id
        )
        assert reminders[0].status == "sent"

    async def test_create_from_defaults(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ):
        """Test creating reminders from default offsets."""
        from app.schemas.booking_reminder import ReminderOffsetEntry

        slot_start = dt.datetime(2030, 6, 1, 10, 0)
        defaults = [
            ReminderOffsetEntry(offset_minutes=15),
            ReminderOffsetEntry(offset_minutes=60),
        ]

        reminders = await crud_reminder.create_from_defaults(
            db_session,
            booking_id=test_booking.id,
            user_id=test_user.id,
            shift_id=test_shift.id,
            slot_start=slot_start,
            defaults=defaults,
        )

        assert len(reminders) == 2
        offsets = {r.offset_minutes for r in reminders}
        assert offsets == {15, 60}
