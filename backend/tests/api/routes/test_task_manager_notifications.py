"""The routes that name people in charge queue the right notice, or none.

The dispatchers themselves are covered in ``tests/logic/test_notification_
triggers.py``. Here they are replaced by recorders (as in
``test_team_notifications.py``), so each test asserts what the background task
was *asked* to do: who was put in charge or taken off, by whom, and that
nothing is queued when someone acts on themselves or the request is refused.

The cast, all in ``test_event``: ``test_event_admin_user`` is the organiser,
``test_user`` a plain member, ``anna`` and ``ben`` two more members, and
``ben`` is already in charge of ``test_task``.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.api.routes.tasks import managers as managers_routes
from app.api.routes.tasks import shifts as shifts_routes
from app.logic.notifications import triggers
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from tests.fixtures.client import act_as

Calls = dict[str, list[dict[str, Any]]]

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
    member: User
    anna: User
    ben: User
    outsider: User


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> Calls:
    """Record the people-in-charge dispatches instead of running them.

    The route modules import the dispatchers by name, so the recorders go onto
    those modules. They go onto the trigger module as well, so a route that
    imported one lazily (as the clone does with ``dispatch_event_cloned``)
    would be caught too.
    """
    calls: Calls = {"added": [], "removed": []}

    async def _added(
        *, task_id: uuid.UUID, user_ids: list[uuid.UUID], actor_id: uuid.UUID
    ) -> None:
        calls["added"].append(
            {"task_id": task_id, "user_ids": user_ids, "actor_id": actor_id}
        )

    async def _removed(
        *, task_id: uuid.UUID, user_id: uuid.UUID, actor_id: uuid.UUID
    ) -> None:
        calls["removed"].append(
            {"task_id": task_id, "user_id": user_id, "actor_id": actor_id}
        )

    for module in (managers_routes, shifts_routes, triggers):
        monkeypatch.setattr(module, "dispatch_task_manager_added", _added)
    for module in (managers_routes, triggers):
        monkeypatch.setattr(module, "dispatch_task_manager_removed", _removed)
    return calls


async def _member(db: AsyncSession, event: Event, key: str) -> User:
    user = User(
        subject=f"local|{key}-notice",
        email=f"{key}.notice@example.com",
        name=key.capitalize(),
        roles=[],
        is_active=True,
    )
    db.add(user)
    await db.flush()
    db.add(EventMembership(user_id=user.id, event_id=event.id, role="member"))
    await db.flush()
    return user


@pytest_asyncio.fixture
async def cast(
    db_session: AsyncSession,
    test_event: Event,
    test_task: Task,
    test_event_admin_user: User,
    test_user: User,
    test_outsider_user: User,
) -> Cast:
    anna = await _member(db_session, test_event, "anna")
    ben = await _member(db_session, test_event, "ben")
    db_session.add(TaskManager(task_id=test_task.id, user_id=ben.id))
    await db_session.flush()
    return Cast(
        event=test_event,
        task=test_task,
        admin=test_event_admin_user,
        member=test_user,
        anna=anna,
        ben=ben,
        outsider=test_outsider_user,
    )


def _managers_url(cast: Cast) -> str:
    return f"/api/v1/tasks/{cast.task.id}/managers"


# ── POST /tasks/{id}/managers ─────────────────────────────────────


@pytest.mark.asyncio
class TestAdding:
    async def test_an_admin_puts_a_member_in_charge(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                _managers_url(cast), json={"user_id": str(cast.anna.id)}
            )

        assert r.status_code == 201, r.text
        assert queued == {
            "added": [
                {
                    "task_id": cast.task.id,
                    "user_ids": [cast.anna.id],
                    "actor_id": cast.admin.id,
                }
            ],
            "removed": [],
        }

    async def test_an_admin_who_names_themselves_is_not_told(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                _managers_url(cast), json={"user_id": str(cast.admin.id)}
            )

        assert r.status_code == 201, r.text
        assert queued == {"added": [], "removed": []}

    async def test_a_non_member_is_refused_and_nobody_is_told(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                _managers_url(cast), json={"user_id": str(cast.outsider.id)}
            )

        assert r.status_code == 422
        assert queued == {"added": [], "removed": []}

    async def test_someone_already_in_charge_is_not_told_again(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                _managers_url(cast), json={"user_id": str(cast.ben.id)}
            )

        assert r.status_code == 409
        assert r.json()["code"] == "task.manager_already"
        assert queued == {"added": [], "removed": []}

    async def test_a_member_may_not_and_nobody_is_told(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        with act_as(app, cast.member):
            r = await async_client.post(
                _managers_url(cast), json={"user_id": str(cast.anna.id)}
            )

        assert r.status_code == 403
        assert queued == {"added": [], "removed": []}


# ── DELETE /tasks/{id}/managers/{user_id} ─────────────────────────


@pytest.mark.asyncio
class TestRemoving:
    async def test_an_admin_takes_someone_off(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.delete(f"{_managers_url(cast)}/{cast.ben.id}")

        assert r.status_code == 204
        assert queued == {
            "added": [],
            "removed": [
                {
                    "task_id": cast.task.id,
                    "user_id": cast.ben.id,
                    "actor_id": cast.admin.id,
                }
            ],
        }

    async def test_stepping_down_tells_nobody(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        with act_as(app, cast.ben):
            r = await async_client.delete(f"{_managers_url(cast)}/{cast.ben.id}")

        assert r.status_code == 204
        assert queued == {"added": [], "removed": []}

    async def test_an_admin_stepping_down_tells_nobody(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
    ) -> None:
        db_session.add(TaskManager(task_id=cast.task.id, user_id=cast.admin.id))
        await db_session.flush()

        with act_as(app, cast.admin):
            r = await async_client.delete(f"{_managers_url(cast)}/{cast.admin.id}")

        assert r.status_code == 204
        assert queued == {"added": [], "removed": []}

    async def test_removing_someone_not_in_charge_tells_nobody(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.delete(f"{_managers_url(cast)}/{cast.anna.id}")

        assert r.status_code == 404
        assert queued == {"added": [], "removed": []}

    async def test_a_member_may_not_and_nobody_is_told(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        with act_as(app, cast.member):
            r = await async_client.delete(f"{_managers_url(cast)}/{cast.ben.id}")

        assert r.status_code == 403
        assert queued == {"added": [], "removed": []}


# ── POST /tasks/with-shifts ───────────────────────────────────────


def _create_body(cast: Cast, **extra: Any) -> dict[str, Any]:
    return {
        "name": "Grill",
        "start_date": "2026-06-11",
        "end_date": "2026-06-11",
        "event_id": str(cast.event.id),
        "schedule": SCHEDULE,
        **extra,
    }


@pytest.mark.asyncio
class TestCreating:
    async def test_one_call_names_everyone_but_the_creator(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        ids = [cast.anna.id, cast.admin.id, cast.ben.id]
        with act_as(app, cast.admin):
            r = await async_client.post(
                "/api/v1/tasks/with-shifts",
                json=_create_body(cast, manager_ids=[str(i) for i in ids]),
            )

        assert r.status_code == 201, r.text
        task_id = uuid.UUID(r.json()["task"]["id"])
        assert queued == {
            "added": [
                {
                    "task_id": task_id,
                    "user_ids": [cast.anna.id, cast.ben.id],
                    "actor_id": cast.admin.id,
                }
            ],
            "removed": [],
        }

    async def test_naming_only_yourself_queues_nothing(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                "/api/v1/tasks/with-shifts",
                json=_create_body(cast, manager_ids=[str(cast.admin.id)]),
            )

        assert r.status_code == 201, r.text
        assert queued == {"added": [], "removed": []}

    async def test_nobody_named_queues_nothing(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                "/api/v1/tasks/with-shifts", json=_create_body(cast)
            )

        assert r.status_code == 201, r.text
        assert queued == {"added": [], "removed": []}

    async def test_a_refused_create_queues_nothing(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                "/api/v1/tasks/with-shifts",
                json=_create_body(
                    cast, manager_ids=[str(cast.anna.id), str(cast.outsider.id)]
                ),
            )

        assert r.status_code == 422
        assert queued == {"added": [], "removed": []}


# ── POST /events/{id}/clone ───────────────────────────────────────


@pytest.mark.asyncio
async def test_cloning_with_members_tells_no_one_they_are_in_charge(
    app: FastAPI,
    async_client: AsyncClient,
    db_session: AsyncSession,
    cast: Cast,
    queued: Calls,
) -> None:
    """The clone copies people in charge with the roster, silently.

    The new roster hears about the event through ``event.cloned``; a notice per
    task on top would bury it.
    """
    with act_as(app, cast.admin):
        r = await async_client.post(
            f"/api/v1/events/{cast.event.id}/clone",
            json={
                "name": "Kirchentags Woche 2027",
                "start_date": dt.date(2027, 6, 9).isoformat(),
                "tasks": [{"source_task_id": str(cast.task.id)}],
                "copy_members": True,
            },
        )

    assert r.status_code == 201, r.text
    new_event_id = uuid.UUID(r.json()["event"]["id"])
    copied = await db_session.execute(
        select(col(TaskManager.user_id))
        .join(Task, col(Task.id) == col(TaskManager.task_id))
        .where(col(Task.event_id) == new_event_id)
    )
    # Not vacuous: Ben is in charge of the copy.
    assert list(copied.scalars()) == [cast.ben.id]
    assert queued == {"added": [], "removed": []}
