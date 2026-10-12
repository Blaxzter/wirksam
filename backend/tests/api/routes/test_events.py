"""Route tests for Event and UserAvailability endpoints."""

import datetime
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.event_membership import event_membership as crud_membership
from app.models.event import Event
from app.models.location import Location
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User
from app.models.user_availability import UserAvailability
from app.models.venue_plan import VenueMarker, VenuePlan, VenuePlanImage


@pytest.mark.asyncio
class TestEventRoutes:
    """Test suite for /events/ routes."""

    async def test_list_events(self, async_client: AsyncClient, test_event: Event):
        """Test listing events returns published groups for normal users."""
        r = await async_client.get("/api/v1/events/")

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert any(item["name"] == test_event.name for item in data["items"])

    async def test_list_events_returns_only_my_events(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_draft_event: Event,
        test_private_event: Event,
    ):
        """The default scope is the caller's own events, drafts included.

        Membership replaced publication status as the boundary: a member
        helping to plan an event sees it before it goes live, and an event
        they are not in never appears at all.
        """
        r = await async_client.get("/api/v1/events/")

        assert r.status_code == 200
        names = [item["name"] for item in r.json()["items"]]
        assert test_event.name in names
        assert test_draft_event.name in names
        assert test_private_event.name not in names

    async def test_discover_scope_excludes_events_i_am_in(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_private_event: Event,
    ):
        """Discover offers public events the caller could still join."""
        r = await async_client.get("/api/v1/events/?scope=discover")

        assert r.status_code == 200
        names = [item["name"] for item in r.json()["items"]]
        assert test_event.name not in names, "already a member"
        assert test_private_event.name not in names, "private stays hidden"

    async def test_scope_all_is_downgraded_for_non_superadmin(
        self,
        async_client: AsyncClient,
        test_private_event: Event,
    ):
        """Asking for everything must not become a way to see everything."""
        r = await async_client.get("/api/v1/events/?scope=all")

        assert r.status_code == 200
        names = [item["name"] for item in r.json()["items"]]
        assert test_private_event.name not in names

    async def test_list_events_admin_sees_all(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_draft_event: Event,
        as_admin: None,
    ):
        """Test that admins can see all groups including drafts."""
        r = await async_client.get("/api/v1/events/")

        assert r.status_code == 200
        names = [item["name"] for item in r.json()["items"]]
        assert test_event.name in names
        assert test_draft_event.name in names

    async def test_get_event(self, async_client: AsyncClient, test_event: Event):
        """Test getting a single published event."""
        r = await async_client.get(f"/api/v1/events/{test_event.id}")

        assert r.status_code == 200
        assert r.json()["name"] == test_event.name
        assert r.json()["status"] == "published"

    async def test_draft_event_visible_to_its_members(
        self, async_client: AsyncClient, test_draft_event: Event
    ):
        """A member may open their own event while it is still a draft."""
        r = await async_client.get(f"/api/v1/events/{test_draft_event.id}")

        assert r.status_code == 200
        assert r.json()["my_role"] == "member"

    async def test_private_event_is_404_for_non_members(
        self, async_client: AsyncClient, test_private_event: Event
    ):
        """A stranger gets 404, not 403.

        403 would confirm the event exists, letting anyone probe for private
        events by id.
        """
        r = await async_client.get(f"/api/v1/events/{test_private_event.id}")

        assert r.status_code == 404

    async def test_draft_event_accessible_to_admin(
        self,
        async_client: AsyncClient,
        test_draft_event: Event,
        as_admin: None,
    ):
        """Test that an admin can access a draft event."""
        r = await async_client.get(f"/api/v1/events/{test_draft_event.id}")

        assert r.status_code == 200
        assert r.json()["status"] == "draft"

    async def test_get_nonexistent_event(self, async_client: AsyncClient):
        """Test getting a non-existent event returns 404."""
        import uuid

        r = await async_client.get(f"/api/v1/events/{uuid.uuid4()}")
        assert r.status_code == 404

    async def test_create_event_as_admin(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test that an admin can create an event."""
        r = await async_client.post(
            "/api/v1/events/",
            json={
                "name": "Neue Gruppe",
                "start_date": "2026-08-01",
                "end_date": "2026-08-07",
            },
        )

        assert r.status_code == 201
        assert r.json()["name"] == "Neue Gruppe"
        assert r.json()["status"] == "draft"

    async def test_update_event_as_admin(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_admin: None,
    ):
        """Test that an admin can update an event."""
        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}",
            json={"name": "Renamed Group"},
        )

        assert r.status_code == 200
        assert r.json()["name"] == "Renamed Group"

    async def test_delete_event_as_admin(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_admin: None,
    ):
        """Test that an admin can delete an event."""
        r = await async_client.delete(f"/api/v1/events/{test_event.id}")
        assert r.status_code == 204

    async def test_search_events(self, async_client: AsyncClient, test_event: Event):
        """Test searching events by name."""
        r = await async_client.get("/api/v1/events/", params={"search": "Kirchentags"})

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert any(item["name"] == test_event.name for item in data["items"])


@pytest.mark.asyncio
class TestAvailabilityRoutes:
    """Test suite for /events/{id}/availability routes."""

    async def test_set_availability_fully_available(
        self, async_client: AsyncClient, test_event: Event
    ):
        """Test registering as fully available."""
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/availability",
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
        self, async_client: AsyncClient, test_event: Event
    ):
        """Test registering availability on specific dates."""
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/availability",
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
        test_event: Event,
        test_user_availability: UserAvailability,
    ):
        """Test that posting again updates the existing availability record."""
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/availability",
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
        test_event: Event,
        test_user_availability: UserAvailability,
    ):
        """Test retrieving the current user's availability."""
        r = await async_client.get(f"/api/v1/events/{test_event.id}/availability/me")

        assert r.status_code == 200
        assert r.json()["availability_type"] == test_user_availability.availability_type
        assert r.json()["user_id"] == str(test_user_availability.user_id)

    async def test_get_my_availability_not_found(
        self, async_client: AsyncClient, test_event: Event
    ):
        """Test that 404 is returned when no availability is registered."""
        r = await async_client.get(f"/api/v1/events/{test_event.id}/availability/me")
        assert r.status_code == 404

    async def test_delete_my_availability(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_user_availability: UserAvailability,
    ):
        """Test removing own availability."""
        r = await async_client.delete(f"/api/v1/events/{test_event.id}/availability/me")
        assert r.status_code == 204

        # Confirm it's gone
        r2 = await async_client.get(f"/api/v1/events/{test_event.id}/availability/me")
        assert r2.status_code == 404

    async def test_delete_my_availability_not_found(
        self, async_client: AsyncClient, test_event: Event
    ):
        """Test that deleting non-existent availability returns 404."""
        r = await async_client.delete(f"/api/v1/events/{test_event.id}/availability/me")
        assert r.status_code == 404

    async def test_list_availabilities_as_admin(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_user_availability: UserAvailability,
        as_admin: None,
    ):
        """Test admin can list all availabilities for a group."""
        r = await async_client.get(f"/api/v1/events/{test_event.id}/availabilities")

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
            f"/api/v1/events/{uuid.uuid4()}/availability",
            json={"availability_type": "fully_available", "dates": []},
        )
        assert r.status_code == 404

    async def test_availability_with_dates_returned(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_user_availability_with_dates: UserAvailability,
    ):
        """Test that specific-date availability includes date entries in response."""
        r = await async_client.get(f"/api/v1/events/{test_event.id}/availability/me")

        assert r.status_code == 200
        data = r.json()
        assert data["availability_type"] == "specific_dates"
        assert len(data["available_dates"]) == 2
        dates = {d["slot_date"] for d in data["available_dates"]}
        assert "2026-06-10" in dates
        assert "2026-06-11" in dates


