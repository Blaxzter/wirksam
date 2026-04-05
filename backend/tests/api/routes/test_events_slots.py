"""Route tests for Event Slots (generation/regeneration) endpoints."""

import pytest
from httpx import AsyncClient

from app.models.event import Event


@pytest.mark.asyncio
class TestEventSlotsRoutes:
    """Test suite for event slot generation routes (admin only)."""

    async def test_create_event_with_slots(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test creating an event with auto-generated slots."""
        r = await async_client.post(
            "/api/v1/events/with-slots",
            json={
                "name": "Generated Event",
                "description": "Auto-generated slots",
                "start_date": "2026-07-01",
                "end_date": "2026-07-03",
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "17:00:00",
                    "slot_duration_minutes": 240,
                    "people_per_slot": 2,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["event"]["name"] == "Generated Event"
        assert data["duty_slots_created"] >= 1

    async def test_create_event_with_slots_and_group(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test creating an event with a new event group."""
        r = await async_client.post(
            "/api/v1/events/with-slots",
            json={
                "name": "Grouped Event",
                "start_date": "2026-08-01",
                "end_date": "2026-08-02",
                "new_event_group": {
                    "name": "New Group",
                    "start_date": "2026-08-01",
                    "end_date": "2026-08-31",
                },
                "schedule": {
                    "default_start_time": "10:00:00",
                    "default_end_time": "14:00:00",
                    "slot_duration_minutes": 120,
                    "people_per_slot": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["event_group"] is not None
        assert data["event_group"]["name"] == "New Group"

    async def test_regenerate_slots_dry_run(
        self, async_client: AsyncClient, as_admin: None, test_event: Event
    ):
        """Test regenerating slots in dry run mode."""
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/regenerate-slots",
            params={"dry_run": True},
            json={
                "schedule": {
                    "default_start_time": "08:00:00",
                    "default_end_time": "16:00:00",
                    "slot_duration_minutes": 240,
                    "people_per_slot": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert "slots_added" in data
        assert "slots_removed" in data
        assert "slots_kept" in data
        assert "affected_bookings" in data

    async def test_regenerate_slots(
        self, async_client: AsyncClient, as_admin: None, test_event: Event
    ):
        """Test actually regenerating slots."""
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/regenerate-slots",
            json={
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "17:00:00",
                    "slot_duration_minutes": 480,
                    "people_per_slot": 3,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["event"]["id"] == str(test_event.id)

    async def test_add_slots_to_event(
        self, async_client: AsyncClient, as_admin: None, test_event: Event
    ):
        """Test adding a new batch of slots to an existing event."""
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/add-slots",
            json={
                "start_date": "2026-06-15",
                "end_date": "2026-06-17",
                "schedule": {
                    "default_start_time": "10:00:00",
                    "default_end_time": "14:00:00",
                    "slot_duration_minutes": 120,
                    "people_per_slot": 2,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["slots_added"] >= 1

    async def test_list_batches(self, async_client: AsyncClient, test_event: Event):
        """Test listing slot batches for an event."""
        r = await async_client.get(f"/api/v1/events/{test_event.id}/batches")

        assert r.status_code == 200
        assert isinstance(r.json(), list)
