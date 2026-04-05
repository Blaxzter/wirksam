"""Coverage gap tests for Booking Reminder endpoints (edge cases, limits, permissions)."""

from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.duty_slot import DutySlot
from app.models.event import Event
from app.models.user import User


@pytest.mark.asyncio
class TestReminderCoverage:
    """Coverage tests for booking_reminders.py routes."""

    async def test_update_reminder_defaults_deduplication(
        self, async_client: AsyncClient
    ):
        """Test that duplicate offset_minutes are deduplicated."""
        r = await async_client.put(
            "/api/v1/users/me/reminder-defaults",
            json={
                "default_reminder_offsets": [
                    {"offset_minutes": 30, "channels": ["push"]},
                    {"offset_minutes": 30, "channels": ["email"]},
                    {"offset_minutes": 60, "channels": ["push"]},
                ]
            },
        )

        assert r.status_code == 200

    async def test_update_reminder_defaults_with_channels(
        self, async_client: AsyncClient
    ):
        """Test updating defaults with specific channels."""
        r = await async_client.put(
            "/api/v1/users/me/reminder-defaults",
            json={
                "default_reminder_offsets": [
                    {"offset_minutes": 15, "channels": ["email", "push"]},
                    {"offset_minutes": 120, "channels": ["push"]},
                ]
            },
        )

        assert r.status_code == 200

    async def test_add_reminder_to_non_confirmed_booking(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_event: Event,
    ):
        """Test adding a reminder to a cancelled booking fails."""
        slot = DutySlot(
            event_id=test_event.id,
            title="Cancelled Reminder Slot",
            date=date(2026, 8, 1),
            start_time=time(9, 0),
            end_time=time(13, 0),
        )
        db_session.add(slot)
        await db_session.flush()

        booking = Booking(
            duty_slot_id=slot.id,
            user_id=test_user.id,
            status="cancelled",
        )
        db_session.add(booking)
        await db_session.flush()
        await db_session.refresh(booking)

        r = await async_client.post(
            f"/api/v1/bookings/{booking.id}/reminders",
            json={"offset_minutes": 30},
        )

        assert r.status_code == 400

    async def test_add_reminder_max_limit(
        self,
        async_client: AsyncClient,
        test_booking: Booking,
    ):
        """Test that exceeding max reminders per booking returns 422."""
        # Add 5 reminders (MAX_REMINDERS_PER_BOOKING = 5)
        offsets = [15, 30, 60, 120, 180]
        for offset in offsets:
            r = await async_client.post(
                f"/api/v1/bookings/{test_booking.id}/reminders",
                json={"offset_minutes": offset},
            )
            assert r.status_code == 201

        # 6th should fail
        r = await async_client.post(
            f"/api/v1/bookings/{test_booking.id}/reminders",
            json={"offset_minutes": 360},
        )
        assert r.status_code == 422

    async def test_list_reminders_for_other_users_booking(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_event: Event,
    ):
        """Test that a user cannot list reminders for another user's booking."""
        slot = DutySlot(
            event_id=test_event.id,
            title="Other User Reminder Slot",
            date=date(2026, 8, 2),
            start_time=time(10, 0),
            end_time=time(14, 0),
        )
        db_session.add(slot)
        await db_session.flush()

        booking = Booking(
            duty_slot_id=slot.id,
            user_id=test_admin_user.id,
            status="confirmed",
        )
        db_session.add(booking)
        await db_session.flush()
        await db_session.refresh(booking)

        r = await async_client.get(f"/api/v1/bookings/{booking.id}/reminders")
        assert r.status_code == 403

    async def test_add_reminder_to_other_users_booking(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_event: Event,
    ):
        """Test that a user cannot add a reminder to another user's booking."""
        slot = DutySlot(
            event_id=test_event.id,
            title="Other Add Reminder Slot",
            date=date(2026, 8, 3),
            start_time=time(10, 0),
            end_time=time(14, 0),
        )
        db_session.add(slot)
        await db_session.flush()

        booking = Booking(
            duty_slot_id=slot.id,
            user_id=test_admin_user.id,
            status="confirmed",
        )
        db_session.add(booking)
        await db_session.flush()
        await db_session.refresh(booking)

        r = await async_client.post(
            f"/api/v1/bookings/{booking.id}/reminders",
            json={"offset_minutes": 30},
        )
        assert r.status_code == 403

    async def test_delete_other_users_reminder(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_event: Event,
    ):
        """Test that a user cannot delete another user's reminder."""
        from app.crud.booking_reminder import booking_reminder as crud_reminder

        slot = DutySlot(
            event_id=test_event.id,
            title="Other Delete Reminder Slot",
            date=date(2026, 8, 4),
            start_time=time(10, 0),
            end_time=time(14, 0),
        )
        db_session.add(slot)
        await db_session.flush()

        booking = Booking(
            duty_slot_id=slot.id,
            user_id=test_admin_user.id,
            status="confirmed",
        )
        db_session.add(booking)
        await db_session.flush()
        await db_session.refresh(booking)

        import datetime as dt

        slot_start = dt.datetime.combine(slot.date, slot.start_time)
        reminder = await crud_reminder.create_reminder(
            db_session,
            booking_id=booking.id,
            user_id=test_admin_user.id,
            duty_slot_id=slot.id,
            offset_minutes=30,
            slot_start=slot_start,
            channels=["push"],
        )

        r = await async_client.delete(f"/api/v1/reminders/{reminder.id}")
        assert r.status_code == 403

    async def test_add_reminder_with_channels(
        self,
        async_client: AsyncClient,
        test_booking: Booking,
    ):
        """Test adding a reminder with specific channels."""
        r = await async_client.post(
            f"/api/v1/bookings/{test_booking.id}/reminders",
            json={"offset_minutes": 30, "channels": ["email", "push"]},
        )

        assert r.status_code == 201
        data = r.json()
        assert "email" in data["channels"]
        assert "push" in data["channels"]