@pytest.mark.asyncio
class TestEventSelfService:
    """Any signed-in user can run their own event."""

    async def test_create_event_as_event_admin(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
    ):
        """Test that an event admin can create a further event."""
        r = await async_client.post(
            "/api/v1/events/",
            json={
                "name": "Manager Group",
                "start_date": "2026-09-01",
                "end_date": "2026-09-07",
            },
        )

        assert r.status_code == 201
        assert r.json()["name"] == "Manager Group"

    async def test_plain_user_can_create_an_event_and_owns_it(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """The headline of the refactor: no gatekeeper stands in the way.

        Creating an event also seeds the owner membership, so the creator can
        immediately manage what they just made.
        """
        r = await async_client.post(
            "/api/v1/events/",
            json={
                "name": "My Own Event",
                "start_date": "2026-09-01",
                "end_date": "2026-09-07",
            },
        )

        assert r.status_code == 201
        body = r.json()
        assert body["my_role"] == "owner"
        assert body["can_manage"] is True
        assert body["member_count"] == 1

        role = await crud_membership.get_role(
            db_session, user_id=test_user.id, event_id=uuid.UUID(body["id"])
        )
        assert role == "owner"

    async def test_new_events_are_private_by_default(
        self,
        async_client: AsyncClient,
    ):
        """An event should not be discoverable until its owner says so."""
        r = await async_client.post(
            "/api/v1/events/",
            json={
                "name": "Quiet Event",
                "start_date": "2026-09-01",
                "end_date": "2026-09-07",
            },
        )

        assert r.status_code == 201
        assert r.json()["visibility"] == "private"

    async def test_update_event_as_event_admin(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_event_admin: None,
    ):
        """An event admin can edit the event they run."""
        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}",
            json={"name": "Updated by Manager"},
        )

        assert r.status_code == 200
        assert r.json()["name"] == "Updated by Manager"

    async def test_update_event_as_normal_user_raises_403(
        self,
        async_client: AsyncClient,
        test_event: Event,
    ):
        """Test that a plain user cannot update events."""
        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}",
            json={"name": "Should Fail"},
        )

        assert r.status_code == 403

    async def test_delete_event_as_event_admin_is_refused(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_event_admin: None,
    ):
        """Deleting is owner-only, deliberately stricter than editing.

        An admin invited to help run an event should not be able to destroy
        the whole thing.
        """
        r = await async_client.delete(f"/api/v1/events/{test_event.id}")

        assert r.status_code == 403

    async def test_delete_event_as_owner(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_admin: None,
    ):
        """The owner (here the superadmin) can delete."""
        r = await async_client.delete(f"/api/v1/events/{test_event.id}")

        assert r.status_code == 204

    async def test_delete_event_as_normal_user_raises_403(
        self,
        async_client: AsyncClient,
        test_event: Event,
    ):
        """Test that a plain user cannot delete events."""
        r = await async_client.delete(f"/api/v1/events/{test_event.id}")

        assert r.status_code == 403

    async def test_list_availabilities_as_event_admin(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_user_availability: UserAvailability,
        as_event_admin: None,
    ):
        """An event admin can see who is available for their event."""
        r = await async_client.get(f"/api/v1/events/{test_event.id}/availabilities")

        assert r.status_code == 200

    async def test_list_availabilities_blocked_for_normal_user(
        self,
        async_client: AsyncClient,
        test_event: Event,
    ):
        """A plain member cannot see the whole roster of availabilities."""
        r = await async_client.get(f"/api/v1/events/{test_event.id}/availabilities")

        assert r.status_code == 403


