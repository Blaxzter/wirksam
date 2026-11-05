"""People in charge and the shifts of tasks that earn vouchers.

Every extra, longer or bigger shift earns vouchers, so by default only the
event admins add, re-time, resize or delete the shifts of a task with
``vouchers_per_shift > 0``. The event setting ``managers_edit_voucher_shifts``
gives that back to the people in charge. The task's details stay theirs either
way, and so do a shift's title, description, place and category.

The cast, all in ``test_event``: ``admin`` (``test_event_admin_user``), and
``manager``, a member in charge of ``test_task``. The event wall clock is the
day before the task starts, so every shift here lies ahead and nobody has
booked one: the shift history rule never decides.
"""

import datetime as dt
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from tests.fixtures.client import act_as
from tests.fixtures.clock import fixed_clock

NOW = dt.datetime(2026, 6, 10, 9, 0)

SCHEDULE: dict[str, Any] = {
    "default_start_time": "09:00:00",
    "default_end_time": "11:00:00",
    "shift_duration_minutes": 60,
    "people_per_shift": 1,
}


@dataclass
class Cast:
    event: Event
    task: Task
    admin: User
    manager: User


@pytest_asyncio.fixture
async def cast(
    db_session: AsyncSession,
    test_event: Event,
    test_task: Task,
    test_event_admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> Cast:
    monkeypatch.setattr("app.logic.clock.wall_clock_now", fixed_clock(NOW))
    manager = User(
        subject="local|voucher-shift-manager",
        email="manager.voucher-shifts@example.com",
        name="Manager",
        roles=[],
        is_active=True,
    )
    db_session.add(manager)
    await db_session.flush()
    db_session.add(
        EventMembership(user_id=manager.id, event_id=test_event.id, role="member")
    )
    db_session.add(TaskManager(task_id=test_task.id, user_id=manager.id))
    await db_session.flush()
    return Cast(
        event=test_event, task=test_task, admin=test_event_admin_user, manager=manager
    )


async def _configure(
    db: AsyncSession, cast: Cast, *, rate: int, managers_may: bool
) -> None:
    cast.task.vouchers_per_shift = rate
    cast.event.managers_edit_voucher_shifts = managers_may
    db.add_all([cast.task, cast.event])
    await db.flush()


async def _shift(
    db: AsyncSession, task: Task, *, batch: ShiftBatch | None = None
) -> Shift:
    shift = Shift(
        task_id=task.id,
        batch_id=batch.id if batch else None,
        title="Theke",
        date=dt.date(2026, 6, 12),
        start_time=dt.time(8, 0),
        end_time=dt.time(12, 0),
        max_bookings=3,
    )
    db.add(shift)
    await db.flush()
    return shift


async def _batch(db: AsyncSession, task: Task) -> ShiftBatch:
    batch = ShiftBatch(
        task_id=task.id, start_date=task.start_date, end_date=task.end_date
    )
    db.add(batch)
    await db.flush()
    return batch


async def _shift_count(db: AsyncSession, task: Task) -> int:
    result = await db.execute(
        select(func.count()).select_from(Shift).where(col(Shift.task_id) == task.id)
    )
    return result.scalar_one()


async def _exists(db: AsyncSession, row: Shift | ShiftBatch) -> bool:
    return await db.get(type(row), row.id, populate_existing=True) is not None


#: A shift write's response, and whether it did what it was asked to do,
#: checked against the database rather than taken from the status code.
Outcome = tuple[Response, Callable[[], Awaitable[bool]]]


async def _create_shift(client: AsyncClient, db: AsyncSession, cast: Cast) -> Outcome:
    r = await client.post(
        "/api/v1/shifts/",
        json={
            "task_id": str(cast.task.id),
            "title": "Extra",
            "date": "2026-06-12",
            "start_time": "14:00:00",
            "end_time": "16:00:00",
        },
    )

    async def done() -> bool:
        rows = await db.execute(
            select(func.count())
            .select_from(Shift)
            .where(col(Shift.task_id) == cast.task.id, col(Shift.title) == "Extra")
        )
        return rows.scalar_one() == 1

    return r, done


async def _retime_shift(client: AsyncClient, db: AsyncSession, cast: Cast) -> Outcome:
    shift = await _shift(db, cast.task)
    r = await client.patch(
        f"/api/v1/shifts/{shift.id}", json={"start_time": "09:00:00"}
    )

    async def done() -> bool:
        await db.refresh(shift)
        return shift.start_time == dt.time(9, 0)

    return r, done


async def _resize_shift(client: AsyncClient, db: AsyncSession, cast: Cast) -> Outcome:
    shift = await _shift(db, cast.task)
    r = await client.patch(f"/api/v1/shifts/{shift.id}", json={"max_bookings": 5})

    async def done() -> bool:
        await db.refresh(shift)
        return shift.max_bookings == 5

    return r, done


async def _delete_shift(client: AsyncClient, db: AsyncSession, cast: Cast) -> Outcome:
    shift = await _shift(db, cast.task)
    r = await client.delete(f"/api/v1/shifts/{shift.id}")

    async def done() -> bool:
        return not await _exists(db, shift)

    return r, done


async def _add_shifts(client: AsyncClient, db: AsyncSession, cast: Cast) -> Outcome:
    before = await _shift_count(db, cast.task)
    r = await client.post(
        f"/api/v1/tasks/{cast.task.id}/add-shifts",
        json={
            "start_date": "2026-06-12",
            "end_date": "2026-06-12",
            "schedule": SCHEDULE,
        },
    )

    async def done() -> bool:
        # 09:00-11:00 in hours: two shifts.
        return await _shift_count(db, cast.task) == before + 2

    return r, done


async def _regenerate_dry(client: AsyncClient, db: AsyncSession, cast: Cast) -> Outcome:
    shift = await _shift(db, cast.task)
    r = await client.post(
        f"/api/v1/tasks/{cast.task.id}/regenerate-shifts",
        params={"dry_run": True},
        json={"schedule": SCHEDULE},
    )

    async def done() -> bool:
        # A preview: it reports the 08:00-12:00 shift as going, and keeps it.
        return (
            r.status_code == 200
            and r.json()["shifts_removed"] == 1
            and await _exists(db, shift)
        )

    return r, done


async def _regenerate(client: AsyncClient, db: AsyncSession, cast: Cast) -> Outcome:
    shift = await _shift(db, cast.task)
    r = await client.post(
        f"/api/v1/tasks/{cast.task.id}/regenerate-shifts", json={"schedule": SCHEDULE}
    )

    async def done() -> bool:
        # Two hourly shifts on each of the task's three days replace it.
        return not await _exists(db, shift) and await _shift_count(db, cast.task) == 6

    return r, done


async def _delete_batch(client: AsyncClient, db: AsyncSession, cast: Cast) -> Outcome:
    batch = await _batch(db, cast.task)
    shift = await _shift(db, cast.task, batch=batch)
    r = await client.delete(f"/api/v1/tasks/{cast.task.id}/batches/{batch.id}")

    async def done() -> bool:
        return not await _exists(db, batch) and not await _exists(db, shift)

    return r, done


ShiftOp = Callable[[AsyncClient, AsyncSession, Cast], Awaitable[Outcome]]
SHIFT_OPS: dict[str, ShiftOp] = {
    "create shift": _create_shift,
    "re-time shift": _retime_shift,
    "resize shift": _resize_shift,
    "delete shift": _delete_shift,
    "add shifts": _add_shifts,
    "regenerate (dry run)": _regenerate_dry,
    "regenerate": _regenerate,
    "delete batch": _delete_batch,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("op", list(SHIFT_OPS))
@pytest.mark.parametrize(
    ("who", "rate", "managers_may", "allowed"),
    [
        pytest.param("manager", 2, False, False, id="in charge, vouchers, default"),
        pytest.param("manager", 2, True, True, id="in charge, vouchers, allowed"),
        pytest.param("manager", 0, False, True, id="in charge, no vouchers"),
        pytest.param("admin", 2, False, True, id="admin, default"),
        pytest.param("admin", 2, True, True, id="admin, allowed"),
    ],
)
async def test_shift_writes(
    app: FastAPI,
    async_client: AsyncClient,
    db_session: AsyncSession,
    cast: Cast,
    op: str,
    who: str,
    rate: int,
    managers_may: bool,
    allowed: bool,
) -> None:
    await _configure(db_session, cast, rate=rate, managers_may=managers_may)
    with act_as(app, getattr(cast, who)):
        r, done = await SHIFT_OPS[op](async_client, db_session, cast)
    if allowed:
        assert r.status_code in (200, 201, 204), r.text
        assert await done(), f"{op} answered {r.status_code} but did not happen"
    else:
        assert r.status_code == 403, r.text
        assert r.json()["code"] == "task.voucher_shifts_admin_only"
        assert not await done(), f"{op} was refused but happened anyway"


@pytest.mark.asyncio
class TestWhatStaysEditable:
    """While the shifts are locked, the person in charge keeps the rest."""

    @pytest_asyncio.fixture
    async def locked(self, db_session: AsyncSession, cast: Cast) -> Shift:
        await _configure(db_session, cast, rate=2, managers_may=False)
        return await _shift(db_session, cast.task)

    async def test_a_shifts_title_place_and_category(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        locked: Shift,
    ) -> None:
        with act_as(app, cast.manager):
            r = await async_client.patch(
                f"/api/v1/shifts/{locked.id}",
                json={
                    "title": "Treffpunkt",
                    "description": "Wir treffen uns an Tor B.",
                    "location": "Tor B",
                    "category": "Einlass",
                },
            )
        assert r.status_code == 200, r.text
        await db_session.refresh(locked)
        assert (locked.title, locked.location) == ("Treffpunkt", "Tor B")

    async def test_the_earning_fields_sent_unchanged(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        locked: Shift,
    ) -> None:
        """A form that always sends every field must keep working."""
        with act_as(app, cast.manager):
            r = await async_client.patch(
                f"/api/v1/shifts/{locked.id}",
                json={
                    "title": "Theke vorne",
                    "date": "2026-06-12",
                    "start_time": "08:00:00",
                    "end_time": "12:00:00",
                    "max_bookings": 3,
                },
            )
        assert r.status_code == 200, r.text
        await db_session.refresh(locked)
        assert locked.title == "Theke vorne"

    async def test_the_tasks_details(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        locked: Shift,
    ) -> None:
        with act_as(app, cast.manager):
            r = await async_client.patch(
                f"/api/v1/tasks/{cast.task.id}",
                json={
                    "name": "Getränke",
                    "description": "Wasser und Saft.",
                    "start_date": "2026-06-11",
                    "end_date": "2026-06-14",
                    "location": "Foyer",
                    "category": "Verpflegung",
                },
            )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Getränke"
        assert r.json()["can_manage"] is True
        assert r.json()["can_manage_shifts"] is False

    async def test_a_rename_reaches_the_generated_shift_titles(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        locked: Shift,
    ) -> None:
        """A title is no earning field, so the shifts follow the task's name."""
        generated = await _shift(db_session, cast.task)
        generated.title = f"{cast.task.name} 08:00-12:00"
        db_session.add(generated)
        await db_session.flush()

        with act_as(app, cast.manager):
            r = await async_client.patch(
                f"/api/v1/tasks/{cast.task.id}", json={"name": "Getränke"}
            )
        assert r.status_code == 200, r.text
        await db_session.refresh(generated)
        await db_session.refresh(locked)
        assert generated.title == "Getränke 08:00-12:00"
        assert locked.title == "Theke"


@pytest.mark.asyncio
async def test_raising_the_rate_from_zero_locks_the_shifts_and_keeps_them(
    app: FastAPI,
    async_client: AsyncClient,
    db_session: AsyncSession,
    cast: Cast,
) -> None:
    """The shifts the person in charge made stay as they are; from then on
    only the organisers change them, and lowering the rate to 0 lifts it."""
    await _configure(db_session, cast, rate=0, managers_may=False)
    url = f"/api/v1/tasks/{cast.task.id}"
    with act_as(app, cast.manager):
        r, _ = await _add_shifts(async_client, db_session, cast)
        assert r.status_code == 201, r.text
        assert r.json()["task"]["can_manage_shifts"] is True
    before = sorted(
        (s.date, s.start_time, s.end_time, s.max_bookings)
        for s in (
            await db_session.execute(
                select(Shift).where(col(Shift.task_id) == cast.task.id)
            )
        ).scalars()
    )
    assert len(before) == 2

    with act_as(app, cast.admin):
        r = await async_client.patch(url, json={"vouchers_per_shift": 2})
    assert r.status_code == 200, r.text
    # An organiser is never limited.
    assert r.json()["can_manage_shifts"] is True
    after = sorted(
        (s.date, s.start_time, s.end_time, s.max_bookings)
        for s in (
            await db_session.execute(
                select(Shift)
                .where(col(Shift.task_id) == cast.task.id)
                .execution_options(populate_existing=True)
            )
        ).scalars()
    )
    assert after == before

    with act_as(app, cast.manager):
        r = await async_client.get(url)
        assert r.json()["can_manage"] is True
        assert r.json()["can_manage_shifts"] is False
        refused, _ = await _add_shifts(async_client, db_session, cast)
        assert refused.status_code == 403
        assert refused.json()["code"] == "task.voucher_shifts_admin_only"

    with act_as(app, cast.admin):
        r = await async_client.patch(url, json={"vouchers_per_shift": 0})
    assert r.status_code == 200, r.text
    with act_as(app, cast.manager):
        r = await async_client.get(url)
    assert r.json()["can_manage_shifts"] is True


@pytest.mark.asyncio
async def test_the_event_setting_unlocks_them(
    app: FastAPI,
    async_client: AsyncClient,
    db_session: AsyncSession,
    cast: Cast,
) -> None:
    """Switched on in the event settings, the person in charge gets the shift
    actions back without a change to the task."""
    await _configure(db_session, cast, rate=2, managers_may=False)
    url = f"/api/v1/tasks/{cast.task.id}"
    with act_as(app, cast.manager):
        assert (await async_client.get(url)).json()["can_manage_shifts"] is False
    with act_as(app, cast.admin):
        r = await async_client.patch(
            f"/api/v1/events/{cast.event.id}",
            json={"managers_edit_voucher_shifts": True},
        )
    assert r.status_code == 200, r.text
    with act_as(app, cast.manager):
        assert (await async_client.get(url)).json()["can_manage_shifts"] is True
        r, done = await _create_shift(async_client, db_session, cast)
    assert r.status_code == 201, r.text
    assert await done()
