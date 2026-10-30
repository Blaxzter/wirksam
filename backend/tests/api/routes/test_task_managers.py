"""People in charge of a task: who names them, what they may do, and what not.

The cast, all in ``test_event`` unless noted:

- ``admin``: ``test_event_admin_user``, an event admin;
- ``manager``: a member in charge of ``test_task``;
- ``member``: ``test_user``, a plain member;
- ``outsider``: ``test_outsider_user``, in no event;
- ``sibling``: a member in charge of *another* task in the same event;
- ``elsewhere``: a member here who is in charge of a task in another event.

Only the first two may edit ``test_task``; being in charge of something else,
here or elsewhere, gives nothing on it.
"""

import datetime as dt
import uuid
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

from app.logic.permissions import task_access
from app.models.booking import Booking
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.event_team import EventTeam, EventTeamMember
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from tests.fixtures.client import act_as

#: The clock for the shift history tests: the morning of the fixture task's
#: first day, so a 08:00-12:00 shift that day is running.
NOW = dt.datetime(2026, 6, 11, 10, 0)

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
    member: User
    outsider: User
    sibling: User
    elsewhere: User
    sibling_task: Task
    other_event: Event

    def __getitem__(self, role: str) -> User:
        return getattr(self, role)


async def _user(db: AsyncSession, key: str, **columns: Any) -> User:
    user = User(
        subject=f"local|{key}",
        email=f"{key}.in-charge@example.com",
        name=key.capitalize(),
        roles=[],
        is_active=True,
        **columns,
    )
    db.add(user)
    await db.flush()
    return user


async def _member(
    db: AsyncSession, user: User, event: Event, role: str = "member"
) -> None:
    db.add(EventMembership(user_id=user.id, event_id=event.id, role=role))
    await db.flush()


async def _task(db: AsyncSession, event: Event, creator: User, **columns: Any) -> Task:
    task = Task(
        name=columns.pop("name", "Theke"),
        start_date=dt.date(2026, 6, 11),
        end_date=dt.date(2026, 6, 13),
        status=columns.pop("status", "published"),
        created_by_id=creator.id,
        event_id=event.id,
        **columns,
    )
    db.add(task)
    await db.flush()
    return task


async def _in_charge(db: AsyncSession, task: Task, user: User) -> None:
    db.add(TaskManager(task_id=task.id, user_id=user.id))
    await db.flush()


@pytest_asyncio.fixture
async def cast(
    db_session: AsyncSession,
    test_event: Event,
    test_draft_event: Event,
    test_task: Task,
    test_event_admin_user: User,
    test_user: User,
    test_outsider_user: User,
) -> Cast:
    manager = await _user(db_session, "manager", phone_number="+49 151 1111")
    sibling = await _user(db_session, "sibling")
    elsewhere = await _user(db_session, "elsewhere")
    for user in (manager, sibling, elsewhere):
        await _member(db_session, user, test_event)
    await _member(db_session, elsewhere, test_draft_event)

    sibling_task = await _task(db_session, test_event, test_user, name="Garderobe")
    other_task = await _task(db_session, test_draft_event, test_user, name="Kasse")
    await _in_charge(db_session, test_task, manager)
    await _in_charge(db_session, sibling_task, sibling)
    await _in_charge(db_session, other_task, elsewhere)
    return Cast(
        event=test_event,
        task=test_task,
        admin=test_event_admin_user,
        manager=manager,
        member=test_user,
        outsider=test_outsider_user,
        sibling=sibling,
        elsewhere=elsewhere,
        sibling_task=sibling_task,
        other_event=test_draft_event,
    )