async def _location_graph(
    db: AsyncSession, *, event: Event, location: Location, creator: User
) -> tuple[Task, ShiftBatch, Shift]:
    """A task, batch and shift on ``event`` that all point at ``location``."""
    task = Task(
        name="Garderobe",
        start_date=datetime.date(2026, 6, 11),
        end_date=datetime.date(2026, 6, 11),
        status="published",
        created_by_id=creator.id,
        event_id=event.id,
        location=location.name,
        location_id=location.id,
    )
    db.add(task)
    await db.flush()
    batch = ShiftBatch(
        task_id=task.id,
        start_date=task.start_date,
        end_date=task.end_date,
        location=location.name,
        location_id=location.id,
    )
    db.add(batch)
    await db.flush()
    shift = Shift(
        task_id=task.id,
        batch_id=batch.id,
        title="Garderobe 18-20",
        date=task.start_date,
        start_time=datetime.time(18, 0),
        end_time=datetime.time(20, 0),
        location=location.name,
        location_id=location.id,
    )
    db.add(shift)
    await db.flush()
    return task, batch, shift


@pytest.mark.asyncio
class TestEventVenueMap:
    """What the venue map adds to the event read, and to deleting an event."""

    async def test_venue_plan_count_counts_only_plans_with_an_image(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_venue_plan: VenuePlan,
    ):
        # A plan still waiting for its image is editor state, not a map.
        db_session.add(VenuePlan(event_id=test_event.id, name="Draft", sort_order=1))
        await db_session.flush()

        r = await async_client.get(f"/api/v1/events/{test_event.id}")
        assert r.status_code == 200
        assert r.json()["venue_plan_count"] == 1

        r = await async_client.get("/api/v1/events/")
        assert r.status_code == 200
        by_id = {e["id"]: e for e in r.json()["items"]}
        assert by_id[str(test_event.id)]["venue_plan_count"] == 1

    async def test_venue_plan_count_is_hidden_from_non_members(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_venue_plan: VenuePlan,
        as_outsider: None,
    ):
        """The map is member-only, so a visitor of a public event must not be
        told there is one (the nav link would lead to a 404)."""
        r = await async_client.get(f"/api/v1/events/{test_event.id}")
        assert r.status_code == 200
        assert r.json()["venue_plan_count"] == 0

    async def test_venue_plan_count_is_zero_without_plans(
        self,
        async_client: AsyncClient,
        test_event: Event,
    ):
        r = await async_client.get(f"/api/v1/events/{test_event.id}")
        assert r.status_code == 200
        assert r.json()["venue_plan_count"] == 0

    async def test_delete_event_with_a_location_graph(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        test_location: Location,
        test_location_marker: VenueMarker,
        as_admin: None,
    ):
        """Regression for the SET NULL next to the event FK on ``tasks``.

        The task survives with neither an event nor a location, its text
        intact; the locations, plans, image and markers go with the event.
        """
        task, batch, shift = await _location_graph(
            db_session, event=test_event, location=test_location, creator=test_user
        )
        plan_id = test_location_marker.plan_id

        r = await async_client.delete(f"/api/v1/events/{test_event.id}")
        assert r.status_code == 204, r.text
        # ``tasks.location_id`` is checked at commit, which the test transaction
        # never reaches; run the deferred checks now.
        await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

        survivor = await db_session.get(Task, task.id, populate_existing=True)
        assert survivor is not None
        assert (survivor.event_id, survivor.location_id) == (None, None)
        assert survivor.location == "Foyer"
        for row in (batch, shift):
            await db_session.refresh(row)
            assert (row.location_id, row.location) == (None, "Foyer")
        for model, row_id in (
            (Location, test_location.id),
            (VenuePlan, plan_id),
            (VenueMarker, test_location_marker.id),
        ):
            assert await db_session.get(model, row_id, populate_existing=True) is None
        images = await db_session.execute(
            select(func.count())
            .select_from(VenuePlanImage)
            .where(col(VenuePlanImage.plan_id) == plan_id)
        )
        assert images.scalar_one() == 0
