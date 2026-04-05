"""Coverage gap tests for DutySlot endpoints (time change, delete with bookings, enrichment)."""

import uuid
from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.duty_slot import DutySlot
from app.models.event import Event
from app.models.user import User


@pytest.mark.asyncio
class TestDutySlotCoverage:
    """Coverage tests for duty slot routes."""

    async def test_update_slot_time_change_triggers_notification(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_duty_slot: DutySlot,
        test_booking: Booking,
    ):
        """Test that updating start_time on a booked slot triggers notification."""
        r = await async_client.patch(
            f"/api/v1/duty-slots/{test_duty_slot.id}",
            json={"start_time": "10:00:00"},
        )

        assert r.status_code == 200
        assert r.json()["start_time"] == "10:00:00"

    async def test_update_slot_date_change(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_duty_slot: DutySlot,
        test_booking: Booking,
    ):
        """Test updating slot date triggers time-change notification."""
        r = await async_client.patch(
            f"/api/v1/duty-slots/{test_duty_slot.id}",
            json={"date": "2026-05-25"},
        )

        assert r.status_code == 200
        assert r.json()["date"] == "2026-05-25"

    async def test_update_slot_end_time_change(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_duty_slot: DutySlot,
        test_booking: Booking,
    ):
        """Test updating slot end_time triggers notification."""
        r = await async_client.patch(
            f"/api/v1/duty-slots/{test_duty_slot.id}",
            json={"end_time": "15:00:00"},
        )

        assert r.status_code == 200
        assert r.json()["end_time"] == "15:00:00"

    async def test_delete_slot_with_confirmed_bookings(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ):
        """Test deleting a slot with confirmed bookings cancels them."""
        slot = DutySlot(
            event_id=test_event.id,
            title="Delete Me With Booking",
            date=date(2026, 9, 15),
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        db_session.add(slot)
        await db_session.flush()
        await db_session.refresh(slot)

        booking = Booking(
            duty_slot_id=slot.id,
            user_id=test_user.id,
            status="confirmed",
        )
        db_session.add(booking)
        await db_session.flush()

        r = await async_client.delete(
            f"/api/v1/duty-slots/{slot.id}",
            params={"cancellation_reason": "Slot removed by admin"},
        )
        assert r.status_code == 204

    async def test_delete_slot_with_cancellation_reason(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_event: Event,
    ):
        """Test deleting a slot with a cancellation reason."""
        slot = DutySlot(
            event_id=test_event.id,
            title="Delete Reason Slot",
            date=date(2026, 9, 16),
            start_time=time(10, 0),
            end_time=time(14, 0),
        )
        db_session.add(slot)
        await db_session.flush()
        await db_session.refresh(slot)

        r = await async_client.delete(
            f"/api/v1/duty-slots/{slot.id}",
            params={"cancellation_reason": "Event rescheduled"},
        )
        assert r.status_code == 204

    async def test_list_slots_for_draft_event_forbidden(
        self,
        async_client: AsyncClient,
        test_draft_event: Event,
    ):
        """Test that non-admin users cannot list slots for draft events."""
        r = await async_client.get(
            "/api/v1/duty-slots/",
            params={"event_id": str(test_draft_event.id)},
        )
        assert r.status_code == 403

    async def test_slot_is_booked_by_me(
        self,
        async_client: AsyncClient,
        test_duty_slot: DutySlot,
        test_booking: Booking,
    ):
        """Test that is_booked_by_me is True when user has a confirmed booking."""
        r = await async_client.get(f"/api/v1/duty-slots/{test_duty_slot.id}")

        assert r.status_code == 200
        assert r.json()["is_booked_by_me"] is True
        assert r.json()["current_bookings"] >= 1

    async def test_slot_is_not_booked_by_me(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
    ):
        """Test that is_booked_by_me is False when user has no booking."""
        slot = DutySlot(
            event_id=test_event.id,
            title="Not Booked Slot",
            date=date(2026, 9, 20),
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        db_session.add(slot)
        await db_session.flush()
        await db_session.refresh(slot)

        r = await async_client.get(f"/api/v1/duty-slots/{slot.id}")

        assert r.status_code == 200
        assert r.json()["is_booked_by_me"] is False
        assert r.json()["current_bookings"] == 0

    async def test_list_slot_bookings_with_user_info(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ):
        """Test listing slot bookings returns user info."""
        slot = DutySlot(
            event_id=test_event.id,
            title="Bookings List Slot",
            date=date(2026, 9, 21),
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        db_session.add(slot)
        await db_session.flush()
        await db_session.refresh(slot)

        booking = Booking(
            duty_slot_id=slot.id,
            user_id=test_user.id,
            status="confirmed",
            notes="Test booking",
        )
        db_session.add(booking)
        await db_session.flush()

        r = await async_client.get(f"/api/v1/duty-slots/{slot.id}/bookings")

        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert data[0]["user_name"] is not None
        assert data[0]["user_email"] is not None

    async def test_list_slot_bookings_not_found(self, async_client: AsyncClient):
        """Test listing bookings for nonexistent slot returns 404."""
        fake_id = uuid.uuid4()
        r = await async_client.get(f"/api/v1/duty-slots/{fake_id}/bookings")
        assert r.status_code == 404

    async def test_list_slots_enrichment(
        self,
        async_client: AsyncClient,
        test_duty_slot: DutySlot,
        test_booking: Booking,
    ):
        """Test that list endpoint returns enriched slots with booking counts."""
        r = await async_client.get("/api/v1/duty-slots/")

        assert r.status_code == 200
        data = r.json()
        items = data["items"]
        slot_item = next((i for i in items if i["id"] == str(test_duty_slot.id)), None)
        assert slot_item is not None
        assert "current_bookings" in slot_item
        assert "is_booked_by_me" in slot_item
        assert slot_item["current_bookings"] >= 1
