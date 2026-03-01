"""Route tests for Event endpoints."""

import pytest
from httpx import AsyncClient

from app.models.event import Event


@pytest.mark.asyncio
class TestEventsRoutes:
    """Test suite for /events/ routes."""

    async def test_list_events(self, async_client: AsyncClient, test_event: Event):
        """Test listing events returns published events."""
        r = await async_client.get("/api/v1/events/")

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert any(item["name"] == test_event.name for item in data["items"])

    async def test_list_events_filters_drafts_for_normal_user(
        self, async_client: AsyncClient, test_event: Event, test_draft_event: Event
    ):
        """Test that normal users only see published events by default."""
        r = await async_client.get("/api/v1/events/")

        assert r.status_code == 200
        data = r.json()
        names = [item["name"] for item in data["items"]]
        assert test_event.name in names
        assert test_draft_event.name not in names

    async def test_get_event(self, async_client: AsyncClient, test_event: Event):
        """Test getting a single published event."""
        r = await async_client.get(f"/api/v1/events/{test_event.id}")

        assert r.status_code == 200
        assert r.json()["name"] == test_event.name

    async def test_draft_event_hidden_from_normal_user(
        self, async_client: AsyncClient, test_draft_event: Event
    ):
        """Test that a normal user cannot access a draft event."""
        r = await async_client.get(f"/api/v1/events/{test_draft_event.id}")

        assert r.status_code == 403

    async def test_create_event_as_admin(self, async_client: AsyncClient, as_admin):
        """Test that an admin can create an event."""
        r = await async_client.post(
            "/api/v1/events/",
            json={
                "name": "Admin Event",
                "start_date": "2026-07-01",
                "end_date": "2026-07-03",
            },
        )

        assert r.status_code == 201
        assert r.json()["name"] == "Admin Event"
        assert r.json()["status"] == "draft"

    async def test_update_event_as_admin(
        self, async_client: AsyncClient, test_event: Event, as_admin
    ):
        """Test that an admin can update an event."""
        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}",
            json={"name": "Updated Event Name"},
        )

        assert r.status_code == 200
        assert r.json()["name"] == "Updated Event Name"

    async def test_delete_event_as_admin(
        self, async_client: AsyncClient, test_event: Event, as_admin
    ):
        """Test that an admin can delete an event."""
        r = await async_client.delete(f"/api/v1/events/{test_event.id}")

        assert r.status_code == 204

    async def test_list_events_with_search(
        self, async_client: AsyncClient, test_event: Event
    ):
        """Test searching events by name."""
        r = await async_client.get("/api/v1/events/", params={"search": "Pfingsten"})

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert any(item["name"] == test_event.name for item in data["items"])

    async def test_get_nonexistent_event(self, async_client: AsyncClient):
        """Test getting a non-existent event returns 404."""
        import uuid

        fake_id = uuid.uuid4()
        r = await async_client.get(f"/api/v1/events/{fake_id}")

        assert r.status_code == 404