async def _shift(
    db: AsyncSession,
    task: Task,
    *,
    date: dt.date = dt.date(2026, 6, 12),
    start: dt.time | None = dt.time(8, 0),
    end: dt.time | None = dt.time(12, 0),
    batch: ShiftBatch | None = None,
) -> Shift:
    shift = Shift(
        task_id=task.id,
        batch_id=batch.id if batch else None,
        title="Theke",
        date=date,
        start_time=start,
        end_time=end,
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


async def _book(
    db: AsyncSession, shift: Shift, user: User, *, notes: str | None = None
) -> Booking:
    """Booked directly: these shifts lie in the past of the real clock."""
    booking = Booking(
        shift_id=shift.id, user_id=user.id, status="confirmed", notes=notes
    )
    db.add(booking)
    await db.flush()
    return booking


async def _manager_rows(db: AsyncSession, **where: Any) -> list[TaskManager]:
    query = select(TaskManager)
    for key, value in where.items():
        query = query.where(col(getattr(TaskManager, key)) == value)
    return list((await db.execute(query)).scalars())


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> dt.datetime:
    monkeypatch.setattr("app.logic.clock.wall_clock_now", lambda: NOW)
    return NOW


ALL_ROLES = ("admin", "manager", "member", "outsider", "sibling", "elsewhere")
MAY_EDIT = {"admin", "manager"}


# ── Naming and removing ───────────────────────────────────────────


@pytest.mark.asyncio
class TestAddAndRemove:
    async def test_an_admin_puts_a_member_in_charge(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                f"/api/v1/tasks/{cast.task.id}/managers",
                json={"user_id": str(cast.member.id)},
            )
            assert r.status_code == 201, r.text
            assert r.json() == {
                "user_id": str(cast.member.id),
                "name": cast.member.name,
                "avatar_etag": None,
            }
            task = (await async_client.get(f"/api/v1/tasks/{cast.task.id}")).json()
        assert {m["user_id"] for m in task["managers"]} == {
            str(cast.member.id),
            str(cast.manager.id),
        }

    async def test_the_grant_records_who_made_it(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        with act_as(app, cast.admin):
            await async_client.post(
                f"/api/v1/tasks/{cast.task.id}/managers",
                json={"user_id": str(cast.member.id)},
            )
        [row] = await _manager_rows(db_session, user_id=cast.member.id)
        assert (row.added_by_id, row.added_by_name) == (cast.admin.id, cast.admin.name)

    async def test_a_non_member_cannot_be_put_in_charge(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                f"/api/v1/tasks/{cast.task.id}/managers",
                json={"user_id": str(cast.outsider.id)},
            )
        assert r.status_code == 422
        assert r.json()["code"] == "task.manager_not_event_member"

    async def test_twice_is_a_conflict(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                f"/api/v1/tasks/{cast.task.id}/managers",
                json={"user_id": str(cast.manager.id)},
            )
        assert r.status_code == 409
        assert r.json()["code"] == "task.manager_already"

    @pytest.mark.parametrize("role", ["member", "manager", "outsider"])
    async def test_only_admins_name_people_in_charge(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, role: str
    ) -> None:
        with act_as(app, cast[role]):
            r = await async_client.post(
                f"/api/v1/tasks/{cast.task.id}/managers",
                json={"user_id": str(cast.sibling.id)},
            )
        assert r.status_code == 403
        assert r.json()["code"] == "event.forbidden"

    async def test_an_unknown_task(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                f"/api/v1/tasks/{uuid.uuid4()}/managers",
                json={"user_id": str(cast.member.id)},
            )
        assert r.status_code == 404
        assert r.json()["code"] == "task.not_found"

    async def test_an_admin_removes_someone(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.delete(
                f"/api/v1/tasks/{cast.task.id}/managers/{cast.manager.id}"
            )
        assert r.status_code == 204
        assert await _manager_rows(db_session, task_id=cast.task.id) == []

    async def test_a_person_in_charge_steps_down(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        with act_as(app, cast.manager):
            r = await async_client.delete(
                f"/api/v1/tasks/{cast.task.id}/managers/{cast.manager.id}"
            )
        assert r.status_code == 204
        assert await _manager_rows(db_session, task_id=cast.task.id) == []

    @pytest.mark.parametrize("role", ["member", "sibling"])
    async def test_nobody_else_removes_someone(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, role: str
    ) -> None:
        with act_as(app, cast[role]):
            r = await async_client.delete(
                f"/api/v1/tasks/{cast.task.id}/managers/{cast.manager.id}"
            )
        assert r.status_code == 403
        assert r.json()["code"] == "event.forbidden"

    async def test_removing_someone_not_in_charge(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.delete(
                f"/api/v1/tasks/{cast.task.id}/managers/{cast.member.id}"
            )
        assert r.status_code == 404
        assert r.json()["code"] == "task.manager_not_found"


# ── What they may do ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestPowers:
    @pytest.mark.parametrize("role", ALL_ROLES)
    async def test_renaming_the_task(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, role: str
    ) -> None:
        with act_as(app, cast[role]):
            r = await async_client.patch(
                f"/api/v1/tasks/{cast.task.id}", json={"name": "Neue Theke"}
            )
        if role in MAY_EDIT:
            assert r.status_code == 200, r.text
            assert r.json()["name"] == "Neue Theke"
            assert r.json()["can_manage"] is True
        else:
            assert r.status_code == 403
            assert r.json()["code"] == "task.forbidden"

    @pytest.mark.parametrize("field", ["status", "team_id", "event_id"])
    async def test_admin_only_fields_are_refused_to_a_person_in_charge(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        field: str,
    ) -> None:
        team = EventTeam(event_id=cast.event.id, name="Kasse")
        db_session.add(team)
        await db_session.flush()
        value = {
            "status": "archived",
            "team_id": str(team.id),
            "event_id": str(cast.other_event.id),
        }[field]
        with act_as(app, cast.manager):
            r = await async_client.patch(
                f"/api/v1/tasks/{cast.task.id}", json={"name": "X", field: value}
            )
        assert r.status_code == 403
        assert r.json()["code"] == "task.admin_only_field"
        assert r.json()["fields"] == [field]
        await db_session.refresh(cast.task)
        assert cast.task.name != "X"

    async def test_admin_only_fields_sent_unchanged_are_ignored(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast
    ) -> None:
        """A form that always sends the whole task keeps working."""
        with act_as(app, cast.manager):
            r = await async_client.patch(
                f"/api/v1/tasks/{cast.task.id}",
                json={
                    "name": "Theke Nord",
                    "status": "published",
                    "team_id": None,
                    "event_id": str(cast.event.id),
                },
            )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Theke Nord"

    async def test_a_person_in_charge_cannot_delete_the_task(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast
    ) -> None:
        with act_as(app, cast.manager):
            r = await async_client.delete(f"/api/v1/tasks/{cast.task.id}")
        assert r.status_code == 403
        assert r.json()["code"] == "event.forbidden"

    async def test_a_person_in_charge_cannot_create_tasks(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast
    ) -> None:
        with act_as(app, cast.manager):
            r = await async_client.post(
                "/api/v1/tasks/with-shifts",
                json={
                    "name": "Neu",
                    "start_date": "2026-06-11",
                    "end_date": "2026-06-11",
                    "event_id": str(cast.event.id),
                    "schedule": SCHEDULE,
                },
            )
        assert r.status_code == 403


async def _create_shift(client: AsyncClient, _db: AsyncSession, cast: Cast) -> Response:
    return await client.post(
        "/api/v1/shifts/",
        json={
            "task_id": str(cast.task.id),
            "title": "Extra",
            "date": "2026-06-12",
            "start_time": "14:00:00",
            "end_time": "16:00:00",
        },
    )


async def _patch_shift(client: AsyncClient, db: AsyncSession, cast: Cast) -> Response:
    shift = await _shift(db, cast.task)
    return await client.patch(f"/api/v1/shifts/{shift.id}", json={"title": "Bar"})


async def _delete_shift(client: AsyncClient, db: AsyncSession, cast: Cast) -> Response:
    shift = await _shift(db, cast.task)
    return await client.delete(f"/api/v1/shifts/{shift.id}")


async def _add_shifts(client: AsyncClient, _db: AsyncSession, cast: Cast) -> Response:
    return await client.post(
        f"/api/v1/tasks/{cast.task.id}/add-shifts",
        json={
            "start_date": "2026-06-12",
            "end_date": "2026-06-12",
            "schedule": SCHEDULE,
        },
    )


async def _regenerate_dry(
    client: AsyncClient, db: AsyncSession, cast: Cast
) -> Response:
    await _shift(db, cast.task)
    return await client.post(
        f"/api/v1/tasks/{cast.task.id}/regenerate-shifts",
        params={"dry_run": True},
        json={"schedule": SCHEDULE},
    )


async def _regenerate(client: AsyncClient, db: AsyncSession, cast: Cast) -> Response:
    await _shift(db, cast.task)
    return await client.post(
        f"/api/v1/tasks/{cast.task.id}/regenerate-shifts", json={"schedule": SCHEDULE}
    )


async def _delete_batch(client: AsyncClient, db: AsyncSession, cast: Cast) -> Response:
    batch = await _batch(db, cast.task)
    await _shift(db, cast.task, batch=batch)
    return await client.delete(f"/api/v1/tasks/{cast.task.id}/batches/{batch.id}")


ShiftOp = Callable[[AsyncClient, AsyncSession, Cast], Awaitable[Response]]
SHIFT_OPS: dict[str, ShiftOp] = {
    "create shift": _create_shift,
    "edit shift": _patch_shift,
    "delete shift": _delete_shift,
    "add shifts": _add_shifts,
    "regenerate (dry run)": _regenerate_dry,
    "regenerate": _regenerate,
    "delete batch": _delete_batch,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("op", list(SHIFT_OPS))
@pytest.mark.parametrize("role", ALL_ROLES)
async def test_shift_writes(
    app: FastAPI,
    async_client: AsyncClient,
    db_session: AsyncSession,
    cast: Cast,
    op: str,
    role: str,
) -> None:
    with act_as(app, cast[role]):
        r = await SHIFT_OPS[op](async_client, db_session, cast)
    if role in MAY_EDIT:
        assert r.status_code in (200, 201, 204), r.text
    else:
        assert r.status_code == 403, r.text
        assert r.json()["code"] == "task.forbidden"


@pytest.mark.asyncio
async def test_write_responses_carry_can_manage(
    app: FastAPI, async_client: AsyncClient, db_session: AsyncSession, cast: Cast
) -> None:
    with act_as(app, cast.manager):
        added = await _add_shifts(async_client, db_session, cast)
        regenerated = await _regenerate_dry(async_client, db_session, cast)
    for r in (added, regenerated):
        assert r.json()["task"]["can_manage"] is True
        assert [m["user_id"] for m in r.json()["task"]["managers"]] == [
            str(cast.manager.id)
        ]


# ── The shift history rule ────────────────────────────────────────


@pytest.mark.asyncio
class TestShiftHistory:
    @pytest.fixture
    async def running(
        self, db_session: AsyncSession, cast: Cast, clock: dt.datetime
    ) -> Shift:
        """A booked 08:00-12:00 shift on the morning ``NOW`` falls in."""
        shift = await _shift(db_session, cast.task, date=NOW.date())
        await _book(db_session, shift, cast.member)
        return shift

    async def test_deleting_a_started_booked_shift(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, running: Shift
    ) -> None:
        with act_as(app, cast.manager):
            r = await async_client.delete(f"/api/v1/shifts/{running.id}")
        assert r.status_code == 403
        assert r.json()["code"] == "task.shift_history_admin_only"
        with act_as(app, cast.admin):
            r = await async_client.delete(f"/api/v1/shifts/{running.id}")
        assert r.status_code == 204

    async def test_extending_a_running_booked_shift(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, running: Shift
    ) -> None:
        with act_as(app, cast.manager):
            r = await async_client.patch(
                f"/api/v1/shifts/{running.id}", json={"end_time": "13:00:00"}
            )
        assert r.status_code == 200, r.text

    async def test_moving_a_future_booked_shift_into_the_past(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        clock: dt.datetime,
    ) -> None:
        future = await _shift(db_session, cast.task, date=dt.date(2026, 6, 12))
        await _book(db_session, future, cast.member)
        yesterday = (NOW.date() - dt.timedelta(days=1)).isoformat()
        with act_as(app, cast.manager):
            r = await async_client.patch(
                f"/api/v1/shifts/{future.id}", json={"date": yesterday}
            )
        assert r.status_code == 403
        assert r.json()["code"] == "task.shift_history_admin_only"
        with act_as(app, cast.admin):
            r = await async_client.patch(
                f"/api/v1/shifts/{future.id}", json={"date": yesterday}
            )
        assert r.status_code == 200

    async def test_deleting_a_batch_with_a_started_booked_shift(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        clock: dt.datetime,
    ) -> None:
        batch = await _batch(db_session, cast.task)
        started = await _shift(db_session, cast.task, date=NOW.date(), batch=batch)
        later = await _shift(
            db_session, cast.task, date=dt.date(2026, 6, 13), batch=batch
        )
        await _book(db_session, started, cast.member)
        with act_as(app, cast.manager):
            r = await async_client.delete(
                f"/api/v1/tasks/{cast.task.id}/batches/{batch.id}"
            )
        assert r.status_code == 403
        assert r.json()["code"] == "task.shift_history_admin_only"
        for row in (batch, started, later):
            assert await db_session.get(type(row), row.id, populate_existing=True)

    async def test_regenerating_a_started_booked_shift_away(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        running: Shift,
    ) -> None:
        url = f"/api/v1/tasks/{cast.task.id}/regenerate-shifts"
        with act_as(app, cast.manager):
            dry = await async_client.post(
                url, params={"dry_run": True}, json={"schedule": SCHEDULE}
            )
            real = await async_client.post(url, json={"schedule": SCHEDULE})
        assert dry.status_code == 200, dry.text
        [affected] = dry.json()["affected_bookings"]
        assert affected["locked"] is True
        assert affected["user_name"] == cast.member.name
        assert real.status_code == 403
        assert real.json()["code"] == "task.shift_history_admin_only"
        assert await db_session.get(Shift, running.id, populate_existing=True)

    async def test_an_admin_sees_nothing_locked(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, running: Shift
    ) -> None:
        with act_as(app, cast.admin):
            dry = await async_client.post(
                f"/api/v1/tasks/{cast.task.id}/regenerate-shifts",
                params={"dry_run": True},
                json={"schedule": SCHEDULE},
            )
        [affected] = dry.json()["affected_bookings"]
        assert affected["locked"] is False


# ── Drafts ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDrafts:
    @pytest_asyncio.fixture
    async def draft(self, db_session: AsyncSession, cast: Cast) -> Task:
        task = await _task(
            db_session, cast.event, cast.admin, name="Entwurf", status="draft"
        )
        await _in_charge(db_session, task, cast.manager)
        await _shift(db_session, task)
        return task

    async def _reads(
        self, client: AsyncClient, cast: Cast, draft: Task
    ) -> dict[str, Any]:
        event = str(cast.event.id)
        return {
            "get": await client.get(f"/api/v1/tasks/{draft.id}"),
            "list": await client.get("/api/v1/tasks/", params={"event_id": event}),
            "feed": await client.get(
                "/api/v1/tasks/feed",
                params={"event_id": event, "date_from": "2026-06-01"},
            ),
            "window": await client.get(
                f"/api/v1/tasks/{draft.id}/shift-window",
                params={"start_date": "2026-06-10"},
            ),
            "shifts": await client.get(
                "/api/v1/shifts/", params={"task_id": str(draft.id)}
            ),
        }

    async def test_its_person_in_charge_sees_it_everywhere(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, draft: Task
    ) -> None:
        with act_as(app, cast.manager):
            r = await self._reads(async_client, cast, draft)
        assert all(resp.status_code == 200 for resp in r.values()), {
            k: v.text for k, v in r.items()
        }
        assert r["get"].json()["can_manage"] is True
        for key in ("list", "feed"):
            [item] = [i for i in r[key].json()["items"] if i["id"] == str(draft.id)]
            assert item["can_manage"] is True
        assert len(r["window"].json()["shifts"]) == 1
        assert r["shifts"].json()["total"] == 1

    async def test_a_member_does_not(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, draft: Task
    ) -> None:
        with act_as(app, cast.member):
            r = await self._reads(async_client, cast, draft)
        for key in ("get", "window", "shifts"):
            assert r[key].status_code == 403
            assert r[key].json()["code"] == "task.not_published"
        for key in ("list", "feed"):
            assert str(draft.id) not in {i["id"] for i in r[key].json()["items"]}

    async def test_the_unfiltered_shift_list_follows_the_same_rule(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, draft: Task
    ) -> None:
        with act_as(app, cast.manager):
            mine = (await async_client.get("/api/v1/shifts/")).json()["items"]
        with act_as(app, cast.member):
            theirs = (await async_client.get("/api/v1/shifts/")).json()["items"]
        assert any(s["task_id"] == str(draft.id) for s in mine)
        assert not any(s["task_id"] == str(draft.id) for s in theirs)

    async def test_flags_on_a_published_task(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast
    ) -> None:
        with act_as(app, cast.member):
            r = await async_client.get(f"/api/v1/tasks/{cast.task.id}")
        assert r.json()["can_manage"] is False
        assert [m["name"] for m in r.json()["managers"]] == [cast.manager.name]


# ── Who sees whose contact details ────────────────────────────────


@pytest.mark.asyncio
class TestBookingLists:
    @pytest_asyncio.fixture
    async def booked(self, db_session: AsyncSession, cast: Cast) -> Shift:
        cast.member.phone_number = "+49 151 2222"
        db_session.add(cast.member)
        shift = await _shift(db_session, cast.task)
        await _book(db_session, shift, cast.member, notes="member note")
        await _book(db_session, shift, cast.sibling, notes="sibling note")
        return shift

    async def test_an_outsider_gets_404(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, booked: Shift
    ) -> None:
        with act_as(app, cast.outsider):
            r = await async_client.get(f"/api/v1/shifts/{booked.id}/bookings")
        assert r.status_code == 404

    @pytest.mark.parametrize("role", ["member", "sibling", "elsewhere"])
    async def test_members_see_names_and_only_their_own_details(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        cast: Cast,
        booked: Shift,
        role: str,
    ) -> None:
        viewer = cast[role]
        with act_as(app, viewer):
            r = await async_client.get(f"/api/v1/shifts/{booked.id}/bookings")
        assert r.status_code == 200
        for row in r.json():
            assert row["user_name"]
            own = row["user_id"] == str(viewer.id)
            assert (row["user_email"] is not None) == own
            assert (row["notes"] is not None) == own
            if not own:
                assert row["user_phone_number"] is None

    @pytest.mark.parametrize("role", ["manager", "admin"])
    async def test_people_in_charge_and_admins_see_everything(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        cast: Cast,
        booked: Shift,
        role: str,
    ) -> None:
        with act_as(app, cast[role]):
            r = await async_client.get(f"/api/v1/shifts/{booked.id}/bookings")
        by_user = {row["user_id"]: row for row in r.json()}
        member_row = by_user[str(cast.member.id)]
        assert member_row["user_email"] == cast.member.email
        assert member_row["user_phone_number"] == "+49 151 2222"
        assert member_row["notes"] == "member note"
        assert by_user[str(cast.sibling.id)]["notes"] == "sibling note"

    async def test_a_booker_reopens_their_shift_of_an_archived_task(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        booked: Shift,
    ) -> None:
        cast.task.status = "archived"
        db_session.add(cast.task)
        await db_session.flush()
        with act_as(app, cast.member):
            shift = await async_client.get(f"/api/v1/shifts/{booked.id}")
            roster = await async_client.get(f"/api/v1/shifts/{booked.id}/bookings")
        assert shift.status_code == 200
        assert roster.status_code == 200
        other = [r for r in roster.json() if r["user_id"] != str(cast.member.id)]
        assert other and all(r["user_email"] is None for r in other)
        with act_as(app, cast.elsewhere):
            shift = await async_client.get(f"/api/v1/shifts/{booked.id}")
            roster = await async_client.get(f"/api/v1/shifts/{booked.id}/bookings")
        for r in (shift, roster):
            assert r.status_code == 403
            assert r.json()["code"] == "task.not_published"

    @pytest.mark.parametrize(
        ("role", "sees_phone"),
        [("manager", True), ("admin", True), ("member", False), ("sibling", False)],
    )
    async def test_task_bookings_show_phones_to_those_in_charge(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        cast: Cast,
        booked: Shift,
        role: str,
        sees_phone: bool,
    ) -> None:
        with act_as(app, cast[role]):
            r = await async_client.get(f"/api/v1/tasks/{cast.task.id}/bookings")
        assert r.status_code == 200
        phones = {row["user_phone_number"] for row in r.json()}
        assert ("+49 151 2222" in phones) == sees_phone

    async def test_task_batches_are_404_for_an_outsider(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast
    ) -> None:
        with act_as(app, cast.outsider):
            r = await async_client.get(f"/api/v1/tasks/{cast.task.id}/batches")
        assert r.status_code == 404


# ── Lifecycle ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestLifecycle:
    @pytest.mark.parametrize("by", ["manager", "admin"])
    async def test_leaving_the_event_ends_it_for_good(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        by: str,
    ) -> None:
        """Leaving and being removed alike; re-joining does not bring it back."""
        with act_as(app, cast[by]):
            r = await async_client.delete(
                f"/api/v1/events/{cast.event.id}/members/{cast.manager.id}"
            )
        assert r.status_code == 204
        assert await _manager_rows(db_session, user_id=cast.manager.id) == []

        await _member(db_session, cast.manager, cast.event)
        assert await task_access(cast.manager, db_session, cast.task) is None

    async def test_rows_in_other_events_stay(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        with act_as(app, cast.elsewhere):
            await async_client.delete(
                f"/api/v1/events/{cast.event.id}/members/{cast.elsewhere.id}"
            )
        assert len(await _manager_rows(db_session, user_id=cast.elsewhere.id)) == 1

    async def test_an_ownership_transfer_ends_it_where_the_source_left(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        as_admin: None,
    ) -> None:
        source = await _user(db_session, "source-owner")
        owned = Event(
            name="Sommerfest",
            start_date=dt.date(2026, 6, 10),
            end_date=dt.date(2026, 6, 14),
            created_by_id=source.id,
        )
        db_session.add(owned)
        await db_session.flush()
        await _member(db_session, source, owned, role="owner")
        await _member(db_session, source, cast.event)
        owned_task = await _task(db_session, owned, source)
        await _in_charge(db_session, owned_task, source)
        await _in_charge(db_session, cast.task, source)
        team = EventTeam(event_id=owned.id, name="Grill")
        db_session.add(team)
        await db_session.flush()
        db_session.add(
            EventTeamMember(team_id=team.id, user_id=source.id, status="approved")
        )
        await db_session.flush()

        r = await async_client.post(
            f"/api/v1/users/{source.id}/transfer-ownership",
            json={"target_user_id": str(cast.admin.id)},
        )
        assert r.status_code == 200, r.text

        # Gone in the event the source no longer belongs to, kept where they do.
        assert [
            m.task_id for m in await _manager_rows(db_session, user_id=source.id)
        ] == [cast.task.id]
        teams = await db_session.execute(
            select(func.count())
            .select_from(EventTeamMember)
            .where(col(EventTeamMember.user_id) == source.id)
        )
        assert teams.scalar_one() == 0

    async def test_moving_the_task_drops_its_people_in_charge(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.patch(
                f"/api/v1/tasks/{cast.task.id}",
                json={"event_id": str(cast.other_event.id)},
            )
        assert r.status_code == 200, r.text
        assert r.json()["managers"] == []
        assert await _manager_rows(db_session, task_id=cast.task.id) == []

    async def test_deleting_the_task_takes_the_rows(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        task_id = cast.task.id
        with act_as(app, cast.admin):
            r = await async_client.delete(f"/api/v1/tasks/{task_id}")
        assert r.status_code == 204
        assert await _manager_rows(db_session, task_id=task_id) == []


# ── Naming them when the task is created ─────────────────────────


@pytest.mark.asyncio
class TestCreateWithManagers:
    def _body(self, cast: Cast, **extra: Any) -> dict[str, Any]:
        return {
            "name": "Neue Aufgabe",
            "start_date": "2026-06-11",
            "end_date": "2026-06-11",
            "event_id": str(cast.event.id),
            "schedule": SCHEDULE,
            **extra,
        }

    async def test_the_rows_are_created(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        ids = [str(cast.member.id), str(cast.manager.id), str(cast.member.id)]
        with act_as(app, cast.admin):
            r = await async_client.post(
                "/api/v1/tasks/with-shifts", json=self._body(cast, manager_ids=ids)
            )
        assert r.status_code == 201, r.text
        task = r.json()["task"]
        assert {m["user_id"] for m in task["managers"]} == {
            str(cast.member.id),
            str(cast.manager.id),
        }
        assert task["can_manage"] is True
        rows = await _manager_rows(db_session, task_id=uuid.UUID(task["id"]))
        assert {row.added_by_id for row in rows} == {cast.admin.id}

    async def test_a_non_member_is_refused(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                "/api/v1/tasks/with-shifts",
                json=self._body(cast, manager_ids=[str(cast.outsider.id)]),
            )
        assert r.status_code == 422
        assert r.json()["code"] == "task.manager_not_event_member"
        created = await db_session.execute(
            select(func.count())
            .select_from(Task)
            .where(col(Task.name) == "Neue Aufgabe")
        )
        assert created.scalar_one() == 0

    async def test_a_new_event_has_nobody_to_put_in_charge(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        cast: Cast,
        test_admin_user: User,
    ) -> None:
        """Only the superadmin creates a task together with a new event."""
        body = self._body(cast, manager_ids=[str(cast.member.id)])
        del body["event_id"]
        body["new_event"] = {
            "name": "Neues Fest",
            "start_date": "2026-06-11",
            "end_date": "2026-06-11",
        }
        with act_as(app, test_admin_user):
            r = await async_client.post("/api/v1/tasks/with-shifts", json=body)
        assert r.status_code == 422
        assert r.json()["code"] == "task.manager_not_event_member"
