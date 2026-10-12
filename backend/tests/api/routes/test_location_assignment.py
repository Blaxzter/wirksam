"""Assigning locations to tasks, batches and shifts (#182).

Every write path that takes ``location`` text also takes ``location_id``. When
an id is given it wins, must belong to the row's event, and its name becomes
the text, so every read path can keep showing ``location`` unchanged.
"""

import datetime as dt
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.event import Event
from app.models.location import Location
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User

SCHEDULE: dict[str, Any] = {
    "default_start_time": "10:00:00",
    "default_end_time": "12:00:00",
    "shift_duration_minutes": 60,
    "people_per_shift": 2,
}


async def _location(session: AsyncSession, event: Event, name: str) -> Location:
    loc = Location(event_id=event.id, name=name)
    session.add(loc)
    await session.flush()
    return loc


async def _shifts(session: AsyncSession, task_id: uuid.UUID | str) -> list[Shift]:
    result = await session.execute(
        select(Shift)
        .where(col(Shift.task_id) == uuid.UUID(str(task_id)))
        .order_by(col(Shift.date), col(Shift.start_time))
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def _batches(session: AsyncSession, task_id: uuid.UUID | str) -> list[ShiftBatch]:
    result = await session.execute(
        select(ShiftBatch)
        .where(col(ShiftBatch.task_id) == uuid.UUID(str(task_id)))
        .order_by(col(ShiftBatch.created_at))
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def _create_with_shifts(
    client: AsyncClient, event: Event, **extra: Any
) -> dict[str, Any]:
    r = await client.post(
        "/api/v1/tasks/with-shifts",
        json={
            "name": "Garderobe",
            "start_date": "2026-06-11",
            "end_date": "2026-06-12",
            "event_id": str(event.id),
            "schedule": SCHEDULE,
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["task"]


@pytest.mark.asyncio
class TestCreateWithShifts:
    async def test_location_id_reaches_task_batch_and_every_shift(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
        as_event_admin: None,
    ):
        task = await _create_with_shifts(
            async_client,
            test_event,
            location="ignored text",
            location_id=str(test_location.id),
        )

        assert task["location_id"] == str(test_location.id)
        assert task["location"] == "Foyer"
        [batch] = await _batches(db_session, task["id"])
        assert batch.location_id == test_location.id
        assert batch.location == "Foyer"
        shifts = await _shifts(db_session, task["id"])
        assert len(shifts) == 4
        assert {(s.location_id, s.location) for s in shifts} == {
            (test_location.id, "Foyer")
        }

    async def test_free_text_only_stays_free(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        as_event_admin: None,
    ):
        task = await _create_with_shifts(async_client, test_event, location="Halle A")

        assert task["location_id"] is None
        assert task["location"] == "Halle A"
        shifts = await _shifts(db_session, task["id"])
        assert {(s.location_id, s.location) for s in shifts} == {(None, "Halle A")}

    async def test_location_of_another_event_is_422(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_private_event: Event,
        as_event_admin: None,
    ):
        foreign = await _location(db_session, test_private_event, "Elsewhere")

        r = await async_client.post(
            "/api/v1/tasks/with-shifts",
            json={
                "name": "Garderobe",
                "start_date": "2026-06-11",
                "end_date": "2026-06-11",
                "event_id": str(test_event.id),
                "location_id": str(foreign.id),
                "schedule": SCHEDULE,
            },
        )

        assert r.status_code == 422
        assert r.json()["code"] == "location.wrong_event"

    async def test_unknown_location_is_422(
        self, async_client: AsyncClient, test_event: Event, as_event_admin: None
    ):
        r = await async_client.post(
            "/api/v1/tasks/with-shifts",
            json={
                "name": "Garderobe",
                "start_date": "2026-06-11",
                "end_date": "2026-06-11",
                "event_id": str(test_event.id),
                "location_id": str(uuid.uuid4()),
                "schedule": SCHEDULE,
            },
        )

        assert r.status_code == 422
        assert r.json()["code"] == "location.wrong_event"

    async def test_inline_new_event_cannot_take_a_location(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_location: Location,
        as_admin: None,
    ):
        r = await async_client.post(
            "/api/v1/tasks/with-shifts",
            json={
                "name": "Garderobe",
                "start_date": "2026-06-11",
                "end_date": "2026-06-11",
                "new_event": {
                    "name": "Brand new",
                    "start_date": "2026-06-11",
                    "end_date": "2026-06-11",
                },
                "location_id": str(test_location.id),
                "schedule": SCHEDULE,
            },
        )

        assert r.status_code == 422
        assert r.json()["code"] == "location.wrong_event"
        created = await db_session.execute(
            select(func.count())
            .select_from(Event)
            .where(col(Event.name) == "Brand new")
        )
        assert created.scalar_one() == 0


@pytest.mark.asyncio
class TestAddShifts:
    async def test_location_name_becomes_the_batch_label(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_location: Location,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/tasks/{test_task.id}/add-shifts",
            json={
                "start_date": "2026-06-12",
                "end_date": "2026-06-12",
                "location": "stale text",
                "location_id": str(test_location.id),
                "category": "Service",
                "schedule": SCHEDULE,
            },
        )

        assert r.status_code == 201, r.text
        [batch] = await _batches(db_session, test_task.id)
        assert batch.label == "Foyer"
        assert batch.location == "Foyer"
        assert batch.location_id == test_location.id
        shifts = await _shifts(db_session, test_task.id)
        assert len(shifts) == 2
        assert {(s.location_id, s.location) for s in shifts} == {
            (test_location.id, "Foyer")
        }
        # The task's own location is not touched by adding a batch.
        assert r.json()["task"]["location_id"] is None

    async def test_foreign_location_is_422(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_private_event: Event,
        as_event_admin: None,
    ):
        foreign = await _location(db_session, test_private_event, "Elsewhere")

        r = await async_client.post(
            f"/api/v1/tasks/{test_task.id}/add-shifts",
            json={
                "start_date": "2026-06-12",
                "end_date": "2026-06-12",
                "location_id": str(foreign.id),
                "schedule": SCHEDULE,
            },
        )

        assert r.status_code == 422
        assert r.json()["code"] == "location.wrong_event"


@pytest.mark.asyncio
class TestRegenerate:
    async def _regenerate(
        self,
        client: AsyncClient,
        task_id: str,
        *,
        batch_id: uuid.UUID | None = None,
        **body: Any,
    ) -> dict[str, Any]:
        params = {"batch_id": str(batch_id)} if batch_id else None
        r = await client.post(
            f"/api/v1/tasks/{task_id}/regenerate-shifts",
            params=params,
            json={"schedule": SCHEDULE, **body},
        )
        assert r.status_code == 200, r.text
        return r.json()

    async def test_omitted_location_id_is_kept(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
        as_event_admin: None,
    ):
        task = await _create_with_shifts(
            async_client, test_event, location_id=str(test_location.id)
        )

        data = await self._regenerate(
            async_client,
            task["id"],
            schedule={**SCHEDULE, "default_end_time": "13:00:00"},
        )

        assert data["shifts_kept"] == 4
        assert data["shifts_added"] == 2
        assert data["task"]["location_id"] == str(test_location.id)
        shifts = await _shifts(db_session, task["id"])
        assert len(shifts) == 6
        assert {(s.location_id, s.location) for s in shifts} == {
            (test_location.id, "Foyer")
        }

    async def test_explicit_null_unlinks_and_keeps_text(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
        as_event_admin: None,
    ):
        task = await _create_with_shifts(
            async_client, test_event, location_id=str(test_location.id)
        )

        data = await self._regenerate(async_client, task["id"], location_id=None)

        assert data["task"]["location_id"] is None
        assert data["task"]["location"] == "Foyer"
        shifts = await _shifts(db_session, task["id"])
        assert {(s.location_id, s.location) for s in shifts} == {(None, "Foyer")}

    async def test_new_id_is_applied_to_existing_shifts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
        as_event_admin: None,
    ):
        stage = await _location(db_session, test_event, "Bühne")
        task = await _create_with_shifts(
            async_client, test_event, location_id=str(test_location.id)
        )
        before = {s.id for s in await _shifts(db_session, task["id"])}

        data = await self._regenerate(
            async_client, task["id"], location_id=str(stage.id)
        )

        assert data["shifts_kept"] == 4
        assert data["task"]["location_id"] == str(stage.id)
        assert data["task"]["location"] == "Bühne"
        shifts = await _shifts(db_session, task["id"])
        assert {s.id for s in shifts} == before
        assert {(s.location_id, s.location) for s in shifts} == {(stage.id, "Bühne")}

    async def test_new_free_text_drops_the_link(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
        as_event_admin: None,
    ):
        task = await _create_with_shifts(
            async_client, test_event, location_id=str(test_location.id)
        )

        data = await self._regenerate(async_client, task["id"], location="Garten")

        assert data["task"]["location_id"] is None
        assert data["task"]["location"] == "Garten"
        shifts = await _shifts(db_session, task["id"])
        assert {(s.location_id, s.location) for s in shifts} == {(None, "Garten")}

    async def test_batch_scoped_keeps_and_applies_on_the_batch(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
        as_event_admin: None,
    ):
        stage = await _location(db_session, test_event, "Bühne")
        task = await _create_with_shifts(
            async_client, test_event, location_id=str(test_location.id)
        )
        [batch] = await _batches(db_session, task["id"])

        # Omitted: the batch's link is kept.
        await self._regenerate(async_client, task["id"], batch_id=batch.id)
        [batch] = await _batches(db_session, task["id"])
        assert batch.location_id == test_location.id

        # Given: applied to the batch and its shifts; the task stays as it was.
        data = await self._regenerate(
            async_client, task["id"], batch_id=batch.id, location_id=str(stage.id)
        )
        [batch] = await _batches(db_session, task["id"])
        assert (batch.location_id, batch.location) == (stage.id, "Bühne")
        shifts = await _shifts(db_session, task["id"])
        assert {s.location_id for s in shifts} == {stage.id}
        assert data["task"]["location_id"] == str(test_location.id)

    async def test_foreign_location_is_422(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_private_event: Event,
        as_event_admin: None,
    ):
        foreign = await _location(db_session, test_private_event, "Elsewhere")
        task = await _create_with_shifts(async_client, test_event)

        r = await async_client.post(
            f"/api/v1/tasks/{task['id']}/regenerate-shifts",
            json={"schedule": SCHEDULE, "location_id": str(foreign.id)},
        )

        assert r.status_code == 422
        assert r.json()["code"] == "location.wrong_event"


@pytest.mark.asyncio
class TestCreateTask:
    async def test_location_id_sets_the_name(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_location: Location,
        as_event_admin: None,
    ):
        r = await async_client.post(
            "/api/v1/tasks/",
            json={
                "name": "Garderobe",
                "start_date": "2026-06-11",
                "end_date": "2026-06-11",
                "event_id": str(test_event.id),
                "location_id": str(test_location.id),
            },
        )

        assert r.status_code == 201, r.text
        assert r.json()["location_id"] == str(test_location.id)
        assert r.json()["location"] == "Foyer"

    async def test_foreign_location_is_422(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_private_event: Event,
        as_event_admin: None,
    ):
        foreign = await _location(db_session, test_private_event, "Elsewhere")

        r = await async_client.post(
            "/api/v1/tasks/",
            json={
                "name": "Garderobe",
                "start_date": "2026-06-11",
                "end_date": "2026-06-11",
                "event_id": str(test_event.id),
                "location_id": str(foreign.id),
            },
        )

        assert r.status_code == 422
        assert r.json()["code"] == "location.wrong_event"


@pytest.mark.asyncio
class TestPatchTask:
    async def test_set_then_clear(
        self,
        async_client: AsyncClient,
        test_task: Task,
        test_location: Location,
        as_event_admin: None,
    ):
        r = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}",
            json={"location_id": str(test_location.id)},
        )
        assert r.status_code == 200, r.text
        assert r.json()["location_id"] == str(test_location.id)
        assert r.json()["location"] == "Foyer"

        r = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}", json={"location_id": None}
        )
        assert r.status_code == 200
        assert r.json()["location_id"] is None
        assert r.json()["location"] == "Foyer"

    async def test_clear_with_new_text(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_location: Location,
        as_event_admin: None,
    ):
        test_task.location_id = test_location.id
        test_task.location = test_location.name
        await db_session.flush()

        r = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}",
            json={"location_id": None, "location": "Garten"},
        )

        assert r.json()["location_id"] is None
        assert r.json()["location"] == "Garten"

    async def test_text_only_change_drops_the_link(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_location: Location,
        as_event_admin: None,
    ):
        test_task.location_id = test_location.id
        test_task.location = test_location.name
        await db_session.flush()

        same = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}", json={"location": "Foyer"}
        )
        assert same.json()["location_id"] == str(test_location.id)

        r = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}", json={"location": "Garten"}
        )
        assert r.json()["location_id"] is None
        assert r.json()["location"] == "Garten"

    async def test_unrelated_patch_keeps_the_link(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_location: Location,
        as_event_admin: None,
    ):
        test_task.location_id = test_location.id
        test_task.location = test_location.name
        await db_session.flush()

        r = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}", json={"name": "Renamed"}
        )

        assert r.json()["location_id"] == str(test_location.id)
        assert r.json()["location"] == "Foyer"

    async def test_moving_to_another_event_drops_the_link(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_location: Location,
        test_private_event: Event,
        as_admin: None,
    ):
        test_task.location_id = test_location.id
        test_task.location = test_location.name
        await db_session.flush()

        r = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}",
            json={"event_id": str(test_private_event.id)},
        )

        assert r.status_code == 200
        assert r.json()["location_id"] is None
        assert r.json()["location"] == "Foyer"

    async def test_moving_unlinks_batches_and_shifts_too(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_private_event: Event,
        as_admin: None,
    ):
        """Regression: the children used to keep the old event's location, so
        renaming it there rewrote rows that now belong to the other event."""
        loc = await _location(db_session, test_event, "Foyer")
        task = await _create_with_shifts(
            async_client, test_event, location_id=str(loc.id)
        )

        r = await async_client.patch(
            f"/api/v1/tasks/{task['id']}",
            json={"event_id": str(test_private_event.id)},
        )
        assert r.status_code == 200, r.text

        r = await async_client.patch(
            f"/api/v1/locations/{loc.id}", json={"name": "Bar"}
        )
        assert r.status_code == 200, r.text

        rows = [*await _batches(db_session, task["id"])]
        rows += await _shifts(db_session, task["id"])
        assert rows
        for row in rows:
            assert row.location_id is None
            assert row.location == "Foyer"

    async def test_moving_into_an_event_without_a_role_is_refused(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_admin_user: User,
        as_event_admin: None,
    ):
        other = Event(
            name="Not mine",
            start_date=dt.date(2026, 6, 1),
            end_date=dt.date(2026, 6, 2),
            status="published",
            visibility="private",
            created_by_id=test_admin_user.id,
        )
        db_session.add(other)
        await db_session.flush()

        r = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}", json={"event_id": str(other.id)}
        )

        assert r.status_code in (403, 404)
        await db_session.refresh(test_task)
        assert test_task.event_id != other.id

    async def test_foreign_location_is_422(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_private_event: Event,
        as_event_admin: None,
    ):
        foreign = await _location(db_session, test_private_event, "Elsewhere")

        r = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}", json={"location_id": str(foreign.id)}
        )

        assert r.status_code == 422
        assert r.json()["code"] == "location.wrong_event"


