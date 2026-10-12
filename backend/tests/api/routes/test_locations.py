"""Route tests for per-event locations (#182).

Covers the gates (member read, stranger 404, admin-only writes), the
case-insensitive name check, rename propagation to the denormalised
``location`` text, delete semantics, pins and the per-day shift list.
"""

import datetime as dt
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.booking import Booking
from app.models.event import Event
from app.models.location import Location
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User
from app.models.venue_plan import VenueMarker, VenuePlan

DAY = dt.date(2026, 6, 11)


async def _linked_rows(
    session: AsyncSession, event: Event, loc: Location, *, status: str = "published"
) -> tuple[Task, ShiftBatch, Shift]:
    """A task, batch and shift in ``event`` that all point at ``loc``."""
    task = Task(
        name="Garderobe",
        start_date=DAY,
        end_date=DAY,
        status=status,
        event_id=event.id,
        location=loc.name,
        location_id=loc.id,
    )
    session.add(task)
    await session.flush()
    batch = ShiftBatch(
        task_id=task.id,
        start_date=DAY,
        end_date=DAY,
        location=loc.name,
        location_id=loc.id,
    )
    session.add(batch)
    await session.flush()
    shift = Shift(
        task_id=task.id,
        batch_id=batch.id,
        title="Garderobe 10-12",
        date=DAY,
        start_time=dt.time(10, 0),
        end_time=dt.time(12, 0),
        location=loc.name,
        location_id=loc.id,
        max_bookings=2,
    )
    session.add(shift)
    await session.flush()
    return task, batch, shift


@pytest.mark.asyncio
class TestListLocations:
    async def test_member_lists_alphabetically_ignoring_case(
        self, async_client: AsyncClient, db_session: AsyncSession, test_event: Event
    ):
        for name in ("bühne", "Ausgang", "Café"):
            db_session.add(Location(event_id=test_event.id, name=name))
        await db_session.flush()

        r = await async_client.get(f"/api/v1/events/{test_event.id}/locations")

        assert r.status_code == 200
        assert [loc["name"] for loc in r.json()] == ["Ausgang", "bühne", "Café"]

    async def test_stranger_gets_404_on_private_event(
        self,
        async_client: AsyncClient,
        test_private_event: Event,
        as_outsider: None,
    ):
        r = await async_client.get(f"/api/v1/events/{test_private_event.id}/locations")

        assert r.status_code == 404
        assert r.json()["code"] == "event.not_found"

    async def test_stranger_reads_public_published_event(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_location: Location,
        as_outsider: None,
    ):
        r = await async_client.get(f"/api/v1/events/{test_event.id}/locations")

        assert r.status_code == 200
        assert [loc["id"] for loc in r.json()] == [str(test_location.id)]


