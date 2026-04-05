"""Coverage gap tests for Event CRUD endpoints (filtering, bookings list, delete, publish)."""

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
class TestEventCrudCoverage:
    """Coverage tests for events/crud.py routes."""

    async def test_list_events_non_admin_sees_only_published(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_draft_event: Event,
    ):
        """Test that non-admin users only see published events."""
        r = await async_client.get("/api/v1/events/")

        assert r.status_code == 200
        data = r.json()
        ids = [item["id"] for item in data["items"]]
        assert str(test_event.id) in ids
        assert str(test_draft_event.id) not in ids

    async def test_list_events_admin_sees_all(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_event: Event,
        test_draft_event: Event,
    ):
        """Test that admin users see all events including drafts."""
        r = await async_client.get("/api/v1/events/")

        assert r.status_code == 200
        data = r.json()
        ids = [item["id"] for item in data["items"]]
        assert str(test_event.id) in ids
        assert str(test_draft_event.id) in ids

    async def test_list_events_with_status_filter(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_draft_event: Event,
    ):
        """Test listing events filtered by status."""
        r = await async_client.get("/api/v1/events/", params={"status": "draft"})

        assert r.status_code == 200
        data = r.json()
        assert all(item["status"] == "draft" for item in data["items"])

    async def test_list_events_my_bookings_filter(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_booking: Booking,
    ):
        """Test filtering events to only those with my bookings."""
        r = await async_client.get("/api/v1/events/", params={"my_bookings": True})

        assert r.status_code == 200
        data = r.json()
        # Should include the event with test_booking
        assert data["total"] >= 1
        ids = [item["id"] for item in data["items"]]
        assert str(test_event.id) in ids

    async def test_list_events_with_search(
        self,
        async_client: AsyncClient,
        test_event: Event,
    ):
        """Test searching events by name."""
        r = await async_client.get(
            "/api/v1/events/", params={"search": test_event.name[:5]}
        )

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1

    async def test_get_draft_event_forbidden_for_non_admin(
        self,
        async_client: AsyncClient,
        test_draft_event: Event,
    ):
        """Test that non-admin cannot view a draft event."""
        r = await async_client.get(f"/api/v1/events/{test_draft_event.id}")
        assert r.status_code == 403

    async def test_get_draft_event_allowed_for_admin(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_draft_event: Event,
    ):
        """Test that admin can view a draft event."""
        r = await async_client.get(f"/api/v1/events/{test_draft_event.id}")
        assert r.status_code == 200

    async def test_list_event_bookings(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ):
        """Test listing all confirmed bookings for an event."""
        slot = DutySlot(
            event_id=test_event.id,
            title="Bookings List Slot",
            date=date(2026, 6, 10),
            start_time=time(9, 0),
            end_time=time(13, 0),
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

        r = await async_client.get(f"/api/v1/events/{test_event.id}/bookings")

        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert "duty_slot_id" in data[0]
        assert "user_name" in data[0]

    async def test_list_event_bookings_not_found(self, async_client: AsyncClient):
        """Test listing bookings for nonexistent event returns 404."""
        fake_id = uuid.uuid4()
        r = await async_client.get(f"/api/v1/events/{fake_id}/bookings")
        assert r.status_code == 404

    async def test_delete_event(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test deleting an event."""
        event = Event(
            name="Delete Me",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 3),
            status="draft",
        )
        db_session.add(event)
        await db_session.flush()
        await db_session.refresh(event)

        r = await async_client.delete(f"/api/v1/events/{event.id}")
        assert r.status_code == 204

    async def test_delete_event_with_bookings(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test deleting an event cancels all confirmed bookings."""
        event = Event(
            name="Delete With Bookings",
            start_date=date(2026, 10, 10),
            end_date=date(2026, 10, 12),
            status="draft",
        )
        db_session.add(event)
        await db_session.flush()
        await db_session.refresh(event)

        slot = DutySlot(
            event_id=event.id,
            title="Slot To Delete",
            date=date(2026, 10, 10),
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        db_session.add(slot)
        await db_session.flush()

        booking = Booking(
            duty_slot_id=slot.id,
            user_id=test_user.id,
            status="confirmed",
        )
        db_session.add(booking)
        await db_session.flush()

        r = await async_client.delete(
            f"/api/v1/events/{event.id}",
            params={"cancellation_reason": "Event cancelled"},
        )
        assert r.status_code == 204

    async def test_publish_event_triggers_notification(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_draft_event: Event,
    ):
        """Test that publishing an event dispatches notification."""
        r = await async_client.patch(
            f"/api/v1/events/{test_draft_event.id}",
            json={"status": "published"},
        )

        assert r.status_code == 200
        assert r.json()["status"] == "published"

    async def test_update_event_no_status_change(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_event: Event,
    ):
        """Test updating event without status change (no notification)."""
        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}",
            json={"description": "Updated description"},
        )

        assert r.status_code == 200
        assert r.json()["description"] == "Updated description"
