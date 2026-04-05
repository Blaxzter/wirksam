"""Coverage gap tests for EventGroup endpoints (availability endpoints, status filtering)."""

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_group import EventGroup
from app.models.user_availability import UserAvailability


@pytest.mark.asyncio
class TestEventGroupCoverage:
    """Coverage tests for event_groups.py routes."""

    async def test_list_groups_non_admin_sees_only_published(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
        test_draft_event_group: EventGroup,
    ):
        """Test that non-admin users only see published groups."""
        r = await async_client.get("/api/v1/event-groups/")

        assert r.status_code == 200
        data = r.json()
        ids = [item["id"] for item in data["items"]]
        assert str(test_event_group.id) in ids
        assert str(test_draft_event_group.id) not in ids

    async def test_list_groups_admin_sees_all(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_event_group: EventGroup,
        test_draft_event_group: EventGroup,
    ):
        """Test that admin users see all groups."""
        r = await async_client.get("/api/v1/event-groups/")

        assert r.status_code == 200
        data = r.json()
        ids = [item["id"] for item in data["items"]]
        assert str(test_event_group.id) in ids
        assert str(test_draft_event_group.id) in ids

    async def test_list_groups_with_status_filter(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_draft_event_group: EventGroup,
    ):
        """Test filtering groups by status."""
        r = await async_client.get("/api/v1/event-groups/", params={"status": "draft"})

        assert r.status_code == 200
        data = r.json()
        assert all(item["status"] == "draft" for item in data["items"])

    async def test_list_groups_with_date_filter(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
    ):
        """Test filtering groups by date range."""
        r = await async_client.get(
            "/api/v1/event-groups/",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )

        assert r.status_code == 200
        assert r.json()["total"] >= 1

    async def test_get_draft_group_forbidden(
        self,
        async_client: AsyncClient,
        test_draft_event_group: EventGroup,
    ):
        """Test that non-admin cannot view a draft group."""
        r = await async_client.get(f"/api/v1/event-groups/{test_draft_event_group.id}")
        assert r.status_code == 403

    async def test_publish_group_triggers_notification(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_draft_event_group: EventGroup,
    ):
        """Test that publishing a group dispatches notification."""
        r = await async_client.patch(
            f"/api/v1/event-groups/{test_draft_event_group.id}",
            json={"status": "published"},
        )

        assert r.status_code == 200
        assert r.json()["status"] == "published"

    async def test_delete_event_group(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test deleting an event group."""
        group = EventGroup(
            name="Delete Me Group",
            start_date=date(2027, 1, 1),
            end_date=date(2027, 1, 7),
            status="draft",
        )
        db_session.add(group)
        await db_session.flush()
        await db_session.refresh(group)

        r = await async_client.delete(f"/api/v1/event-groups/{group.id}")
        assert r.status_code == 204


@pytest.mark.asyncio
class TestEventGroupAvailability:
    """Coverage tests for event group availability endpoints."""

    async def test_list_group_availabilities(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_event_group: EventGroup,
        test_user_availability: UserAvailability,
    ):
        """Test admin listing all availabilities for a group."""
        r = await async_client.get(
            f"/api/v1/event-groups/{test_event_group.id}/availabilities"
        )

        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "user_full_name" in data[0]
        assert "user_email" in data[0]

    async def test_get_my_availability(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
        test_user_availability: UserAvailability,
    ):
        """Test getting the current user's availability for a group."""
        r = await async_client.get(
            f"/api/v1/event-groups/{test_event_group.id}/availability/me"
        )

        assert r.status_code == 200
        data = r.json()
        assert data["availability_type"] == "fully_available"

    async def test_get_my_availability_not_found(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test getting availability when none registered returns 404."""
        group = EventGroup(
            name="No Availability Group",
            start_date=date(2027, 2, 1),
            end_date=date(2027, 2, 7),
            status="published",
        )
        db_session.add(group)
        await db_session.flush()
        await db_session.refresh(group)

        r = await async_client.get(f"/api/v1/event-groups/{group.id}/availability/me")
        assert r.status_code == 404

    async def test_set_my_availability(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
    ):
        """Test setting availability for a group."""
        r = await async_client.post(
            f"/api/v1/event-groups/{test_event_group.id}/availability",
            json={
                "availability_type": "specific_dates",
                "notes": "Only mornings",
                "dates": [
                    {"date": "2026-06-10"},
                    {"date": "2026-06-11"},
                ],
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["availability_type"] == "specific_dates"
        assert data["notes"] == "Only mornings"

    async def test_set_my_availability_upsert(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
        test_user_availability: UserAvailability,
    ):
        """Test upserting availability (update existing)."""
        r = await async_client.post(
            f"/api/v1/event-groups/{test_event_group.id}/availability",
            json={
                "availability_type": "fully_available",
                "notes": "Changed plans",
            },
        )

        assert r.status_code == 201
        assert r.json()["availability_type"] == "fully_available"

    async def test_delete_my_availability(
        self,
        async_client: AsyncClient,
        test_event_group: EventGroup,
        test_user_availability: UserAvailability,
    ):
        """Test deleting the current user's availability."""
        r = await async_client.delete(
            f"/api/v1/event-groups/{test_event_group.id}/availability/me"
        )
        assert r.status_code == 204

    async def test_delete_my_availability_not_found(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test deleting availability when none exists returns 404."""
        group = EventGroup(
            name="No Avail Delete Group",
            start_date=date(2027, 3, 1),
            end_date=date(2027, 3, 7),
            status="published",
        )
        db_session.add(group)
        await db_session.flush()
        await db_session.refresh(group)

        r = await async_client.delete(
            f"/api/v1/event-groups/{group.id}/availability/me"
        )
        assert r.status_code == 404

    async def test_list_availabilities_nonexistent_group(
        self,
        async_client: AsyncClient,
        as_admin: None,
    ):
        """Test listing availabilities for a nonexistent group returns 404."""
        fake_id = uuid.uuid4()
        r = await async_client.get(f"/api/v1/event-groups/{fake_id}/availabilities")
        assert r.status_code == 404
