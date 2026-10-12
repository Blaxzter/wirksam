"""The location backfill in ``20261012_0001_add_locations_and_venue_map``.

The test database is built by running the migrations on an empty schema, so
the backfill itself never sees a row there. This module seeds the shape a
production database has at upgrade time (free-text ``location`` on tasks,
batches and shifts, ``location_id`` still NULL) and runs exactly the SQL the
upgrade runs, imported from the migration module.
"""

import importlib.util
import uuid
from datetime import date, time
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.event import Event
from app.models.location import Location
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "alembic"
    / "versions"
    / "20261012_0001_add_locations_and_venue_map.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("location_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BACKFILL_SQL: tuple[str, ...] = _load_migration().BACKFILL_SQL


async def _run_backfill(session: AsyncSession) -> None:
    """Run the upgrade's SQL. It bypasses the identity map, so tests reload
    rows with ``populate_existing=True`` before reading them back."""
    for statement in BACKFILL_SQL:
        await session.execute(text(statement))


async def _locations(session: AsyncSession, event_id: uuid.UUID) -> dict[str, Location]:
    result = await session.execute(
        select(Location).where(col(Location.event_id) == event_id)
    )
    return {loc.name: loc for loc in result.scalars().all()}


def _task(event: Event | None, user: User, location: str | None) -> Task:
    return Task(
        name="Backfill",
        start_date=date(2026, 6, 10),
        end_date=date(2026, 6, 12),
        status="published",
        created_by_id=user.id,
        event_id=event.id if event else None,
        location=location,
    )


def _shift(task: Task, location: str | None, batch: ShiftBatch | None = None) -> Shift:
    return Shift(
        task_id=task.id,
        batch_id=batch.id if batch else None,
        title="Slot",
        date=date(2026, 6, 10),
        start_time=time(9, 0),
        end_time=time(10, 0),
        location=location,
    )


@pytest.mark.asyncio
class TestLocationBackfill:
    async def test_creates_one_location_per_trimmed_name_and_links_rows(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_private_event: Event,
        test_user: User,
    ) -> None:
        task = _task(test_event, test_user, "  Foyer ")
        blank_task = _task(test_event, test_user, "   ")
        other_event_task = _task(test_private_event, test_user, "Foyer")
        orphan = _task(None, test_user, "Lost hall")
        db_session.add_all([task, blank_task, other_event_task, orphan])
        await db_session.flush()

        batch = ShiftBatch(
            task_id=task.id,
            start_date=date(2026, 6, 10),
            end_date=date(2026, 6, 12),
            location="Main hall",
        )
        db_session.add(batch)
        await db_session.flush()

        shift_same = _shift(task, "Foyer", batch)
        shift_case = _shift(task, "foyer")
        shift_new = _shift(task, " Garden")
        shift_none = _shift(task, None)
        orphan_shift = _shift(orphan, "Lost hall")
        long_name = "X" * 130
        shift_long = _shift(task, long_name)
        db_session.add_all(
            [shift_same, shift_case, shift_new, shift_none, orphan_shift, shift_long]
        )
        await db_session.flush()

        await _run_backfill(db_session)

        locations = await _locations(db_session, test_event.id)
        # Exact, case-sensitive after trimming: "foyer" is its own location.
        assert set(locations) == {"Foyer", "foyer", "Main hall", "Garden", "X" * 120}

        refreshed = {
            obj.id: await db_session.get(type(obj), obj.id, populate_existing=True)
            for obj in (
                task,
                blank_task,
                orphan,
                batch,
                shift_same,
                shift_case,
                shift_new,
                shift_none,
                orphan_shift,
                shift_long,
            )
        }

        def location_id_of(obj: Task | ShiftBatch | Shift) -> uuid.UUID | None:
            row = refreshed[obj.id]
            assert row is not None
            return row.location_id  # type: ignore[union-attr]

        assert location_id_of(task) == locations["Foyer"].id
        assert location_id_of(batch) == locations["Main hall"].id
        assert location_id_of(shift_same) == locations["Foyer"].id
        assert location_id_of(shift_case) == locations["foyer"].id
        assert location_id_of(shift_new) == locations["Garden"].id
        assert location_id_of(shift_long) == locations["X" * 120].id
        assert location_id_of(blank_task) is None
        assert location_id_of(shift_none) is None

        # The text is not rewritten.
        refreshed_task = refreshed[task.id]
        assert refreshed_task is not None and refreshed_task.location == "  Foyer "

        # Orphans keep their text and get no id.
        assert location_id_of(orphan) is None
        assert location_id_of(orphan_shift) is None
        orphan_names = await db_session.scalars(
            select(col(Location.name)).where(col(Location.name) == "Lost hall")
        )
        assert list(orphan_names) == []

        # Same name in another event is another location.
        other = await _locations(db_session, test_private_event.id)
        assert set(other) == {"Foyer"}
        assert other["Foyer"].id != locations["Foyer"].id
        other_task = await db_session.get(
            Task, other_event_task.id, populate_existing=True
        )
        assert other_task is not None
        assert other_task.location_id == other["Foyer"].id

    async def test_rerunning_is_idempotent(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        task = _task(test_event, test_user, "Foyer")
        db_session.add(task)
        await db_session.flush()
        db_session.add_all([_shift(task, "Foyer"), _shift(task, "Garden")])
        await db_session.flush()

        await _run_backfill(db_session)
        first = {
            name: loc.id
            for name, loc in (await _locations(db_session, test_event.id)).items()
        }
        await _run_backfill(db_session)
        second = {
            name: loc.id
            for name, loc in (await _locations(db_session, test_event.id)).items()
        }

        assert first == second
        assert set(first) == {"Foyer", "Garden"}
        reloaded = await db_session.get(Task, task.id, populate_existing=True)
        assert reloaded is not None and reloaded.location_id == first["Foyer"]

    async def test_keeps_locations_created_after_the_upgrade(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        """An existing location of the same name is reused, not duplicated."""
        existing = Location(event_id=test_event.id, name="Foyer")
        db_session.add(existing)
        task = _task(test_event, test_user, "Foyer")
        db_session.add(task)
        await db_session.flush()

        await _run_backfill(db_session)

        locations = await _locations(db_session, test_event.id)
        assert list(locations) == ["Foyer"]
        assert locations["Foyer"].id == existing.id
        reloaded = await db_session.get(Task, task.id, populate_existing=True)
        assert reloaded is not None and reloaded.location_id == existing.id