@pytest.mark.asyncio
class TestShiftWrites:
    async def test_post_shift_with_location_id(
        self,
        async_client: AsyncClient,
        test_task: Task,
        test_location: Location,
        as_event_admin: None,
    ):
        r = await async_client.post(
            "/api/v1/shifts/",
            json={
                "task_id": str(test_task.id),
                "title": "Extra",
                "date": "2026-06-12",
                "location": "whatever",
                "location_id": str(test_location.id),
            },
        )

        assert r.status_code == 201, r.text
        assert r.json()["location_id"] == str(test_location.id)
        assert r.json()["location"] == "Foyer"

    async def test_post_shift_foreign_location_is_422(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_private_event: Event,
        as_event_admin: None,
    ):
        foreign = await _location(db_session, test_private_event, "Elsewhere")

        r = await async_client.post(
            "/api/v1/shifts/",
            json={
                "task_id": str(test_task.id),
                "title": "Extra",
                "date": "2026-06-12",
                "location_id": str(foreign.id),
            },
        )

        assert r.status_code == 422
        assert r.json()["code"] == "location.wrong_event"

    async def test_patch_shift_set_and_clear(
        self,
        async_client: AsyncClient,
        test_shift: Shift,
        test_location: Location,
        as_event_admin: None,
    ):
        r = await async_client.patch(
            f"/api/v1/shifts/{test_shift.id}",
            json={"location_id": str(test_location.id)},
        )
        assert r.status_code == 200, r.text
        assert r.json()["location_id"] == str(test_location.id)
        assert r.json()["location"] == "Foyer"

        r = await async_client.patch(
            f"/api/v1/shifts/{test_shift.id}", json={"location_id": None}
        )
        assert r.json()["location_id"] is None
        assert r.json()["location"] == "Foyer"

    async def test_patch_shift_text_only_drops_the_link(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shift: Shift,
        test_location: Location,
        as_event_admin: None,
    ):
        test_shift.location_id = test_location.id
        test_shift.location = test_location.name
        await db_session.flush()

        r = await async_client.patch(
            f"/api/v1/shifts/{test_shift.id}", json={"location": "Garten"}
        )

        assert r.json()["location_id"] is None
        assert r.json()["location"] == "Garten"


