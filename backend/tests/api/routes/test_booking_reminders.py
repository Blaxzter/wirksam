"""Route tests for Booking Reminder endpoints."""

import pytest
from httpx import AsyncClient

from app.models.booking import Booking


@pytest.mark.asyncio
class TestBookingReminderRoutes:
    """Test suite for booking reminder routes."""

    async def test_get_reminder_defaults(self, async_client: AsyncClient):
        """Test getting the current user's default reminder offsets."""
        r = await async_client.get("/api/v1/users/me/reminder-defaults")

        assert r.status_code == 200
        data = r.json()
        assert "default_reminder_offsets" in data

    async def test_update_reminder_defaults(self, async_client: AsyncClient):
        """Test updating the current user's default reminder offsets."""
        r = await async_client.put(
            "/api/v1/users/me/reminder-defaults",
            json={
                "default_reminder_offsets": [
                    {"offset_minutes": 30},
                    {"offset_minutes": 60},
                ]
            },
        )

        assert r.status_code == 200

    async def test_list_booking_reminders(
        self, async_client: AsyncClient, test_booking: Booking
    ):
        """Test listing reminders for a booking."""
        r = await async_client.get(f"/api/v1/bookings/{test_booking.id}/reminders")

        assert r.status_code == 200
        data = r.json()
        assert "items" in data

    async def test_add_booking_reminder(
        self, async_client: AsyncClient, test_booking: Booking
    ):
        """Test adding a reminder to a booking."""
        r = await async_client.post(
            f"/api/v1/bookings/{test_booking.id}/reminders",
            json={"offset_minutes": 30},
        )

        assert r.status_code == 201
        data = r.json()
        assert data["offset_minutes"] == 30

    async def test_add_and_delete_reminder(
        self, async_client: AsyncClient, test_booking: Booking
    ):
        """Test adding and then deleting a reminder."""
        # Add
        r1 = await async_client.post(
            f"/api/v1/bookings/{test_booking.id}/reminders",
            json={"offset_minutes": 15},
        )
        assert r1.status_code == 201
        reminder_id = r1.json()["id"]

        # Delete
        r2 = await async_client.delete(f"/api/v1/reminders/{reminder_id}")
        assert r2.status_code == 204

    async def test_delete_nonexistent_reminder(self, async_client: AsyncClient):
        """Test deleting a nonexistent reminder returns 404."""
        import uuid

        fake_id = uuid.uuid4()
        r = await async_client.delete(f"/api/v1/reminders/{fake_id}")
        assert r.status_code == 404

    async def test_list_reminders_for_nonexistent_booking(
        self, async_client: AsyncClient
    ):
        """Test listing reminders for a nonexistent booking returns 404."""
        import uuid

        fake_id = uuid.uuid4()
        r = await async_client.get(f"/api/v1/bookings/{fake_id}/reminders")
        assert r.status_code == 404
