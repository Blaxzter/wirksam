"""Route tests for EventGroup and UserAvailability endpoints."""

from typing import Any

import pytest
from httpx import AsyncClient

from app.models.event_group import EventGroup
from app.models.user_availability import UserAvailability


@pytest.mark.asyncio
class TestEventGroupRoutes:
    """Test suite for /event-groups/ routes."""

    async def test_list_event_groups(
        self, async_client: AsyncClient, test_event_group: EventGroup
    ):
        """Test listing event groups returns published groups for normal users."""
        r = await async_client.get("/api/v1/event-groups/")

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert any(item["name"] == test_event_group.name for item in data["items"])

    async def test_list_event_groups_hides_drafts_from_normal_user(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
        test_draft_event_group: EventGroup,
    ):
        """Test that draft groups are not visible to normal users."""
        r = await async_client.get("/api/v1/event-groups/")

        assert r.status_code == 200
        names = [item["name"] for item in r.json()["items"]]
        assert test_event_group.name in names
        assert test_draft_event_group.name not in names

    async def test_list_event_groups_admin_sees_all(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
        test_draft_event_group: EventGroup,
        as_admin: None,
    ):
        """Test that admins can see all groups including drafts."""
        r = await async_client.get("/api/v1/event-groups/")

        assert r.status_code == 200
        names = [item["name"] for item in r.json()["items"]]
        assert test_event_group.name in names
        assert test_draft_event_group.name in names

    async def test_get_event_group(
        self, async_client: AsyncClient, test_event_group: EventGroup
    ):
        """Test getting a single published event group."""
        r = await async_client.get(f"/api/v1/event-groups/{test_event_group.id}")

        assert r.status_code == 200
        assert r.json()["name"] == test_event_group.name
        assert r.json()["status"] == "published"

    async def test_draft_event_group_hidden_from_normal_user(
        self, async_client: AsyncClient, test_draft_event_group: EventGroup
    ):
        """Test that a normal user cannot access a draft event group."""
        r = await async_client.get(f"/api/v1/event-groups/{test_draft_event_group.id}")

        assert r.status_code == 403

    async def test_draft_event_group_accessible_to_admin(
        self,
        async_client: AsyncClient,
        test_draft_event_group: EventGroup,
        as_admin: None,
    ):
        """Test that an admin can access a draft event group."""
        r = await async_client.get(f"/api/v1/event-groups/{test_draft_event_group.id}")

        assert r.status_code == 200
        assert r.json()["status"] == "draft"

    async def test_get_nonexistent_event_group(self, async_client: AsyncClient):
        """Test getting a non-existent event group returns 404."""
        import uuid

        r = await async_client.get(f"/api/v1/event-groups/{uuid.uuid4()}")
        assert r.status_code == 404

    async def test_create_event_group_as_admin(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test that an admin can create an event group."""
        r = await async_client.post(
            "/api/v1/event-groups/",
            json={
                "name": "Neue Gruppe",
                "start_date": "2026-08-01",
                "end_date": "2026-08-07",
            },
        )

        assert r.status_code == 201
        assert r.json()["name"] == "Neue Gruppe"
        assert r.json()["status"] == "draft"

    async def test_update_event_group_as_admin(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
        as_admin: None,
    ):
        """Test that an admin can update an event group."""
        r = await async_client.patch(
            f"/api/v1/event-groups/{test_event_group.id}",
            json={"name": "Renamed Group"},
        )

        assert r.status_code == 200
        assert r.json()["name"] == "Renamed Group"

    async def test_delete_event_group_as_admin(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
        as_admin: None,
    ):
        """Test that an admin can delete an event group."""
        r = await async_client.delete(f"/api/v1/event-groups/{test_event_group.id}")
        assert r.status_code == 204

    async def test_search_event_groups(
        self, async_client: AsyncClient, test_event_group: EventGroup
    ):
        """Test searching event groups by name."""
        r = await async_client.get(
            "/api/v1/event-groups/", params={"search": "Kirchentags"}
        )

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert any(item["name"] == test_event_group.name for item in data["items"])


@pytest.mark.asyncio
class TestAvailabilityRoutes:
    """Test suite for /event-groups/{id}/availability routes."""

    async def test_set_availability_fully_available(
        self, async_client: AsyncClient, test_event_group: EventGroup
    ):
        """Test registering as fully available."""
        r = await async_client.post(
            f"/api/v1/event-groups/{test_event_group.id}/availability",
            json={
                "availability_type": "fully_available",
                "notes": "Ready!",
                "dates": [],
            },
        )

        assert r.status_code == 201
        assert r.json()["availability_type"] == "fully_available"
        assert r.json()["notes"] == "Ready!"
        assert r.json()["available_dates"] == []

    async def test_set_availability_specific_dates(
        self, async_client: AsyncClient, test_event_group: EventGroup
    ):
        """Test registering availability on specific dates."""
        r = await async_client.post(
            f"/api/v1/event-groups/{test_event_group.id}/availability",
            json={
                "availability_type": "specific_dates",
                "dates": ["2026-06-10", "2026-06-11"],
            },
        )

        assert r.status_code == 201
        assert r.json()["availability_type"] == "specific_dates"
        assert len(r.json()["available_dates"]) == 2

    async def test_set_availability_upserts(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
        test_user_availability: UserAvailability,
    ):
        """Test that posting again updates the existing availability record."""
        r = await async_client.post(
            f"/api/v1/event-groups/{test_event_group.id}/availability",
            json={
                "availability_type": "specific_dates",
                "notes": "Updated",
                "dates": ["2026-06-13"],
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["availability_type"] == "specific_dates"
        assert data["notes"] == "Updated"
        assert len(data["available_dates"]) == 1

    async def test_get_my_availability(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
        test_user_availability: UserAvailability,
    ):
        """Test retrieving the current user's availability."""
        r = await async_client.get(
            f"/api/v1/event-groups/{test_event_group.id}/availability/me"
        )

        assert r.status_code == 200
        assert r.json()["availability_type"] == test_user_availability.availability_type
        assert r.json()["user_id"] == str(test_user_availability.user_id)

    async def test_get_my_availability_not_found(
        self, async_client: AsyncClient, test_event_group: EventGroup
    ):
        """Test that 404 is returned when no availability is registered."""
        r = await async_client.get(
            f"/api/v1/event-groups/{test_event_group.id}/availability/me"
        )
        assert r.status_code == 404

    async def test_delete_my_availability(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
        test_user_availability: UserAvailability,
    ):
        """Test removing own availability."""
        r = await async_client.delete(
            f"/api/v1/event-groups/{test_event_group.id}/availability/me"
        )
        assert r.status_code == 204

        # Confirm it's gone
        r2 = await async_client.get(
            f"/api/v1/event-groups/{test_event_group.id}/availability/me"
        )
        assert r2.status_code == 404

    async def test_delete_my_availability_not_found(
        self, async_client: AsyncClient, test_event_group: EventGroup
    ):
        """Test that deleting non-existent availability returns 404."""
        r = await async_client.delete(
            f"/api/v1/event-groups/{test_event_group.id}/availability/me"
        )
        assert r.status_code == 404

    async def test_list_availabilities_as_admin(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
        test_user_availability: UserAvailability,
        as_admin: None,
    ):
        """Test admin can list all availabilities for a group."""
        r = await async_client.get(
            f"/api/v1/event-groups/{test_event_group.id}/availabilities"
        )

        assert r.status_code == 200
        data: list[dict[str, Any]] = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(
            item["user_id"] == str(test_user_availability.user_id) for item in data
        )

    async def test_availability_for_nonexistent_group(self, async_client: AsyncClient):
        """Test that posting availability for a non-existent group returns 404."""
        import uuid

        r = await async_client.post(
            f"/api/v1/event-groups/{uuid.uuid4()}/availability",
            json={"availability_type": "fully_available", "dates": []},
        )
        assert r.status_code == 404

    async def test_availability_with_dates_returned(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
        test_user_availability_with_dates: UserAvailability,
    ):
        """Test that specific-date availability includes date entries in response."""
        r = await async_client.get(
            f"/api/v1/event-groups/{test_event_group.id}/availability/me"
        )

        assert r.status_code == 200
        data = r.json()
        assert data["availability_type"] == "specific_dates"
        assert len(data["available_dates"]) == 2
        dates = {d["slot_date"] for d in data["available_dates"]}
        assert "2026-06-10" in dates
        assert "2026-06-11" in dates