@pytest.mark.asyncio
class TestCreateLocation:
    async def test_event_admin_creates(
        self, async_client: AsyncClient, test_event: Event, as_event_admin: None
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/locations",
            json={
                "name": "  Bühne  ",
                "description": "Hinter dem **Zelt**",
                "address": "",
                "map_url": "https://maps.example.test/x",
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Bühne"
        assert data["event_id"] == str(test_event.id)
        assert data["description"] == "Hinter dem **Zelt**"
        assert data["address"] is None
        assert data["map_url"] == "https://maps.example.test/x"

    async def test_member_is_forbidden(
        self, async_client: AsyncClient, test_event: Event
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/locations", json={"name": "Bühne"}
        )

        assert r.status_code == 403
        assert r.json()["code"] == "event.forbidden"

    async def test_stranger_gets_404_on_private_event(
        self,
        async_client: AsyncClient,
        test_private_event: Event,
        as_outsider: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_private_event.id}/locations",
            json={"name": "Bühne"},
        )

        assert r.status_code == 404

    async def test_duplicate_name_ignoring_case_is_409(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_location: Location,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/locations",
            json={"name": test_location.name.upper()},
        )

        assert r.status_code == 409
        assert r.json()["code"] == "location.name_taken"

    async def test_lost_race_on_the_unique_constraint_is_409(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_location: Location,
        as_event_admin: None,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Two requests can both pass the pre-check; the loser gets a 409."""

        async def _no_precheck(*_args: object, **_kwargs: object) -> None:
            return None

        monkeypatch.setattr("app.api.routes.locations._ensure_name_free", _no_precheck)

        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/locations",
            json={"name": test_location.name},
        )
        assert r.status_code == 409
        assert r.json()["code"] == "location.name_taken"

        other = await async_client.post(
            f"/api/v1/events/{test_event.id}/locations", json={"name": "Bar"}
        )
        assert other.status_code == 201
        r = await async_client.patch(
            f"/api/v1/locations/{other.json()['id']}",
            json={"name": test_location.name},
        )
        assert r.status_code == 409
        assert r.json()["code"] == "location.name_taken"

    async def test_same_name_in_another_event_is_fine(
        self,
        async_client: AsyncClient,
        test_private_event: Event,
        test_location: Location,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_private_event.id}/locations",
            json={"name": test_location.name},
        )

        assert r.status_code == 201

    @pytest.mark.parametrize(
        "url", ["javascript:alert(1)", "data:text/html,hi", "ftp://x.test", "https://"]
    )
    async def test_map_url_must_be_http(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_event_admin: None,
        url: str,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/locations",
            json={"name": "Bühne", "map_url": url},
        )

        assert r.status_code == 422

    async def test_blank_name_is_422(
        self, async_client: AsyncClient, test_event: Event, as_event_admin: None
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/locations", json={"name": "   "}
        )

        assert r.status_code == 422


@pytest.mark.asyncio
class TestUpdateLocation:
    async def test_rename_propagates_to_task_batch_and_shift(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
        as_event_admin: None,
    ):
        task, batch, shift = await _linked_rows(db_session, test_event, test_location)
        # A row that only carries the same text, without the link, is not
        # touched: it was never "at" this location.
        loose = Task(
            name="Loose",
            start_date=DAY,
            end_date=DAY,
            event_id=test_event.id,
            location=test_location.name,
        )
        db_session.add(loose)
        await db_session.flush()

        r = await async_client.patch(
            f"/api/v1/locations/{test_location.id}", json={"name": "Großes Foyer"}
        )

        assert r.status_code == 200
        assert r.json()["name"] == "Großes Foyer"
        for row in (task, batch, shift, loose):
            await db_session.refresh(row)
        assert task.location == "Großes Foyer"
        assert batch.location == "Großes Foyer"
        assert shift.location == "Großes Foyer"
        assert loose.location == "Foyer"

    async def test_partial_update_keeps_other_fields(
        self,
        async_client: AsyncClient,
        test_location: Location,
        as_event_admin: None,
    ):
        r = await async_client.patch(
            f"/api/v1/locations/{test_location.id}",
            json={"contact": "", "address": "Neue Straße 2"},
        )

        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Foyer"
        assert data["contact"] is None
        assert data["address"] == "Neue Straße 2"
        assert data["description"] == test_location.description

    async def test_case_only_rename_of_itself_is_allowed(
        self,
        async_client: AsyncClient,
        test_location: Location,
        as_event_admin: None,
    ):
        r = await async_client.patch(
            f"/api/v1/locations/{test_location.id}", json={"name": "FOYER"}
        )

        assert r.status_code == 200
        assert r.json()["name"] == "FOYER"

    async def test_rename_onto_another_location_is_409(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
        as_event_admin: None,
    ):
        db_session.add(Location(event_id=test_event.id, name="Bühne"))
        await db_session.flush()

        r = await async_client.patch(
            f"/api/v1/locations/{test_location.id}", json={"name": "bühne"}
        )

        assert r.status_code == 409
        assert r.json()["code"] == "location.name_taken"

    async def test_null_name_is_422(
        self,
        async_client: AsyncClient,
        test_location: Location,
        as_event_admin: None,
    ):
        r = await async_client.patch(
            f"/api/v1/locations/{test_location.id}", json={"name": None}
        )

        assert r.status_code == 422

    async def test_member_is_forbidden(
        self, async_client: AsyncClient, test_location: Location
    ):
        r = await async_client.patch(
            f"/api/v1/locations/{test_location.id}", json={"name": "X"}
        )

        assert r.status_code == 403
        assert r.json()["code"] == "event.forbidden"

    async def test_unknown_location_is_404(
        self, async_client: AsyncClient, as_event_admin: None
    ):
        r = await async_client.patch(
            f"/api/v1/locations/{uuid.uuid4()}", json={"name": "X"}
        )

        assert r.status_code == 404
        assert r.json()["code"] == "location.not_found"


@pytest.mark.asyncio
class TestDeleteLocation:
    async def test_delete_unlinks_rows_keeps_text_and_drops_markers(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
        test_location_marker: VenueMarker,
        as_event_admin: None,
    ):
        task, batch, shift = await _linked_rows(db_session, test_event, test_location)
        marker_id = test_location_marker.id

        r = await async_client.delete(f"/api/v1/locations/{test_location.id}")

        assert r.status_code == 204
        for row in (task, batch, shift):
            await db_session.refresh(row)
            assert row.location_id is None
            assert row.location == "Foyer"
        db_session.expunge(test_location_marker)
        assert await db_session.get(VenueMarker, marker_id) is None
        remaining = await db_session.execute(
            select(func.count())
            .select_from(Location)
            .where(col(Location.event_id) == test_event.id)
        )
        assert remaining.scalar_one() == 0

    async def test_member_is_forbidden(
        self, async_client: AsyncClient, test_location: Location
    ):
        r = await async_client.delete(f"/api/v1/locations/{test_location.id}")

        assert r.status_code == 403

    async def test_stranger_gets_404_on_private_event(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_private_event: Event,
        as_outsider: None,
    ):
        loc = Location(event_id=test_private_event.id, name="Geheim")
        db_session.add(loc)
        await db_session.flush()

        r = await async_client.delete(f"/api/v1/locations/{loc.id}")

        assert r.status_code == 404
        assert r.json()["code"] == "event.not_found"


@pytest.mark.asyncio
class TestLocationDetail:
    async def test_member_sees_pins_in_plan_order(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
        test_venue_plan: VenuePlan,
        test_location_marker: VenueMarker,
    ):
        upstairs = VenuePlan(event_id=test_event.id, name="Upstairs", sort_order=-1)
        db_session.add(upstairs)
        await db_session.flush()
        db_session.add(
            VenueMarker(
                plan_id=upstairs.id,
                location_id=test_location.id,
                kind="location",
                x=0.5,
                y=0.5,
            )
        )
        await db_session.flush()

        r = await async_client.get(f"/api/v1/locations/{test_location.id}")

        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Foyer"
        assert data["description"] == test_location.description
        assert [p["plan_name"] for p in data["pins"]] == ["Upstairs", "Ground floor"]
        pin = data["pins"][1]
        assert pin["marker_id"] == str(test_location_marker.id)
        assert pin["image_etag"] == test_venue_plan.image_etag
        assert (pin["image_width"], pin["image_height"]) == (800, 600)
        assert (pin["x"], pin["y"]) == (0.25, 0.75)

    async def test_public_visitor_gets_no_pins(
        self,
        async_client: AsyncClient,
        test_location: Location,
        test_location_marker: VenueMarker,
        as_outsider: None,
    ):
        r = await async_client.get(f"/api/v1/locations/{test_location.id}")

        assert r.status_code == 200
        assert r.json()["pins"] == []

    async def test_stranger_gets_404_on_private_event(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_private_event: Event,
        as_outsider: None,
    ):
        loc = Location(event_id=test_private_event.id, name="Geheim")
        db_session.add(loc)
        await db_session.flush()

        r = await async_client.get(f"/api/v1/locations/{loc.id}")

        assert r.status_code == 404

    async def test_unknown_is_404(self, async_client: AsyncClient):
        r = await async_client.get(f"/api/v1/locations/{uuid.uuid4()}")

        assert r.status_code == 404
        assert r.json()["code"] == "location.not_found"


@pytest.mark.asyncio
class TestLocationShifts:
    async def _shift(
        self,
        session: AsyncSession,
        task: Task,
        loc: Location | None,
        *,
        day: dt.date = DAY,
        start: dt.time = dt.time(8, 0),
        title: str = "Shift",
    ) -> Shift:
        shift = Shift(
            task_id=task.id,
            title=title,
            date=day,
            start_time=start,
            end_time=dt.time(start.hour + 1, 0),
            location=loc.name if loc else None,
            location_id=loc.id if loc else None,
            max_bookings=3,
        )
        session.add(shift)
        await session.flush()
        return shift

    async def _task(
        self, session: AsyncSession, event: Event, *, status: str = "published"
    ) -> Task:
        task = Task(
            name=f"Task {status}",
            start_date=DAY,
            end_date=DAY,
            status=status,
            event_id=event.id,
        )
        session.add(task)
        await session.flush()
        return task

    async def test_lists_the_day_sorted_with_my_booking(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
        test_user: User,
        test_event_admin_user: User,
    ):
        task = await self._task(db_session, test_event)
        late = await self._shift(
            db_session, task, test_location, start=dt.time(14, 0), title="Late"
        )
        early = await self._shift(
            db_session, task, test_location, start=dt.time(9, 0), title="Early"
        )
        await self._shift(db_session, task, test_location, day=DAY + dt.timedelta(1))
        await self._shift(db_session, task, None)  # no location
        mine = Booking(shift_id=late.id, user_id=test_user.id, status="confirmed")
        db_session.add_all(
            [
                mine,
                Booking(
                    shift_id=late.id,
                    user_id=test_event_admin_user.id,
                    status="confirmed",
                ),
            ]
        )
        await db_session.flush()

        r = await async_client.get(
            f"/api/v1/locations/{test_location.id}/shifts", params={"on": str(DAY)}
        )

        assert r.status_code == 200
        data = r.json()
        assert [s["id"] for s in data] == [str(early.id), str(late.id)]
        assert data[0]["task_name"] == task.name
        assert data[0]["current_bookings"] == 0
        assert data[0]["is_booked_by_me"] is False
        assert data[0]["my_booking_id"] is None
        assert data[1]["current_bookings"] == 2
        assert data[1]["is_booked_by_me"] is True
        assert data[1]["my_booking_id"] == str(mine.id)

    async def test_cancelled_booking_is_not_mine(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
        test_user: User,
    ):
        task = await self._task(db_session, test_event)
        shift = await self._shift(db_session, task, test_location)
        db_session.add(
            Booking(shift_id=shift.id, user_id=test_user.id, status="cancelled")
        )
        await db_session.flush()

        r = await async_client.get(
            f"/api/v1/locations/{test_location.id}/shifts", params={"on": str(DAY)}
        )

        assert r.json()[0]["is_booked_by_me"] is False
        assert r.json()[0]["current_bookings"] == 0

    async def test_draft_shifts_hidden_from_member(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
    ):
        published = await self._task(db_session, test_event)
        draft = await self._task(db_session, test_event, status="draft")
        visible = await self._shift(db_session, published, test_location)
        await self._shift(db_session, draft, test_location)

        r = await async_client.get(
            f"/api/v1/locations/{test_location.id}/shifts", params={"on": str(DAY)}
        )

        assert [s["id"] for s in r.json()] == [str(visible.id)]

    async def test_draft_shifts_shown_to_admin(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
        as_event_admin: None,
    ):
        published = await self._task(db_session, test_event)
        draft = await self._task(db_session, test_event, status="draft")
        await self._shift(db_session, published, test_location)
        await self._shift(db_session, draft, test_location)

        r = await async_client.get(
            f"/api/v1/locations/{test_location.id}/shifts", params={"on": str(DAY)}
        )

        assert len(r.json()) == 2

    async def test_defaults_to_today(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
    ):
        task = await self._task(db_session, test_event)
        today = await self._shift(db_session, task, test_location, day=dt.date.today())
        await self._shift(db_session, task, test_location)

        r = await async_client.get(f"/api/v1/locations/{test_location.id}/shifts")

        assert [s["id"] for s in r.json()] == [str(today.id)]

    async def test_public_visitor_gets_404(
        self,
        async_client: AsyncClient,
        test_location: Location,
        as_outsider: None,
    ):
        r = await async_client.get(f"/api/v1/locations/{test_location.id}/shifts")

        assert r.status_code == 404
        assert r.json()["code"] == "event.not_found"
