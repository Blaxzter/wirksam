"""What a task's edits do to the shifts it already has (findings #16 and #17).

Saving the details takes a new place to the shifts still showing the old one.
Regenerating updates the shifts it keeps, but only where they still have what
the task or batch gave them: anything someone typed on a shift stays.
"""

import datetime as dt
import uuid
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.event import Event
from app.models.location import Location
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task

pytestmark = pytest.mark.usefixtures("clock_before_fixture_shifts")

DAY = dt.date(2026, 6, 11)
SCHEDULE: dict[str, Any] = {
    "default_start_time": "10:00:00",
    "default_end_time": "14:00:00",
    "shift_duration_minutes": 120,
    "people_per_shift": 1,
}


async def _location(db: AsyncSession, event: Event, name: str) -> Location:
    row = Location(event_id=event.id, name=name)
    db.add(row)
    await db.flush()
    return row


@pytest_asyncio.fixture
async def task(db_session: AsyncSession, test_event: Event) -> Task:
    row = Task(
        name="Bar",
        start_date=DAY,
        end_date=DAY,
        status="published",
        location="Zelt",
        category="Getränke",
        event_id=test_event.id,
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _shift(
    db: AsyncSession,
    task: Task,
    *,
    start: int = 10,
    title: str | None = None,
    location: str | None = "Zelt",
    location_id: uuid.UUID | None = None,
    category: str | None = "Getränke",
    batch_id: uuid.UUID | None = None,
) -> Shift:
    row = Shift(
        task_id=task.id,
        batch_id=batch_id,
        title=title or f"Bar {start}:00-{start + 2}:00",
        date=DAY,
        start_time=dt.time(start, 0),
        end_time=dt.time(start + 2, 0),
        location=location,
        location_id=location_id,
        category=category,
        max_bookings=1,
    )
    db.add(row)
    await db.flush()
    return row


async def _reload(db: AsyncSession, *rows: Any) -> None:
    for row in rows:
        await db.refresh(row)


@pytest.mark.asyncio
class TestSavingAPlaceReachesTheShifts:
    async def _patch(
        self, client: AsyncClient, task: Task, **body: Any
    ) -> dict[str, Any]:
        r = await client.patch(f"/api/v1/tasks/{task.id}", json=body)
        assert r.status_code == 200, r.text
        return r.json()

    async def test_a_typed_place_reaches_the_shifts_that_still_have_the_old_one(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        task: Task,
    ) -> None:
        follows = await _shift(db_session, task, start=10)
        own = await _shift(db_session, task, start=12, location="Bühne")

        await self._patch(async_client, task, location="Halle")

        await _reload(db_session, follows, own)
        assert follows.location == "Halle"
        assert own.location == "Bühne"

    async def test_a_location_from_the_list_links_them_too(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event: Event,
        task: Task,
    ) -> None:
        foyer = await _location(db_session, test_event, "Foyer")
        follows = await _shift(db_session, task)

        await self._patch(async_client, task, location_id=str(foyer.id))

        await _reload(db_session, follows)
        assert (follows.location, follows.location_id) == ("Foyer", foyer.id)

    async def test_leaving_the_list_unlinks_them(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event: Event,
        task: Task,
    ) -> None:
        foyer = await _location(db_session, test_event, "Foyer")
        task.location, task.location_id = "Foyer", foyer.id
        db_session.add(task)
        await db_session.flush()
        follows = await _shift(db_session, task, location="Foyer", location_id=foyer.id)

        await self._patch(async_client, task, location_id=None, location="Halle")

        await _reload(db_session, follows)
        assert (follows.location, follows.location_id) == ("Halle", None)

    async def test_clearing_the_place_clears_it_on_those_shifts(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        task: Task,
    ) -> None:
        follows = await _shift(db_session, task, start=10)
        own = await _shift(db_session, task, start=12, location="Bühne")

        await self._patch(async_client, task, location=None)

        await _reload(db_session, follows, own)
        assert follows.location is None
        assert own.location == "Bühne"

    async def test_a_first_place_reaches_shifts_without_one(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        task: Task,
    ) -> None:
        task.location = None
        db_session.add(task)
        await db_session.flush()
        without = await _shift(db_session, task, start=10, location=None)
        own = await _shift(db_session, task, start=12, location="Bühne")

        await self._patch(async_client, task, location="Halle")

        await _reload(db_session, without, own)
        assert without.location == "Halle"
        assert own.location == "Bühne"

    async def test_a_link_to_another_location_of_the_same_name_is_its_own_place(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event: Event,
        task: Task,
    ) -> None:
        other = await _location(db_session, test_event, "Zelt")
        linked = await _shift(db_session, task, location="Zelt", location_id=other.id)

        await self._patch(async_client, task, location="Halle")

        await _reload(db_session, linked)
        assert (linked.location, linked.location_id) == ("Zelt", other.id)

    async def test_saving_without_changing_the_place_touches_nothing(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        task: Task,
    ) -> None:
        """The edit form always sends the place along with the name."""
        own = await _shift(db_session, task, location="Bühne")

        await self._patch(async_client, task, name="Theke", location="Zelt")

        await _reload(db_session, own)
        assert own.location == "Bühne"

    async def test_a_batch_with_the_old_place_follows_and_one_of_its_own_stays(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        task: Task,
    ) -> None:
        """A batch is what its later shifts are generated from."""
        follows = ShiftBatch(
            task_id=task.id,
            label="Bar",
            start_date=DAY,
            end_date=DAY,
            location="Zelt",
            default_start_time=dt.time(10, 0),
            default_end_time=dt.time(14, 0),
            shift_duration_minutes=120,
            people_per_shift=1,
        )
        own = ShiftBatch(
            task_id=task.id,
            label="Bühne",
            start_date=DAY,
            end_date=DAY,
            location="Bühne",
            default_start_time=dt.time(10, 0),
            default_end_time=dt.time(14, 0),
            shift_duration_minutes=120,
            people_per_shift=1,
        )
        db_session.add_all([follows, own])
        await db_session.flush()

        await self._patch(async_client, task, location="Halle")

        await _reload(db_session, follows, own)
        assert follows.location == "Halle"
        assert own.location == "Bühne"

    async def test_moving_to_another_event_keeps_the_text_and_drops_the_link(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_event: Event,
        test_private_event: Event,
        task: Task,
    ) -> None:
        foyer = await _location(db_session, test_event, "Foyer")
        task.location, task.location_id = "Foyer", foyer.id
        db_session.add(task)
        await db_session.flush()
        shift = await _shift(db_session, task, location="Foyer", location_id=foyer.id)
        own = await _shift(db_session, task, start=12, location="Bühne")

        await self._patch(async_client, task, event_id=str(test_private_event.id))

        await _reload(db_session, shift, own)
        assert (shift.location, shift.location_id) == ("Foyer", None)
        assert own.location == "Bühne"


@pytest.mark.asyncio
class TestRegeneratingKeepsWhatWasTyped:
    async def _regenerate(
        self,
        client: AsyncClient,
        task: Task,
        *,
        batch_id: uuid.UUID | None = None,
        **body: Any,
    ) -> dict[str, Any]:
        r = await client.post(
            f"/api/v1/tasks/{task.id}/regenerate-shifts",
            params={"batch_id": str(batch_id)} if batch_id else None,
            json={"schedule": SCHEDULE, **body},
        )
        assert r.status_code == 200, r.text
        return r.json()

    async def test_without_any_change_a_typed_shift_stays_as_it_was(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        task: Task,
    ) -> None:
        typed = await _shift(
            db_session,
            task,
            title="Spätschicht mit Kasse",
            location="Bühne",
            category="Kasse",
        )

        data = await self._regenerate(async_client, task)

        assert data["shifts_kept"] == 1
        await _reload(db_session, typed)
        assert typed.title == "Spätschicht mit Kasse"
        assert typed.location == "Bühne"
        assert typed.category == "Kasse"

    async def test_a_rename_reaches_generated_titles_only(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        task: Task,
    ) -> None:
        generated = await _shift(db_session, task, start=10, title="Bar 10:00-12:00")
        typed = await _shift(db_session, task, start=12, title="Spätschicht")

        await self._regenerate(async_client, task, name="Theke")

        await _reload(db_session, generated, typed)
        assert generated.title == "Theke 10:00-12:00"
        assert typed.title == "Spätschicht"

    async def test_a_new_place_reaches_the_shifts_that_still_have_the_old_one(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        task: Task,
    ) -> None:
        follows = await _shift(db_session, task, start=10)
        own = await _shift(db_session, task, start=12, location="Bühne")

        await self._regenerate(async_client, task, location="Halle")

        await _reload(db_session, follows, own)
        assert follows.location == "Halle"
        assert own.location == "Bühne"

    async def test_a_new_category_reaches_the_shifts_that_still_have_the_old_one(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        task: Task,
    ) -> None:
        follows = await _shift(db_session, task, start=10)
        own = await _shift(db_session, task, start=12, category="Kasse")

        await self._regenerate(async_client, task, category="Essen")

        await _reload(db_session, follows, own)
        assert follows.category == "Essen"
        assert own.category == "Kasse"

    async def test_the_number_of_places_comes_from_the_schedule(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        task: Task,
    ) -> None:
        shift = await _shift(db_session, task)

        await self._regenerate(
            async_client, task, schedule={**SCHEDULE, "people_per_shift": 4}
        )

        await _reload(db_session, shift)
        assert shift.max_bookings == 4

    async def test_a_batch_compares_with_the_batchs_own_values(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        task: Task,
    ) -> None:
        batch = ShiftBatch(
            task_id=task.id,
            label="Bühne",
            start_date=DAY,
            end_date=DAY,
            location="Bühne",
            category="Technik",
            default_start_time=dt.time(10, 0),
            default_end_time=dt.time(14, 0),
            shift_duration_minutes=120,
            people_per_shift=1,
        )
        db_session.add(batch)
        await db_session.flush()
        follows = await _shift(
            db_session,
            task,
            start=10,
            batch_id=batch.id,
            location="Bühne",
            category="Technik",
        )
        own = await _shift(
            db_session,
            task,
            start=12,
            batch_id=batch.id,
            location="Zelt",
            category="Getränke",
        )

        await self._regenerate(
            async_client, task, batch_id=batch.id, location="Halle", category="Licht"
        )

        await _reload(db_session, follows, own)
        assert (follows.location, follows.category) == ("Halle", "Licht")
        assert (own.location, own.category) == ("Zelt", "Getränke")

    async def test_a_batch_with_the_tasks_old_place_follows_a_whole_task_regenerate(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        task: Task,
    ) -> None:
        batch = ShiftBatch(
            task_id=task.id,
            label="Bar",
            start_date=DAY,
            end_date=DAY,
            location="Zelt",
            default_start_time=dt.time(10, 0),
            default_end_time=dt.time(14, 0),
            shift_duration_minutes=120,
            people_per_shift=1,
        )
        db_session.add(batch)
        await db_session.flush()

        await self._regenerate(async_client, task, location="Halle")

        await _reload(db_session, batch)
        assert batch.location == "Halle"

    async def test_the_dry_run_changes_nothing(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        task: Task,
    ) -> None:
        shift = await _shift(db_session, task)

        r = await async_client.post(
            f"/api/v1/tasks/{task.id}/regenerate-shifts",
            params={"dry_run": True},
            json={"schedule": SCHEDULE, "name": "Theke", "location": "Halle"},
        )

        assert r.status_code == 200, r.text
        await _reload(db_session, shift)
        assert shift.title == "Bar 10:00-12:00"
        assert shift.location == "Zelt"


@pytest.mark.asyncio
@pytest.mark.usefixtures("as_event_admin")
async def test_only_the_shifts_of_this_task_are_touched(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_event: Event,
    task: Task,
) -> None:
    other = Task(
        name="Grill",
        start_date=DAY,
        end_date=DAY,
        status="published",
        location="Zelt",
        event_id=test_event.id,
    )
    db_session.add(other)
    await db_session.flush()
    elsewhere = await _shift(db_session, other)

    r = await async_client.patch(f"/api/v1/tasks/{task.id}", json={"location": "Halle"})

    assert r.status_code == 200, r.text
    rows = await db_session.execute(
        select(col(Shift.location)).where(col(Shift.id) == elsewhere.id)
    )
    assert rows.scalar_one() == "Zelt"
