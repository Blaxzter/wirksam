"""Tests for POST /events/{event_id}/clone.

The clone endpoint is the one place where a request body names rows that belong
to *another* event, so the authorisation assertions here (task id from a foreign
event, non-admin caller, sandbox source) matter as much as the counting ones.
"""

import datetime
import uuid
from typing import Any, TypedDict

import pytest
from httpx import AsyncClient
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic.notifications import triggers as triggers_module
from app.models.booking import Booking
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User

# ``test_event`` runs 2026-06-10 → 2026-06-14. Cloning it to 2027-06-09 is a
# whole-year move that is deliberately *not* a round number of weeks, so an
# off-by-one in the offset shows up as a wrong weekday, not a near miss.
NEW_START = datetime.date(2027, 6, 9)
DELTA = datetime.timedelta(days=364)

SOURCE_OVERRIDES: list[dict[str, Any]] = [
    {"date": "2026-06-11", "start_time": "09:00:00", "end_time": "12:00:00"}
]


class SourceFixture(TypedDict):
    event: Event
    task: Task
    batch: ShiftBatch
    shifts: list[Shift]


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
async def source_event(
    db_session: AsyncSession,
    test_event: Event,
    test_user: User,
) -> SourceFixture:
    """A source event carrying one task → one batch → three booked shifts."""
    task = Task(
        name="Kuchentheke",
        description="Kuchen verkaufen",
        start_date=datetime.date(2026, 6, 11),
        end_date=datetime.date(2026, 6, 12),
        status="published",
        location="Foyer",
        category="catering",
        shift_duration_minutes=120,
        default_start_time=datetime.time(8, 0),
        default_end_time=datetime.time(12, 0),
        people_per_shift=2,
        schedule_overrides=list(SOURCE_OVERRIDES),
        created_by_id=test_user.id,
        event_id=test_event.id,
    )
    db_session.add(task)
    await db_session.flush()

    batch = ShiftBatch(
        task_id=task.id,
        label="Kuchentheke",
        start_date=datetime.date(2026, 6, 11),
        end_date=datetime.date(2026, 6, 12),
        location="Foyer",
        category="catering",
        default_start_time=datetime.time(8, 0),
        default_end_time=datetime.time(12, 0),
        shift_duration_minutes=120,
        people_per_shift=2,
        remainder_mode="short",
        schedule_overrides=list(SOURCE_OVERRIDES),
    )
    db_session.add(batch)
    await db_session.flush()

    shifts = [
        Shift(
            task_id=task.id,
            batch_id=batch.id,
            title="Kuchentheke 09:00-11:00",
            description="Erste Schicht",
            date=datetime.date(2026, 6, 11),
            start_time=datetime.time(9, 0),
            end_time=datetime.time(11, 0),
            location="Foyer",
            category="catering",
            max_bookings=2,
        ),
        Shift(
            task_id=task.id,
            batch_id=batch.id,
            title="Kuchentheke 11:00-12:00",
            date=datetime.date(2026, 6, 11),
            start_time=datetime.time(11, 0),
            end_time=datetime.time(12, 0),
            location="Foyer",
            category="catering",
            max_bookings=2,
        ),
        Shift(
            task_id=task.id,
            batch_id=batch.id,
            title="Kuchentheke 08:00-10:00",
            date=datetime.date(2026, 6, 12),
            start_time=datetime.time(8, 0),
            end_time=datetime.time(10, 0),
            location="Foyer",
            category="catering",
            max_bookings=2,
        ),
    ]
    db_session.add_all(shifts)
    await db_session.flush()

    db_session.add(
        Booking(shift_id=shifts[0].id, user_id=test_user.id, status="confirmed")
    )
    await db_session.flush()

    return SourceFixture(event=test_event, task=task, batch=batch, shifts=shifts)


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record the announcement dispatch instead of running it.

    The route imports ``dispatch_event_cloned`` from the trigger module at call
    time, so patching the module attribute is enough — and it means the test
    asserts on what the background task was *asked* to do rather than driving a
    second session and an SMTP stub through it.
    """
    calls: list[dict[str, Any]] = []

    async def _record(
        *,
        event_id: uuid.UUID,
        note: str | None = None,
        exclude_user_id: uuid.UUID | None = None,
    ) -> None:
        calls.append(
            {"event_id": event_id, "note": note, "exclude_user_id": exclude_user_id}
        )

    monkeypatch.setattr(triggers_module, "dispatch_event_cloned", _record)
    return calls


def _body(source: SourceFixture, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Kirchentags Woche 2027",
        "start_date": NEW_START.isoformat(),
        "tasks": [{"source_task_id": str(source["task"].id)}],
    }
    payload.update(overrides)
    return payload


async def _tasks_of(db: AsyncSession, event_id: uuid.UUID) -> list[Task]:
    result = await db.execute(select(Task).where(col(Task.event_id) == event_id))
    return list(result.scalars().all())


async def _shifts_of(db: AsyncSession, task_id: uuid.UUID) -> list[Shift]:
    result = await db.execute(
        select(Shift)
        .where(col(Shift.task_id) == task_id)
        .order_by(col(Shift.date), col(Shift.start_time))
    )
    return list(result.scalars().all())


async def _batches_of(db: AsyncSession, task_id: uuid.UUID) -> list[ShiftBatch]:
    result = await db.execute(
        select(ShiftBatch)
        .where(col(ShiftBatch.task_id) == task_id)
        .order_by(col(ShiftBatch.start_date))
    )
    return list(result.scalars().all())


def _grid(shifts: list[Shift]) -> list[tuple[datetime.date, str, str]]:
    """The (date, start, end) triples a generated or copied set of shifts covers.

    Spelled out rather than counted: a count matches whatever the generator
    happens to produce, while the grid is what ``remainder_mode`` and the
    per-date overrides actually decide.
    """
    return [
        (
            s.date,
            s.start_time.isoformat() if s.start_time else "",
            s.end_time.isoformat() if s.end_time else "",
        )
        for s in shifts
    ]


async def _add_source_task(
    db: AsyncSession,
    *,
    event: Event,
    creator: User,
    name: str,
    start: datetime.date = datetime.date(2026, 6, 11),
    end: datetime.date = datetime.date(2026, 6, 12),
    **columns: Any,
) -> Task:
    """A second task on the source event, for the branches the main one misses."""
    task = Task(
        name=name,
        start_date=start,
        end_date=end,
        status="published",
        created_by_id=creator.id,
        event_id=event.id,
        **columns,
    )
    db.add(task)
    await db.flush()
    return task


# ── Happy path ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCloneHappyPath:
    async def test_returns_counts_and_decorated_event(
        self,
        async_client: AsyncClient,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event),
        )
        assert r.status_code == 201, r.text
        data = r.json()

        assert data["tasks_created"] == 1
        assert data["shifts_created"] == 3
        assert data["members_copied"] == 0
        assert data["notified"] is False

        event = data["event"]
        assert event["name"] == "Kirchentags Woche 2027"
        assert event["id"] != str(source_event["event"].id)
        # Decorated, not bare: the frontend renders off my_role/can_manage.
        assert event["my_role"] == "owner"
        assert event["can_manage"] is True
        assert event["member_count"] == 1

    async def test_new_event_defaults(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
        test_event_admin_user: User,
    ):
        """Duration preserved, description copied, flags deliberately reset."""
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event),
        )
        assert r.status_code == 201
        event = r.json()["event"]

        assert event["start_date"] == "2027-06-09"
        # Source ran 10th → 14th: four days, kept.
        assert event["end_date"] == "2027-06-13"
        assert event["description"] == source_event["event"].description
        assert event["status"] == "draft"
        assert event["visibility"] == "private"
        assert event["is_featured"] is False
        assert event["is_sandbox"] is False
        assert event["sandbox_expires_at"] is None
        assert event["created_by_id"] == str(test_event_admin_user.id)

        clone = await db_session.get(Event, uuid.UUID(event["id"]))
        assert clone is not None
        assert clone.is_featured is False
        assert clone.is_sandbox is False
        assert clone.sandbox_expires_at is None

    async def test_explicit_end_date_and_description_win(
        self,
        async_client: AsyncClient,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                end_date="2027-06-20",
                description=None,
                visibility="public",
            ),
        )
        assert r.status_code == 201
        event = r.json()["event"]
        assert event["end_date"] == "2027-06-20"
        assert event["description"] is None
        assert event["visibility"] == "public"

    async def test_copy_defaults_false_clears_default_times(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        source_event["event"].default_start_time = datetime.time(8, 0)
        source_event["event"].default_end_time = datetime.time(18, 0)
        db_session.add(source_event["event"])
        await db_session.flush()

        with_defaults = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event, name="With defaults"),
        )
        assert with_defaults.status_code == 201
        assert with_defaults.json()["event"]["default_start_time"] == "08:00:00"

        without = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event, name="Without defaults", copy_defaults=False),
        )
        assert without.status_code == 201
        assert without.json()["event"]["default_start_time"] is None
        assert without.json()["event"]["default_end_time"] is None

    async def test_no_tasks_clones_the_shell_only(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event, tasks=[]),
        )
        assert r.status_code == 201
        assert r.json()["tasks_created"] == 0
        assert r.json()["shifts_created"] == 0

        # The two counters are arithmetic over ``len(body.tasks)``, so they
        # cannot disagree with each other. The database can.
        new_event_id = uuid.UUID(r.json()["event"]["id"])
        assert await _tasks_of(db_session, new_event_id) == []
        shifts = await db_session.execute(
            select(sa_func.count())
            .select_from(Shift)
            .join(Task, col(Task.id) == col(Shift.task_id))
            .where(col(Task.event_id) == new_event_id)
        )
        assert shifts.scalar_one() == 0
        batches = await db_session.execute(
            select(sa_func.count())
            .select_from(ShiftBatch)
            .join(Task, col(Task.id) == col(ShiftBatch.task_id))
            .where(col(Task.event_id) == new_event_id)
        )
        assert batches.scalar_one() == 0


# ── Date offset ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCloneDateOffset:
    async def test_task_batch_and_shift_dates_all_move_by_one_delta(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event),
        )
        assert r.status_code == 201
        new_event_id = uuid.UUID(r.json()["event"]["id"])

        tasks = await _tasks_of(db_session, new_event_id)
        assert len(tasks) == 1
        task = tasks[0]
        assert task.start_date == source_event["task"].start_date + DELTA
        assert task.end_date == source_event["task"].end_date + DELTA

        batches = list(
            (
                await db_session.execute(
                    select(ShiftBatch).where(col(ShiftBatch.task_id) == task.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(batches) == 1
        batch = batches[0]
        assert batch.start_date == source_event["batch"].start_date + DELTA
        assert batch.end_date == source_event["batch"].end_date + DELTA
        # Config that lives nowhere else survives.
        assert batch.remainder_mode == "short"
        assert batch.label == "Kuchentheke"
        assert batch.people_per_shift == 2

        shifts = await _shifts_of(db_session, task.id)
        assert [s.date for s in shifts] == [
            s.date + DELTA for s in source_event["shifts"]
        ]
        # Times never move, only dates.
        assert [s.start_time for s in shifts] == [
            datetime.time(9, 0),
            datetime.time(11, 0),
            datetime.time(8, 0),
        ]
        # Every shift is wired to the CLONED batch, not the source's.
        assert {s.batch_id for s in shifts} == {batch.id}
        assert batch.id != source_event["batch"].id

    async def test_schedule_overrides_shifted_on_task_and_batch(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event),
        )
        assert r.status_code == 201
        new_event_id = uuid.UUID(r.json()["event"]["id"])

        task = (await _tasks_of(db_session, new_event_id))[0]
        assert task.schedule_overrides == [
            {"date": "2027-06-10", "start_time": "09:00:00", "end_time": "12:00:00"}
        ]

        batch = (
            (
                await db_session.execute(
                    select(ShiftBatch).where(col(ShiftBatch.task_id) == task.id)
                )
            )
            .scalars()
            .one()
        )
        assert batch.schedule_overrides == task.schedule_overrides

        # The source blob is untouched — _shift_overrides returns a new list.
        await db_session.refresh(source_event["task"])
        assert source_event["task"].schedule_overrides == SOURCE_OVERRIDES

    async def test_clone_metadata_points_at_the_caller(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
        test_event_admin_user: User,
        test_user: User,
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event),
        )
        new_event_id = uuid.UUID(r.json()["event"]["id"])
        task = (await _tasks_of(db_session, new_event_id))[0]

        assert task.created_by_id == test_event_admin_user.id
        assert task.created_by_id != test_user.id
        assert task.is_sandbox is False
        assert task.id != source_event["task"].id


# ── What must NOT come along ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCloneLeavesSourceAlone:
    async def test_bookings_are_not_copied_and_source_is_intact(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        before = await db_session.execute(select(sa_func.count()).select_from(Booking))
        booking_count_before = before.scalar_one()

        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event),
        )
        assert r.status_code == 201
        new_event_id = uuid.UUID(r.json()["event"]["id"])

        after = await db_session.execute(select(sa_func.count()).select_from(Booking))
        assert after.scalar_one() == booking_count_before

        new_task = (await _tasks_of(db_session, new_event_id))[0]
        booked = await db_session.execute(
            select(sa_func.count())
            .select_from(Booking)
            .join(Shift, col(Shift.id) == col(Booking.shift_id))
            .where(col(Shift.task_id) == new_task.id)
        )
        assert booked.scalar_one() == 0

        # The source task keeps every one of its own shifts: a delete-orphan
        # relationship would have MOVED them onto the clone.
        source_shifts = await _shifts_of(db_session, source_event["task"].id)
        assert len(source_shifts) == 3
        assert all(s.date.year == 2026 for s in source_shifts)
        assert all(s.batch_id == source_event["batch"].id for s in source_shifts)

        await db_session.refresh(source_event["event"])
        assert source_event["event"].start_date == datetime.date(2026, 6, 10)
        assert source_event["event"].name == "Kirchentags Woche 2026"


# ── Authorisation ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCloneAuthorisation:
    async def test_plain_member_gets_403(
        self,
        async_client: AsyncClient,
        source_event: SourceFixture,
    ):
        """The default identity, ``test_user``, is only a member here."""
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event),
        )
        assert r.status_code == 403
        assert r.json()["code"] == "event.forbidden"

    async def test_outsider_gets_403(
        self,
        async_client: AsyncClient,
        source_event: SourceFixture,
        as_outsider: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event),
        )
        assert r.status_code == 403

    async def test_unknown_event_is_404(
        self,
        async_client: AsyncClient,
        as_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{uuid.uuid4()}/clone",
            json={"name": "Nope", "start_date": "2027-01-01"},
        )
        assert r.status_code == 404
        # The source lookup is ``crud_event.get(raise_404_error=True)``, shared
        # with every other event route, which raises a bare HTTPException — so
        # the machine-readable identity is the problem *type*, and there is no
        # ``code`` key at all. Pinned so a route that starts answering
        # ``task.not_found`` (or an untyped ``about:blank``) here is caught.
        assert r.json()["type"] == "urn:problem:event.not_found"
        assert "code" not in r.json()

    async def test_task_from_another_event_is_404(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        test_draft_event: Event,
        test_user: User,
        as_event_admin: None,
    ):
        """The hole a clone endpoint invites: a task id the caller does not own."""
        foreign = Task(
            name="Not yours",
            start_date=datetime.date(2026, 12, 2),
            end_date=datetime.date(2026, 12, 3),
            status="published",
            created_by_id=test_user.id,
            event_id=test_draft_event.id,
        )
        db_session.add(foreign)
        await db_session.flush()

        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                tasks=[{"source_task_id": str(foreign.id)}],
            ),
        )
        assert r.status_code == 404
        assert r.json()["code"] == "task.not_found"

    async def test_sandbox_source_is_refused(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event_admin_user: User,
        as_event_admin: None,
    ):
        """A demo must never turn into a real event."""
        demo = Event(
            name="Demo-Veranstaltung",
            start_date=datetime.date(2026, 6, 10),
            end_date=datetime.date(2026, 6, 14),
            status="published",
            visibility="private",
            is_sandbox=True,
            sandbox_expires_at=datetime.datetime(2026, 6, 10, 12, 0),
            created_by_id=test_event_admin_user.id,
        )
        db_session.add(demo)
        await db_session.flush()
        db_session.add(
            EventMembership(
                user_id=test_event_admin_user.id, event_id=demo.id, role="owner"
            )
        )
        await db_session.flush()

        r = await async_client.post(
            f"/api/v1/events/{demo.id}/clone",
            json={"name": "Real event", "start_date": "2027-06-09"},
        )
        assert r.status_code == 403
        assert r.json()["code"] == "sandbox.clone_disabled"

        # And nothing was created on the way out.
        count = await db_session.execute(
            select(sa_func.count())
            .select_from(Event)
            .where(col(Event.name) == "Real event")
        )
        assert count.scalar_one() == 0


# ── Date-range validation ───────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCloneDateValidation:
    async def test_task_outside_new_window_is_422(
        self,
        async_client: AsyncClient,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        """A one-day clone cannot hold a two-day task."""
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event, end_date=NEW_START.isoformat()),
        )
        assert r.status_code == 422
        assert r.json()["code"] == "event.date_range_conflict"

    async def test_task_date_override_outside_window_is_422(
        self,
        async_client: AsyncClient,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                tasks=[
                    {
                        "source_task_id": str(source_event["task"].id),
                        "start_date": "2027-07-01",
                        "end_date": "2027-07-02",
                    }
                ],
            ),
        )
        assert r.status_code == 422
        assert r.json()["code"] == "event.date_range_conflict"

    async def test_end_before_start_is_422(
        self,
        async_client: AsyncClient,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event, end_date="2027-06-01"),
        )
        assert r.status_code == 422
        assert r.json()["code"] == "event.invalid_dates"


# ── Per-task overrides ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCloneTaskOverrides:
    async def test_overrides_land_on_the_cloned_task(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                tasks=[
                    {
                        "source_task_id": str(source_event["task"].id),
                        "name": "Waffelstand",
                        "status": "draft",
                        "location": "Garten",
                        "category": "food",
                        "people_per_shift": 4,
                        "shift_duration_minutes": 60,
                    }
                ],
            ),
        )
        assert r.status_code == 201
        task = (await _tasks_of(db_session, uuid.UUID(r.json()["event"]["id"])))[0]

        assert task.name == "Waffelstand"
        assert task.status == "draft"
        assert task.location == "Garten"
        assert task.category == "food"
        assert task.people_per_shift == 4
        assert task.shift_duration_minutes == 60
        # Not overridden → source value, unchanged.
        assert task.default_start_time == datetime.time(8, 0)
        assert task.description == "Kuchen verkaufen"

    async def test_date_override_moves_the_batches_and_shifts_too(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        """A re-dated task takes everything under it along.

        The event offset is 364 days; this task is moved 366. Moving the Task
        row alone would leave its batches and shifts two days behind, pointing
        at dates the task no longer covers.
        """
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                tasks=[
                    {
                        "source_task_id": str(source_event["task"].id),
                        "start_date": "2027-06-12",
                        "end_date": "2027-06-13",
                    }
                ],
            ),
        )
        assert r.status_code == 201, r.text
        task = (await _tasks_of(db_session, uuid.UUID(r.json()["event"]["id"])))[0]

        assert (task.start_date, task.end_date) == (
            datetime.date(2027, 6, 12),
            datetime.date(2027, 6, 13),
        )

        batch = (await _batches_of(db_session, task.id))[0]
        assert (batch.start_date, batch.end_date) == (
            datetime.date(2027, 6, 12),
            datetime.date(2027, 6, 13),
        )

        shifts = await _shifts_of(db_session, task.id)
        assert [s.date for s in shifts] == [
            datetime.date(2027, 6, 12),
            datetime.date(2027, 6, 12),
            datetime.date(2027, 6, 13),
        ]
        # The overrides follow the *task's* offset, not the event's, or the
        # override would name a day the shifts no longer fall on.
        assert task.schedule_overrides == [
            {"date": "2027-06-12", "start_time": "09:00:00", "end_time": "12:00:00"}
        ]
        assert batch.schedule_overrides == task.schedule_overrides

    async def test_generation_overrides_change_the_regenerated_grid(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        """``regenerate`` has to honour the per-task generation overrides.

        They are written onto the cloned batch as well as the task, so an
        override that only reached the Task row would be a no-op here: the
        generator reads the batch column first.
        """
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                tasks=[
                    {
                        "source_task_id": str(source_event["task"].id),
                        "mode": "regenerate",
                        "shift_duration_minutes": 60,
                        "people_per_shift": 3,
                    }
                ],
            ),
        )
        assert r.status_code == 201, r.text
        task = (await _tasks_of(db_session, uuid.UUID(r.json()["event"]["id"])))[0]
        shifts = await _shifts_of(db_session, task.id)

        # Hourly, not two-hourly: 09-12 on the override day, 08-12 on the other.
        assert _grid(shifts) == [
            (datetime.date(2027, 6, 10), "09:00:00", "10:00:00"),
            (datetime.date(2027, 6, 10), "10:00:00", "11:00:00"),
            (datetime.date(2027, 6, 10), "11:00:00", "12:00:00"),
            (datetime.date(2027, 6, 11), "08:00:00", "09:00:00"),
            (datetime.date(2027, 6, 11), "09:00:00", "10:00:00"),
            (datetime.date(2027, 6, 11), "10:00:00", "11:00:00"),
            (datetime.date(2027, 6, 11), "11:00:00", "12:00:00"),
        ]
        assert r.json()["shifts_created"] == 7
        assert all(s.max_bookings == 3 for s in shifts)

        batch = (await _batches_of(db_session, task.id))[0]
        assert batch.shift_duration_minutes == 60
        assert batch.people_per_shift == 3


# ── Regenerate mode ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCloneRegenerateMode:
    async def test_regenerate_produces_shifts_from_batch_config(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                tasks=[
                    {
                        "source_task_id": str(source_event["task"].id),
                        "mode": "regenerate",
                    }
                ],
            ),
        )
        assert r.status_code == 201
        assert r.json()["shifts_created"] > 0

        new_event_id = uuid.UUID(r.json()["event"]["id"])
        task = (await _tasks_of(db_session, new_event_id))[0]
        batch = (
            (
                await db_session.execute(
                    select(ShiftBatch).where(col(ShiftBatch.task_id) == task.id)
                )
            )
            .scalars()
            .one()
        )
        shifts = await _shifts_of(db_session, task.id)

        assert len(shifts) == r.json()["shifts_created"]
        # Generated in the SHIFTED window, wired to the cloned batch.
        assert all(s.batch_id == batch.id for s in shifts)
        assert all(
            datetime.date(2027, 6, 10) <= s.date <= datetime.date(2027, 6, 11)
            for s in shifts
        )
        # The batch override moved with everything else, so the first day
        # starts at the override time rather than the batch default.
        first_day = [s for s in shifts if s.date == datetime.date(2027, 6, 10)]
        assert first_day
        assert min(s.start_time for s in first_day if s.start_time) == datetime.time(
            9, 0
        )
        assert all(s.max_bookings == 2 for s in shifts)


# ── Member copying ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCloneMembers:
    async def test_roster_copied_with_owner_demoted_and_self_skipped(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
        test_admin_user: User,
        test_event_admin_user: User,
        test_user: User,
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event, copy_members=True),
        )
        assert r.status_code == 201
        # Three in the source; the caller is already here, so two were written.
        assert r.json()["members_copied"] == 2

        new_event_id = uuid.UUID(r.json()["event"]["id"])
        rows = (
            (
                await db_session.execute(
                    select(EventMembership).where(
                        col(EventMembership.event_id) == new_event_id
                    )
                )
            )
            .scalars()
            .all()
        )
        roles = {m.user_id: m.role for m in rows}

        assert roles[test_event_admin_user.id] == "owner"
        # The source owner is demoted: an event has exactly one owner, and it
        # is whoever pressed clone.
        assert roles[test_admin_user.id] == "admin"
        assert roles[test_user.id] == "member"
        assert len(roles) == 3

    async def test_source_roster_is_left_at_its_own_roles(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
        test_admin_user: User,
        test_event_admin_user: User,
        test_user: User,
    ):
        """The demotion is a *new* row's role, never the source membership.

        The copy loop walks live ORM rows from the request session, so writing
        ``membership.role = "admin"`` instead of building a new row would
        permanently demote the source event's owner — and every assertion about
        the clone's roster would still pass.
        """
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event, copy_members=True),
        )
        assert r.status_code == 201

        rows = (
            (
                await db_session.execute(
                    select(EventMembership).where(
                        col(EventMembership.event_id) == source_event["event"].id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {m.user_id: m.role for m in rows} == {
            test_admin_user.id: "owner",
            test_event_admin_user.id: "admin",
            test_user.id: "member",
        }

    async def test_not_copied_by_default(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
        test_event_admin_user: User,
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event),
        )
        assert r.json()["members_copied"] == 0

        rows = (
            (
                await db_session.execute(
                    select(EventMembership).where(
                        col(EventMembership.event_id)
                        == uuid.UUID(r.json()["event"]["id"])
                    )
                )
            )
            .scalars()
            .all()
        )
        assert [(m.user_id, m.role) for m in rows] == [
            (test_event_admin_user.id, "owner")
        ]


# ── Announcement ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCloneAnnouncement:
    async def test_announce_queues_the_dispatch(
        self,
        async_client: AsyncClient,
        source_event: SourceFixture,
        as_event_admin: None,
        queued: list[dict[str, Any]],
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                copy_members=True,
                announce={"send": True, "note": "Same as last year, bring aprons."},
            ),
        )
        assert r.status_code == 201
        assert r.json()["notified"] is True

        assert len(queued) == 1
        assert queued[0]["event_id"] == uuid.UUID(r.json()["event"]["id"])
        assert queued[0]["note"] == "Same as last year, bring aprons."

    async def test_not_queued_when_send_is_false(
        self,
        async_client: AsyncClient,
        source_event: SourceFixture,
        as_event_admin: None,
        queued: list[dict[str, Any]],
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event, announce={"send": False, "note": "ignored"}),
        )
        assert r.status_code == 201
        assert r.json()["notified"] is False
        assert queued == []

    async def test_send_without_copy_members_notifies_nobody(
        self,
        async_client: AsyncClient,
        source_event: SourceFixture,
        as_event_admin: None,
        queued: list[dict[str, Any]],
    ):
        """Asking to announce to a roster of one — yourself — is not a send.

        Without ``copy_members`` the clone's only membership is the cloner's
        own owner row, and the cloner is excluded from the announcement by
        definition. Reporting ``notified: true`` would have the UI promise a
        mail that was never sent.
        """
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                copy_members=False,
                announce={"send": True, "note": "Nobody to tell."},
            ),
        )
        assert r.status_code == 201, r.text
        assert r.json()["members_copied"] == 0
        assert r.json()["notified"] is False
        assert queued == []

    async def test_not_queued_when_announce_omitted(
        self,
        async_client: AsyncClient,
        source_event: SourceFixture,
        as_event_admin: None,
        queued: list[dict[str, Any]],
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event),
        )
        assert r.json()["notified"] is False
        assert queued == []

    async def test_note_is_capped(
        self,
        async_client: AsyncClient,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event, announce={"send": True, "note": "x" * 501}),
        )
        assert r.status_code == 422


# ── Copy mode: what "faithful reproduction" means column by column ──────────


@pytest.mark.asyncio
class TestCloneCopyFidelity:
    """``copy`` exists to reproduce the source shift rows, not just their dates."""

    async def test_every_shift_column_is_reproduced(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        """Title, description, end time, location, category and headcount.

        Dropping ``title`` and ``description`` from the copy would leave every
        date assertion green while destroying the exact thing copy mode is for.
        """
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event),
        )
        assert r.status_code == 201, r.text
        task = (await _tasks_of(db_session, uuid.UUID(r.json()["event"]["id"])))[0]

        cloned = await _shifts_of(db_session, task.id)
        # The fixture's shifts are already in (date, start_time) order.
        source = source_event["shifts"]
        assert len(cloned) == len(source)

        for new, old in zip(cloned, source, strict=True):
            assert new.title == old.title
            assert new.description == old.description
            assert new.start_time == old.start_time
            assert new.end_time == old.end_time
            assert new.location == old.location
            assert new.category == old.category
            assert new.max_bookings == old.max_bookings
            assert new.date == old.date + DELTA
            assert new.id != old.id

        # Both description branches are exercised: the fixture's first shift
        # carries one and its second does not.
        assert cloned[0].description == "Erste Schicht"
        assert cloned[1].description is None

    async def test_shift_without_a_batch_is_copied_unattached(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
        test_user: User,
    ):
        """A hand-added shift has no ``batch_id``; the copy must not invent one."""
        task = await _add_source_task(
            db_session,
            event=source_event["event"],
            creator=test_user,
            name="Handarbeit",
        )
        batch = ShiftBatch(
            task_id=task.id,
            label="Handarbeit",
            start_date=datetime.date(2026, 6, 11),
            end_date=datetime.date(2026, 6, 12),
            default_start_time=datetime.time(8, 0),
            default_end_time=datetime.time(12, 0),
            shift_duration_minutes=240,
            remainder_mode="drop",
        )
        db_session.add(batch)
        await db_session.flush()
        db_session.add_all(
            [
                Shift(
                    task_id=task.id,
                    batch_id=batch.id,
                    title="Aus dem Block",
                    date=datetime.date(2026, 6, 11),
                    start_time=datetime.time(8, 0),
                    end_time=datetime.time(12, 0),
                ),
                Shift(
                    task_id=task.id,
                    batch_id=None,
                    title="Von Hand",
                    date=datetime.date(2026, 6, 12),
                    start_time=datetime.time(14, 0),
                    end_time=datetime.time(16, 0),
                ),
            ]
        )
        await db_session.flush()

        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event, tasks=[{"source_task_id": str(task.id)}]),
        )
        assert r.status_code == 201, r.text
        assert r.json()["shifts_created"] == 2

        new_task = (await _tasks_of(db_session, uuid.UUID(r.json()["event"]["id"])))[0]
        new_batch = (await _batches_of(db_session, new_task.id))[0]
        by_title = {s.title: s for s in await _shifts_of(db_session, new_task.id)}

        assert by_title["Aus dem Block"].batch_id == new_batch.id
        assert by_title["Von Hand"].batch_id is None
        assert by_title["Von Hand"].date == datetime.date(2027, 6, 11)


# ── Regenerate mode: the branches the happy path never reaches ──────────────


@pytest.mark.asyncio
class TestCloneRegenerateEdgeCases:
    """``regenerate`` re-runs the generator, so its inputs decide the grid."""

    async def test_grid_is_exact_not_merely_non_empty(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
    ):
        """Pin every generated slot, including each day's trailing short one.

        The fixture's batch is ``remainder_mode="short"`` with a 120-minute
        duration, so the override day's 09:00-12:00 ends on a partial slot.
        Degrading to ``"drop"`` would lose 11:00-12:00 and nothing else —
        invisible to a count compared against itself.
        """
        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                tasks=[
                    {
                        "source_task_id": str(source_event["task"].id),
                        "mode": "regenerate",
                    }
                ],
            ),
        )
        assert r.status_code == 201, r.text
        task = (await _tasks_of(db_session, uuid.UUID(r.json()["event"]["id"])))[0]

        assert _grid(await _shifts_of(db_session, task.id)) == [
            # Override day: 09:00-12:00 at 120 minutes leaves a short 11-12.
            (datetime.date(2027, 6, 10), "09:00:00", "11:00:00"),
            (datetime.date(2027, 6, 10), "11:00:00", "12:00:00"),
            # Default day: 08:00-12:00 divides evenly.
            (datetime.date(2027, 6, 11), "08:00:00", "10:00:00"),
            (datetime.date(2027, 6, 11), "10:00:00", "12:00:00"),
        ]
        assert r.json()["shifts_created"] == 4

    async def test_source_task_without_batches_gets_a_synthetic_one(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
        test_user: User,
    ):
        """A task predating batches still regenerates, off a batch built here."""
        task = await _add_source_task(
            db_session,
            event=source_event["event"],
            creator=test_user,
            name="Ohne Block",
            default_start_time=datetime.time(8, 0),
            default_end_time=datetime.time(12, 0),
            shift_duration_minutes=120,
            people_per_shift=2,
        )
        assert await _batches_of(db_session, task.id) == []

        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                tasks=[{"source_task_id": str(task.id), "mode": "regenerate"}],
            ),
        )
        assert r.status_code == 201, r.text
        assert r.json()["shifts_created"] == 4

        new_task = (await _tasks_of(db_session, uuid.UUID(r.json()["event"]["id"])))[0]
        batches = await _batches_of(db_session, new_task.id)
        assert len(batches) == 1, "the regenerate screen needs a batch to read"
        assert batches[0].label == "Ohne Block"
        assert (batches[0].start_date, batches[0].end_date) == (
            datetime.date(2027, 6, 10),
            datetime.date(2027, 6, 11),
        )
        assert batches[0].remainder_mode == "drop"

        shifts = await _shifts_of(db_session, new_task.id)
        assert all(s.batch_id == batches[0].id for s in shifts)
        assert _grid(shifts) == [
            (datetime.date(2027, 6, 10), "08:00:00", "10:00:00"),
            (datetime.date(2027, 6, 10), "10:00:00", "12:00:00"),
            (datetime.date(2027, 6, 11), "08:00:00", "10:00:00"),
            (datetime.date(2027, 6, 11), "10:00:00", "12:00:00"),
        ]

    async def test_missing_generation_config_yields_no_shifts_not_a_500(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
        test_user: User,
    ):
        """Neither the batch nor the task has the values generation needs."""
        task = await _add_source_task(
            db_session,
            event=source_event["event"],
            creator=test_user,
            name="Ohne Zeiten",
        )
        db_session.add(
            ShiftBatch(
                task_id=task.id,
                label="Ohne Zeiten",
                start_date=datetime.date(2026, 6, 11),
                end_date=datetime.date(2026, 6, 12),
                remainder_mode="drop",
            )
        )
        await db_session.flush()

        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                tasks=[{"source_task_id": str(task.id), "mode": "regenerate"}],
            ),
        )
        assert r.status_code == 201, r.text
        assert r.json()["tasks_created"] == 1
        assert r.json()["shifts_created"] == 0

        new_task = (await _tasks_of(db_session, uuid.UUID(r.json()["event"]["id"])))[0]
        assert await _shifts_of(db_session, new_task.id) == []
        # The batch still travels: it is the row the edit screen reads, and
        # where the organiser fills the missing times in.
        assert len(await _batches_of(db_session, new_task.id)) == 1

    async def test_unparseable_override_is_dropped_and_the_rest_still_apply(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
        test_user: User,
    ):
        """A junk entry in the JSON blob must not take the generation with it."""
        overrides: list[dict[str, Any]] = [
            {"date": "2026-06-11", "start_time": "09:00:00", "end_time": "12:00:00"},
            {"date": "irgendwann", "start_time": "06:00:00", "end_time": "07:00:00"},
        ]
        task = await _add_source_task(
            db_session,
            event=source_event["event"],
            creator=test_user,
            name="Kaputter Override",
            schedule_overrides=list(overrides),
        )
        db_session.add(
            ShiftBatch(
                task_id=task.id,
                label="Kaputter Override",
                start_date=datetime.date(2026, 6, 11),
                end_date=datetime.date(2026, 6, 12),
                default_start_time=datetime.time(8, 0),
                default_end_time=datetime.time(12, 0),
                shift_duration_minutes=120,
                remainder_mode="drop",
                schedule_overrides=list(overrides),
            )
        )
        await db_session.flush()

        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                tasks=[{"source_task_id": str(task.id), "mode": "regenerate"}],
            ),
        )
        assert r.status_code == 201, r.text

        new_task = (await _tasks_of(db_session, uuid.UUID(r.json()["event"]["id"])))[0]
        # The good entry still moved with the clone — the first day starts at
        # 09:00, not at the batch default of 08:00.
        assert _grid(await _shifts_of(db_session, new_task.id)) == [
            (datetime.date(2027, 6, 10), "09:00:00", "11:00:00"),
            (datetime.date(2027, 6, 11), "08:00:00", "10:00:00"),
            (datetime.date(2027, 6, 11), "10:00:00", "12:00:00"),
        ]

    async def test_unparseable_override_is_copied_through_verbatim(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
        test_user: User,
    ):
        """``_shift_overrides`` moves what it can parse and keeps the rest.

        Dropping the unreadable entry would silently edit the organiser's data;
        failing on it would make one bad blob unclonable forever.
        """
        overrides: list[dict[str, Any]] = [
            {"date": "2026-06-11", "start_time": "09:00:00", "end_time": "12:00:00"},
            {"date": "irgendwann", "start_time": "06:00:00", "end_time": "07:00:00"},
            {"start_time": "05:00:00", "end_time": "06:00:00"},
        ]
        task = await _add_source_task(
            db_session,
            event=source_event["event"],
            creator=test_user,
            name="Kaputter Override kopiert",
            schedule_overrides=list(overrides),
        )

        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(source_event, tasks=[{"source_task_id": str(task.id)}]),
        )
        assert r.status_code == 201, r.text

        new_task = (await _tasks_of(db_session, uuid.UUID(r.json()["event"]["id"])))[0]
        assert new_task.schedule_overrides == [
            {"date": "2027-06-10", "start_time": "09:00:00", "end_time": "12:00:00"},
            {"date": "irgendwann", "start_time": "06:00:00", "end_time": "07:00:00"},
            {"start_time": "05:00:00", "end_time": "06:00:00"},
        ]


# ── Rows that land outside the clone's window ───────────────────────────────


@pytest.mark.asyncio
class TestCloneRowsOutsideWindow:
    """A task can fit the new window while its own rows do not.

    ``add_shifts_to_task`` validates shift dates against the *event*, never the
    task, so a source task may legitimately own batches and shifts outside its
    own start/end. Shortening the window on the way through is what turns that
    into a conflict.
    """

    async def test_batch_outside_the_window_is_422(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
        test_user: User,
    ):
        task = await _add_source_task(
            db_session,
            event=source_event["event"],
            creator=test_user,
            name="Spaeter Block",
            start=datetime.date(2026, 6, 10),
            end=datetime.date(2026, 6, 10),
        )
        db_session.add(
            ShiftBatch(
                task_id=task.id,
                label="Spaeter Block",
                start_date=datetime.date(2026, 6, 13),
                end_date=datetime.date(2026, 6, 14),
                remainder_mode="drop",
            )
        )
        await db_session.flush()

        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                end_date="2027-06-11",
                tasks=[{"source_task_id": str(task.id)}],
            ),
        )
        assert r.status_code == 422, r.text
        assert r.json()["code"] == "event.date_range_conflict"
        # The message has to name the block, or the organiser cannot find it.
        assert "Spaeter Block" in r.json()["detail"]
        assert "2027-06-12" in r.json()["detail"]

    async def test_shift_outside_the_window_is_422(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
        test_user: User,
    ):
        task = await _add_source_task(
            db_session,
            event=source_event["event"],
            creator=test_user,
            name="Spaete Schicht",
            start=datetime.date(2026, 6, 10),
            end=datetime.date(2026, 6, 10),
        )
        db_session.add(
            Shift(
                task_id=task.id,
                batch_id=None,
                title="Abbau",
                date=datetime.date(2026, 6, 14),
                start_time=datetime.time(18, 0),
                end_time=datetime.time(20, 0),
            )
        )
        await db_session.flush()

        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                end_date="2027-06-11",
                tasks=[{"source_task_id": str(task.id)}],
            ),
        )
        assert r.status_code == 422, r.text
        assert r.json()["code"] == "event.date_range_conflict"
        assert "Spaete Schicht" in r.json()["detail"]
        assert "2027-06-13" in r.json()["detail"]

    async def test_abort_inside_the_task_loop_leaves_the_source_alone(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        source_event: SourceFixture,
        as_event_admin: None,
        test_user: User,
    ):
        """The genuine mid-clone abort: the Event row is already written.

        The sandbox guard refuses before the first write, so there is nothing
        to undo there. This 422 comes out of the task loop, after the Event,
        the owner membership and the first task have been added — and what the
        route owes the caller is a conflict naming the offending task, with the
        *source* untouched.

        Nothing is asserted here about the clone's own rows surviving or not.
        ``tests/fixtures/client.py`` documents the gap: the real ``get_db``
        owns its transaction and unwinds it when a route raises, while this
        fixture yields a savepoint-wrapped session with no such context
        manager, so writes made on the way to an error survive in tests and do
        not survive in production. An assertion either way would be an
        assertion about the fixture, not about the route.
        """
        late = await _add_source_task(
            db_session,
            event=source_event["event"],
            creator=test_user,
            name="Spaete Schicht",
            start=datetime.date(2026, 6, 10),
            end=datetime.date(2026, 6, 10),
        )
        db_session.add(
            Shift(
                task_id=late.id,
                batch_id=None,
                title="Abbau",
                date=datetime.date(2026, 6, 14),
                start_time=datetime.time(18, 0),
                end_time=datetime.time(20, 0),
            )
        )
        await db_session.flush()

        r = await async_client.post(
            f"/api/v1/events/{source_event['event'].id}/clone",
            json=_body(
                source_event,
                end_date="2027-06-11",
                tasks=[
                    # The first task clones cleanly; the abort happens on the
                    # second pass through the loop.
                    {"source_task_id": str(source_event["task"].id)},
                    {"source_task_id": str(late.id)},
                ],
            ),
        )
        assert r.status_code == 422, r.text
        assert r.json()["code"] == "event.date_range_conflict"
        assert "Spaete Schicht" in r.json()["detail"]

        source_tasks = await _tasks_of(db_session, source_event["event"].id)
        assert {t.id for t in source_tasks} == {source_event["task"].id, late.id}

        kept = await _shifts_of(db_session, source_event["task"].id)
        assert len(kept) == 3
        assert all(s.date.year == 2026 for s in kept)
        assert all(s.batch_id == source_event["batch"].id for s in kept)
        assert [s.date for s in await _shifts_of(db_session, late.id)] == [
            datetime.date(2026, 6, 14)
        ]