@pytest.mark.asyncio
class TestFeedFilter:
    async def test_matches_by_task_or_by_shift(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_location: Location,
    ):
        other = await _location(db_session, test_event, "Bühne")

        def task(name: str, loc: Location | None) -> Task:
            return Task(
                name=name,
                start_date=dt.date(2026, 6, 11),
                end_date=dt.date(2026, 6, 12),
                status="published",
                event_id=test_event.id,
                location=loc.name if loc else None,
                location_id=loc.id if loc else None,
            )

        by_task = task("By task", test_location)
        by_shift = task("By shift", other)
        elsewhere = task("Elsewhere", other)
        nowhere = task("Nowhere", None)
        db_session.add_all([by_task, by_shift, elsewhere, nowhere])
        await db_session.flush()
        for t, loc in (
            (by_shift, test_location),
            (by_shift, other),
            (elsewhere, other),
        ):
            db_session.add(
                Shift(
                    task_id=t.id,
                    title="S",
                    date=dt.date(2026, 6, 11),
                    start_time=dt.time(10, 0),
                    end_time=dt.time(11, 0),
                    location=loc.name,
                    location_id=loc.id,
                )
            )
        await db_session.flush()

        params = {"event_id": str(test_event.id), "date_from": "2026-06-01"}
        r = await async_client.get(
            "/api/v1/tasks/feed",
            params={**params, "location_id": str(test_location.id)},
        )

        assert r.status_code == 200, r.text
        data = r.json()
        assert {i["name"] for i in data["items"]} == {"By task", "By shift"}
        assert data["total"] == 2

        unfiltered = await async_client.get("/api/v1/tasks/feed", params=params)
        assert unfiltered.json()["total"] == 4
