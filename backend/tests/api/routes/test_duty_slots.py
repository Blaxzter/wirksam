"""Route tests for DutySlot endpoints."""

import uuid
from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.duty_slot import DutySlot
from app.models.event import Event


@pytest.mark.asyncio
class TestDutySlotRoutes:
    """Test suite for /duty-slots/ routes."""

    async def test_list_duty_slots(
        self, async_client: AsyncClient, test_duty_slot: DutySlot
    ):
        """Test listing duty slots."""
        r = await async_client.get("/api/v1/duty-slots/")

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert any(item["id"] == str(test_duty_slot.id) for item in data["items"])

    async def test_list_duty_slots_filter_by_event(
        self, async_client: AsyncClient, test_duty_slot: DutySlot, test_event: Event
    ):
        """Test filtering duty slots by event_id."""
        r = await async_client.get(
            "/api/v1/duty-slots/", params={"event_id": str(test_event.id)}
        )

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert all(item["event_id"] == str(test_event.id) for item in data["items"])

    async def test_list_duty_slots_search(
        self, async_client: AsyncClient, test_duty_slot: DutySlot
    ):
        """Test searching duty slots."""
        r = await async_client.get(
            "/api/v1/duty-slots/",
            params={"search": test_duty_slot.title[:5]},
        )

        assert r.status_code == 200
        assert r.json()["total"] >= 1

    async def test_get_duty_slot(
        self, async_client: AsyncClient, test_duty_slot: DutySlot
    ):
        """Test getting a specific duty slot."""
        r = await async_client.get(f"/api/v1/duty-slots/{test_duty_slot.id}")

        assert r.status_code == 200
        assert r.json()["id"] == str(test_duty_slot.id)
        assert "current_bookings" in r.json()
        assert "is_booked_by_me" in r.json()

    async def test_get_duty_slot_not_found(self, async_client: AsyncClient):
        """Test getting a nonexistent duty slot."""
        fake_id = uuid.uuid4()
        r = await async_client.get(f"/api/v1/duty-slots/{fake_id}")
        assert r.status_code == 404

    async def test_create_duty_slot(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_event: Event,
    ):
        """Test creating a duty slot (admin only)."""
        r = await async_client.post(
            "/api/v1/duty-slots/",
            json={
                "event_id": str(test_event.id),
                "title": "New Shift",
                "date": "2026-06-15",
                "start_time": "09:00:00",
                "end_time": "13:00:00",
                "max_bookings": 2,
            },
        )

        assert r.status_code == 201
        assert r.json()["title"] == "New Shift"
        assert r.json()["max_bookings"] == 2

    async def test_update_duty_slot(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_duty_slot: DutySlot,
    ):
        """Test updating a duty slot (admin only)."""
        r = await async_client.patch(
            f"/api/v1/duty-slots/{test_duty_slot.id}",
            json={"title": "Updated Shift Title"},
        )

        assert r.status_code == 200
        assert r.json()["title"] == "Updated Shift Title"

    async def test_delete_duty_slot(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_event: Event,
    ):
        """Test deleting a duty slot (admin only)."""
        slot = DutySlot(
            event_id=test_event.id,
            title="To Delete",
            date=date(2026, 9, 1),
            start_time=time(10, 0),
            end_time=time(14, 0),
        )
        db_session.add(slot)
        await db_session.flush()
        await db_session.refresh(slot)

        r = await async_client.delete(f"/api/v1/duty-slots/{slot.id}")
        assert r.status_code == 204

    async def test_list_slot_bookings(
        self, async_client: AsyncClient, test_duty_slot: DutySlot
    ):
        """Test listing bookings for a specific slot."""
        r = await async_client.get(f"/api/v1/duty-slots/{test_duty_slot.id}/bookings")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
