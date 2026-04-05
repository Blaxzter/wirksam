"""Extended route tests for Booking endpoints (active dates, dismiss, filters)."""

from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.duty_slot import DutySlot
from app.models.event import Event
from app.models.user import User


@pytest.mark.asyncio
class TestBookingsExtendedRoutes:
    """Extended test suite for /bookings/ routes."""

    async def test_list_my_bookings_with_status_filter(
        self, async_client: AsyncClient, test_booking: Booking
    ):
        """Test listing bookings with status filter."""
        r = await async_client.get(
            "/api/v1/bookings/me", params={"status": "confirmed"}
        )

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1

    async def test_list_my_bookings_with_date_filter(
        self, async_client: AsyncClient, test_booking: Booking
    ):
        """Test listing bookings with date range filter."""
        r = await async_client.get(
            "/api/v1/bookings/me",
            params={"date_from": "2026-01-01", "date_to": "2027-12-31"},
        )

        assert r.status_code == 200

    async def test_my_booking_active_dates(
        self, async_client: AsyncClient, test_booking: Booking
    ):
        """Test getting active booking dates."""
        r = await async_client.get(
            "/api/v1/bookings/me/active-dates",
            params={"date_from": "2026-01-01", "date_to": "2027-12-31"},
        )

        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_dismiss_cancelled_booking(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_event: Event,
    ):
        """Test dismissing a cancelled booking."""
        slot = DutySlot(
            event_id=test_event.id,
            title="Dismiss Test",
            date=date(2026, 7, 1),
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        db_session.add(slot)
        await db_session.flush()
        await db_session.refresh(slot)

        booking = Booking(
            duty_slot_id=slot.id,
            user_id=test_user.id,
            status="cancelled",
        )
        db_session.add(booking)
        await db_session.flush()
        await db_session.refresh(booking)

        r = await async_client.delete(f"/api/v1/bookings/{booking.id}/dismiss")
        assert r.status_code == 204

    async def test_dismiss_active_booking_fails(
        self, async_client: AsyncClient, test_booking: Booking
    ):
        """Test that dismissing a non-cancelled booking fails."""
        r = await async_client.delete(f"/api/v1/bookings/{test_booking.id}/dismiss")
        assert r.status_code == 400

    async def test_get_booking_not_owned(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_event: Event,
    ):
        """Test that a user cannot view another user's booking."""
        slot = DutySlot(
            event_id=test_event.id,
            title="Other User Slot",
            date=date(2026, 7, 2),
            start_time=time(9, 0),
            end_time=time(13, 0),
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

        r = await async_client.get(f"/api/v1/bookings/{booking.id}")
        assert r.status_code == 403

    async def test_rebook_cancelled_slot(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_event: Event,
    ):
        """Test rebooking a previously cancelled booking."""
        slot = DutySlot(
            event_id=test_event.id,
            title="Rebook Test",
            date=date(2026, 8, 1),
            start_time=time(10, 0),
            end_time=time(14, 0),
        )
        db_session.add(slot)
        await db_session.flush()
        await db_session.refresh(slot)

        # Create cancelled booking
        booking = Booking(
            duty_slot_id=slot.id,
            user_id=test_user.id,
            status="cancelled",
        )
        db_session.add(booking)
        await db_session.flush()

        # Rebook
        r = await async_client.post(
            "/api/v1/bookings/",
            json={"duty_slot_id": str(slot.id)},
        )
        assert r.status_code == 201
        assert r.json()["status"] == "confirmed"

    async def test_list_my_bookings_pagination(
        self, async_client: AsyncClient, test_booking: Booking
    ):
        """Test bookings list pagination."""
        r = await async_client.get(
            "/api/v1/bookings/me", params={"skip": 0, "limit": 1}
        )

        assert r.status_code == 200
        data = r.json()
        assert data["skip"] == 0
        assert data["limit"] == 1
