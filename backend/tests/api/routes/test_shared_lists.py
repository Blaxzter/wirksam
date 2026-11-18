"""Managing shared lists through the API: create, edit, pause, resume, end,
rotate, in bulk and all at once, and the event setting that stops people in
charge from sharing (``app/api/routes/shared_lists.py``).

The cast, all in ``test_event``:

- the event admin, ``test_event_admin_user`` (``as_event_admin``);
- ``manager``, a member in charge of ``test_task``;
- ``test_user``, a plain member, who ``async_client`` signs in as by default.

The event's clock stands at 2026-06-10 12:00, the day before ``test_task``'s
shifts. Which shifts a list offers and when it expires are pinned in
``tests/logic/test_shared_list_offer.py``; the tables in
``test_shared_lists_overview.py``; the full matrix of the transitions in
``tests/logic/test_shared_list_manage.py``.
"""

import datetime as dt
import uuid
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.crud.shared_list import shared_list as crud_shared_list
from app.models.booking import Booking
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.event_team import EventTeam
from app.models.shared_list import (
    SharedList,
    SharedListExcludedShift,
    SharedListTask,
)
from app.models.shift import Shift
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from tests.fixtures.client import act_as
from tests.fixtures.clock import set_wall_clock
from tests.fixtures.sandbox import SandboxSetup
from tests.fixtures.shared_lists import CountQueries, SharedListFactory

NOW = dt.datetime(2026, 6, 10, 12, 0)
TODAY = NOW.date()
DAY1 = dt.date(2026, 6, 11)
DAY2 = dt.date(2026, 6, 12)
DAY3 = dt.date(2026, 6, 13)


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    set_wall_clock(monkeypatch, NOW)


async def _task(
    db: AsyncSession,
    event: Event,
    creator: User,
    name: str,
    *,
    status: str = "published",
    team_id: uuid.UUID | None = None,
) -> Task:
    task = Task(
        name=name,
        start_date=DAY1,
        end_date=DAY3,
        status=status,
        created_by_id=creator.id,
        event_id=event.id,
        team_id=team_id,
    )
    db.add(task)
    await db.flush()
    return task


async def _shift(
    db: AsyncSession,
    task: Task,
    day: dt.date,
    start: dt.time | None = dt.time(10),
    *,
    max_bookings: int = 2,
) -> Shift:
    shift = Shift(
        task_id=task.id,
        title=task.name,
        date=day,
        start_time=start,
        end_time=None,
        max_bookings=max_bookings,
    )
    db.add(shift)
    await db.flush()
    return shift


async def _book(db: AsyncSession, shift: Shift, user: User) -> None:
    db.add(Booking(shift_id=shift.id, user_id=user.id, status="confirmed"))
    await db.flush()


async def _member(db: AsyncSession, event: Event, key: str) -> User:
    user = User(
        subject=f"local|{key}-lists",
        email=f"{key}.lists@example.com",
        name=key.capitalize(),
        roles=[],
        is_active=True,
    )
    db.add(user)
    await db.flush()
    db.add(EventMembership(user_id=user.id, event_id=event.id, role="member"))
    await db.flush()
    return user


def _problem(r: Response, status: int, code: str) -> dict[str, Any]:
    assert r.status_code == status, r.text
    body: dict[str, Any] = r.json()
    assert body["code"] == code, body
    return body


@pytest_asyncio.fixture
async def shifts(db_session: AsyncSession, test_task: Task) -> list[Shift]:
    """Three shifts of ``test_task``, one a day, two places each."""
    return [await _shift(db_session, test_task, day) for day in (DAY1, DAY2, DAY3)]


@pytest_asyncio.fixture
async def bar(db_session: AsyncSession, test_event: Event, test_user: User) -> Task:
    """A second published task in ``test_event``, with one shift ahead."""
    task = await _task(db_session, test_event, test_user, "Bar")
    await _shift(db_session, task, DAY1, dt.time(18))
    return task


@pytest_asyncio.fixture
async def manager(db_session: AsyncSession, test_event: Event, test_task: Task) -> User:
    """A member of ``test_event`` in charge of ``test_task``."""
    user = await _member(db_session, test_event, "manager")
    db_session.add(TaskManager(task_id=test_task.id, user_id=user.id))
    await db_session.flush()
    return user


async def _create(
    client: AsyncClient, event: Event, task_ids: list[uuid.UUID], **body: Any
) -> Response:
    return await client.post(
        f"/api/v1/events/{event.id}/shared-lists",
        json={
            "title": "Helfer gesucht",
            "task_ids": [str(t) for t in task_ids],
            **body,
        },
    )


@pytest.mark.asyncio
class TestCreate:
    async def test_an_event_admin_shares_a_task(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_event_admin_user: User,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        r = await _create(
            async_client,
            test_event,
            [test_task.id],
            title="  Pfingsten: Wer hilft mit?  ",
            intro="   ",
            share_note="WhatsApp-Gruppe",
            excluded_shift_ids=[str(shifts[1].id)],
        )

        assert r.status_code == 201, r.text
        body = r.json()
        assert len(body["code"]) == 12
        assert body["title"] == "Pfingsten: Wer hilft mit?"
        assert body["intro"] is None
        assert body["share_note"] == "WhatsApp-Gruppe"
        assert body["status"] == body["effective_status"] == "live"
        assert body["access"] == "admin"
        assert body["created_by_name"] == test_event_admin_user.name
        assert body["tasks"] == [{"id": str(test_task.id), "name": test_task.name}]
        assert body["task_ids"] == [str(test_task.id)]
        assert body["excluded_shift_ids"] == [str(shifts[1].id)]
        assert body["excluded_shift_count"] == 1
        assert body["only_days"] == [DAY1.isoformat(), DAY3.isoformat()]
        assert (body["capacity"], body["free"]) == (4, 4)
        assert body["closes_at"] == dt.datetime.combine(DAY3, dt.time(10)).isoformat()
        # The defaults: an address required, no phone, no names, no limit.
        assert body["ask_email"] == "required"
        assert body["ask_phone"] == "off"
        assert body["show_names"] == "none"
        assert body["max_per_person"] is None
        assert body["ends_mode"] == "last_shift"
        assert body["event"]["id"] == str(test_event.id)
        assert body["detail_tasks"][0]["offered"] is True
        assert body["detail_tasks"][0]["shift_count"] == 2

        stored = await crud_shared_list.get(
            db_session, shared_list_id=uuid.UUID(body["id"])
        )
        assert stored is not None
        assert stored.created_by_id == test_event_admin_user.id

    async def test_a_person_in_charge_shares_their_own_task(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        test_event: Event,
        test_task: Task,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        with act_as(app, manager):
            r = await _create(async_client, test_event, [test_task.id])

        assert r.status_code == 201, r.text
        assert r.json()["access"] == "manager"
        assert r.json()["created_by_name"] == "Manager"

    async def test_a_person_in_charge_cannot_share_someone_elses_task(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        test_event: Event,
        test_task: Task,
        bar: Task,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        with act_as(app, manager):
            r = await _create(async_client, test_event, [test_task.id, bar.id])

        body = _problem(r, 403, "shared_list.tasks_forbidden")
        assert body["task_ids"] == [str(bar.id)]

    async def test_a_plain_member_cannot_share(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_task: Task,
        shifts: list[Shift],
    ) -> None:
        r = await _create(async_client, test_event, [test_task.id])
        _problem(r, 403, "shared_list.tasks_forbidden")

    @pytest.mark.parametrize(
        ("kind", "code"),
        [
            ("team", "shared_list.task_team_locked"),
            ("draft", "shared_list.task_not_published"),
            ("elsewhere", "shared_list.task_not_in_event"),
        ],
    )
    async def test_a_task_no_list_can_offer_is_refused(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_private_event: Event,
        test_task: Task,
        test_user: User,
        shifts: list[Shift],
        as_event_admin: None,
        kind: str,
        code: str,
    ) -> None:
        if kind == "team":
            team = EventTeam(event_id=test_event.id, name="Sanitäter")
            db_session.add(team)
            await db_session.flush()
            task = await _task(
                db_session, test_event, test_user, "Sani", team_id=team.id
            )
        elif kind == "draft":
            task = await _task(
                db_session, test_event, test_user, "Entwurf", status="draft"
            )
        else:
            task = await _task(db_session, test_private_event, test_user, "Anderswo")
        await _shift(db_session, task, DAY1)

        r = await _create(async_client, test_event, [test_task.id, task.id])

        body = _problem(r, 422, code)
        assert body["task_ids"] == [str(task.id)]

    async def test_excluded_ids_of_other_shifts_are_dropped(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_task: Task,
        bar: Task,
        shifts: list[Shift],
        db_session: AsyncSession,
        as_event_admin: None,
    ) -> None:
        bar_shift = (
            await db_session.execute(select(Shift).where(col(Shift.task_id) == bar.id))
        ).scalar_one()

        r = await _create(
            async_client,
            test_event,
            [test_task.id],
            excluded_shift_ids=[
                str(shifts[0].id),
                str(bar_shift.id),
                str(uuid.uuid4()),
            ],
        )

        assert r.status_code == 201, r.text
        assert r.json()["excluded_shift_ids"] == [str(shifts[0].id)]

    async def test_a_list_with_no_shift_ahead_is_refused(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        as_event_admin: None,
    ) -> None:
        await _shift(db_session, test_task, TODAY, dt.time(8))  # has started
        ahead = await _shift(db_session, test_task, DAY1)

        r = await _create(
            async_client, test_event, [test_task.id], excluded_shift_ids=[str(ahead.id)]
        )

        _problem(r, 422, "shared_list.no_shifts")

    async def test_a_list_of_full_shifts_is_refused(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_user: User,
        as_event_admin: None,
    ) -> None:
        full = await _shift(db_session, test_task, DAY1, max_bookings=1)
        await _book(db_session, full, test_user)

        r = await _create(async_client, test_event, [test_task.id])

        _problem(r, 422, "shared_list.no_free_places")

    @pytest.mark.parametrize(
        ("ends_on", "ok"),
        [
            (TODAY - dt.timedelta(days=1), False),
            (TODAY, True),
            (DAY3, True),
            (DAY3 + dt.timedelta(days=1), False),
            (None, False),
        ],
    )
    async def test_the_closing_day_lies_between_today_and_the_last_shift(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_task: Task,
        shifts: list[Shift],
        as_event_admin: None,
        ends_on: dt.date | None,
        ok: bool,
    ) -> None:
        r = await _create(
            async_client,
            test_event,
            [test_task.id],
            ends_mode="date",
            ends_on=ends_on.isoformat() if ends_on else None,
        )

        if ok:
            assert r.status_code == 201, r.text
            assert ends_on is not None
            assert r.json()["ends_on"] == ends_on.isoformat()
        else:
            body = _problem(r, 422, "shared_list.ends_on_invalid")
            assert body["last_shift_date"] == DAY3.isoformat()

    async def test_a_closing_day_without_closing_on_a_day_is_ignored(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_task: Task,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        r = await _create(
            async_client,
            test_event,
            [test_task.id],
            ends_mode="manual",
            ends_on=DAY2.isoformat(),
        )

        assert r.status_code == 201, r.text
        assert r.json()["ends_mode"] == "manual"
        assert r.json()["ends_on"] is None
        assert r.json()["closes_at"] is None

    async def test_an_unpublished_event_cannot_share(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_draft_event: Event,
        test_user: User,
        as_event_admin: None,
    ) -> None:
        task = await _task(db_session, test_draft_event, test_user, "Kasse")
        await _shift(db_session, task, DAY1)

        r = await _create(async_client, test_draft_event, [task.id])

        _problem(r, 409, "shared_list.event_not_published")

    async def test_an_event_holds_a_bounded_number_of_lists(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        """Ended lists count: the cap bounds what every view evaluates."""
        monkeypatch.setattr(settings, "SHARED_LISTS_PER_EVENT", 2)
        await make_shared_list()
        await make_shared_list(status="ended")

        r = await _create(async_client, test_event, [test_task.id])

        body = _problem(r, 409, "shared_list.too_many")
        assert body["max"] == 2

    async def test_a_demo_event_shares_too(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
    ) -> None:
        """The demo's guest, as its owner, tries sharing like an organiser:
        its lists mail nobody (``test_public_shared_lists.py``)."""
        await db_session.execute(
            update(EventMembership)
            .where(
                col(EventMembership.event_id) == test_sandbox.event.id,
                col(EventMembership.user_id) == test_sandbox.guest.id,
            )
            .values(role="owner")
        )
        task = await _task(db_session, test_sandbox.event, test_sandbox.guest, "Demo")
        await _shift(db_session, task, DAY1)

        with act_as(app, test_sandbox.guest):
            r = await _create(async_client, test_sandbox.event, [task.id])

        assert r.status_code == 201, r.text
        assert r.json()["status"] == "live"

    async def test_the_superadmin_does_not_find_a_demo_event(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
        as_admin: None,
    ) -> None:
        task = await _task(db_session, test_sandbox.event, test_sandbox.guest, "Demo")

        r = await _create(async_client, test_sandbox.event, [task.id])

        _problem(r, 404, "event.not_found")

    async def test_people_in_charge_cannot_share_while_the_event_says_no(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_event_admin_user: User,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        test_event.managers_share_lists = False
        db_session.add(test_event)
        await db_session.flush()

        with act_as(app, manager):
            refused = await _create(async_client, test_event, [test_task.id])
        with act_as(app, test_event_admin_user):
            allowed = await _create(async_client, test_event, [test_task.id])

        _problem(refused, 403, "shared_list.managers_disabled")
        assert allowed.status_code == 201, allowed.text


@pytest.mark.asyncio
class TestSwitchedOff:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/api/v1/events/{event}/shared-lists"),
            ("GET", "/api/v1/events/{event}/shared-lists/overview"),
            ("GET", "/api/v1/events/{event}/shared-lists/reusable?task_id={list}"),
            ("POST", "/api/v1/events/{event}/shared-lists"),
            ("GET", "/api/v1/shared-lists/{list}"),
            ("POST", "/api/v1/shared-lists/{list}/pause"),
        ],
    )
    async def test_every_route_is_gone(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        test_event: Event,
        test_shared_list: SharedList,
        as_event_admin: None,
        method: str,
        path: str,
    ) -> None:
        monkeypatch.setattr(settings, "SHARED_LISTS_ENABLED", False)

        r = await async_client.request(
            method,
            path.format(event=test_event.id, list=test_shared_list.id),
            json={"title": "x", "task_ids": [str(uuid.uuid4())]},
        )

        _problem(r, 404, "shared_list.disabled")


@pytest.mark.asyncio
class TestRead:
    async def test_a_person_in_charge_of_some_tasks_reads_it_without_changing_it(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_task: Task,
        bar: Task,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        mixed = await make_shared_list(tasks=[test_task, bar], status="paused")

        with act_as(app, manager):
            r = await async_client.get(f"/api/v1/shared-lists/{mixed.id}")

        assert r.status_code == 200, r.text
        assert r.json()["access"] == "viewer"
        assert r.json()["issue"] is None

    async def test_someone_outside_the_list_does_not_find_it(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        bar: Task,
        manager: User,
        test_outsider_user: User,
    ) -> None:
        theirs = await make_shared_list(tasks=[bar])

        with act_as(app, manager):
            r = await async_client.get(f"/api/v1/shared-lists/{theirs.id}")
        _problem(r, 404, "shared_list.not_found")
        with act_as(app, test_outsider_user):
            r = await async_client.get(f"/api/v1/shared-lists/{theirs.id}")
        _problem(r, 404, "shared_list.not_found")
        r = await async_client.get(f"/api/v1/shared-lists/{uuid.uuid4()}")
        _problem(r, 404, "shared_list.not_found")

    async def test_the_detail_says_why_a_task_is_not_offered(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_private_event: Event,
        test_task: Task,
        bar: Task,
        test_user: User,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        """Moving a task takes it off its lists; should a link survive, the
        list still names it, and offers and counts nothing of it."""
        team = EventTeam(event_id=test_event.id, name="Sanitäter")
        db_session.add(team)
        await db_session.flush()
        sani = await _task(db_session, test_event, test_user, "Sani")
        moved = await _task(db_session, test_event, test_user, "Umgezogen")
        await _shift(db_session, moved, DAY1)
        shared_list = await make_shared_list(tasks=[test_task, bar, sani, moved])
        bar.status = "draft"
        sani.team_id = team.id
        moved.event_id = test_private_event.id
        db_session.add_all([bar, sani, moved])
        await db_session.flush()

        r = await async_client.get(f"/api/v1/shared-lists/{shared_list.id}")

        assert r.status_code == 200, r.text
        body = r.json()
        reasons = {t["name"]: t["not_offered_reason"] for t in body["detail_tasks"]}
        assert reasons == {
            test_task.name: None,
            "Bar": "not_published",
            "Sani": "team_locked",
            "Umgezogen": "moved",
        }
        assert len(body["task_ids"]) == 4
        assert [t["name"] for t in body["tasks"]] == [test_task.name, "Bar", "Sani"]
        assert body["capacity"] == 6


@pytest.mark.asyncio
class TestUpdate:
    async def test_an_edit_keeps_the_link(
        self,
        async_client: AsyncClient,
        test_shared_list: SharedList,
        bar: Task,
        test_task: Task,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        code = test_shared_list.code

        r = await async_client.patch(
            f"/api/v1/shared-lists/{test_shared_list.id}",
            json={
                "title": "Neu",
                "task_ids": [str(bar.id), str(test_task.id)],
                "excluded_shift_ids": [str(shifts[2].id)],
                "show_names": "first",
                "max_per_person": 2,
                "ask_phone": "optional",
            },
        )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == code
        assert body["title"] == "Neu"
        assert body["task_ids"] == [str(bar.id), str(test_task.id)]
        assert body["excluded_shift_ids"] == [str(shifts[2].id)]
        assert (body["show_names"], body["max_per_person"]) == ("first", 2)
        assert body["ask_phone"] == "optional"

    async def test_null_keeps_what_always_has_a_value_and_clears_the_rest(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        test_shared_list.max_per_person = 3
        test_shared_list.share_note = "Aushang"
        db_session.add(test_shared_list)
        await db_session.flush()

        r = await async_client.patch(
            f"/api/v1/shared-lists/{test_shared_list.id}",
            json={
                "title": None,
                "task_ids": None,
                "ask_email": None,
                "max_per_person": None,
                "share_note": None,
            },
        )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["title"] == "Helfer gesucht"
        assert body["ask_email"] == "required"
        assert len(body["task_ids"]) == 1
        assert body["max_per_person"] is None
        assert body["share_note"] is None

    async def test_extending_a_list_drops_its_closing_day(
        self,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        """ "Verlängern" on a list whose day is over."""
        shared_list = await make_shared_list(
            ends_mode="date", ends_on=TODAY - dt.timedelta(days=1)
        )

        r = await async_client.patch(
            f"/api/v1/shared-lists/{shared_list.id}",
            json={"ends_mode": "last_shift", "ends_on": None},
        )

        assert r.status_code == 200, r.text
        assert r.json()["ends_mode"] == "last_shift"
        assert r.json()["ends_on"] is None
        assert r.json()["effective_status"] == "live"

    async def test_a_changed_closing_day_is_checked(
        self,
        async_client: AsyncClient,
        test_shared_list: SharedList,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        r = await async_client.patch(
            f"/api/v1/shared-lists/{test_shared_list.id}",
            json={"ends_mode": "date", "ends_on": "2026-07-01"},
        )

        body = _problem(r, 422, "shared_list.ends_on_invalid")
        assert body["last_shift_date"] == DAY3.isoformat()

    async def test_a_new_title_needs_no_check_of_the_shifts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
        as_event_admin: None,
    ) -> None:
        """The list's task was unpublished meanwhile; it can still be renamed."""
        test_task.status = "draft"
        db_session.add(test_task)
        await db_session.flush()

        r = await async_client.patch(
            f"/api/v1/shared-lists/{test_shared_list.id}", json={"title": "Später"}
        )

        assert r.status_code == 200, r.text
        assert r.json()["title"] == "Später"
        assert r.json()["effective_status"] == "expired"

    async def test_new_tasks_must_be_the_callers(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_task: Task,
        bar: Task,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        shared_list = await make_shared_list(created_by=manager)

        with act_as(app, manager):
            r = await async_client.patch(
                f"/api/v1/shared-lists/{shared_list.id}",
                json={"task_ids": [str(test_task.id), str(bar.id)]},
            )

        body = _problem(r, 403, "shared_list.tasks_forbidden")
        assert body["task_ids"] == [str(bar.id)]

    async def test_a_viewer_cannot_edit(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_task: Task,
        bar: Task,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        mixed = await make_shared_list(tasks=[test_task, bar])

        with act_as(app, manager):
            r = await async_client.patch(
                f"/api/v1/shared-lists/{mixed.id}", json={"title": "Meins"}
            )

        _problem(r, 403, "shared_list.forbidden")

    async def test_an_ended_list_cannot_be_edited(
        self,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        ended = await make_shared_list(status="ended")

        r = await async_client.patch(
            f"/api/v1/shared-lists/{ended.id}", json={"title": "Wieder da"}
        )

        _problem(r, 409, "shared_list.ended")


@pytest.mark.asyncio
class TestTransitions:
    async def test_pause_resume_rotate_end(
        self,
        async_client: AsyncClient,
        test_shared_list: SharedList,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        base = f"/api/v1/shared-lists/{test_shared_list.id}"
        old_code = test_shared_list.code

        paused = await async_client.post(f"{base}/pause")
        assert paused.status_code == 200, paused.text
        assert paused.json()["status"] == "paused"
        assert paused.json()["paused_at"] is not None
        again = await async_client.post(f"{base}/pause")
        assert again.status_code == 200
        assert again.json()["paused_at"] == paused.json()["paused_at"]

        resumed = await async_client.post(f"{base}/resume")
        assert resumed.json()["status"] == "live"
        assert resumed.json()["paused_at"] is None

        rotated = await async_client.post(f"{base}/rotate")
        assert rotated.status_code == 200, rotated.text
        assert rotated.json()["code"] != old_code
        assert rotated.json()["rotated_at"] is not None

        ended = await async_client.post(f"{base}/end")
        assert ended.json()["status"] == ended.json()["effective_status"] == "ended"
        assert ended.json()["ended_at"] is not None
        assert (await async_client.post(f"{base}/end")).status_code == 200
        for action in ("pause", "resume", "rotate"):
            _problem(
                await async_client.post(f"{base}/{action}"), 409, "shared_list.ended"
            )

    async def test_a_viewer_cannot_change_it(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_task: Task,
        bar: Task,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        mixed = await make_shared_list(tasks=[test_task, bar])

        with act_as(app, manager):
            r = await async_client.post(f"/api/v1/shared-lists/{mixed.id}/pause")

        _problem(r, 403, "shared_list.forbidden")

    async def test_people_in_charge_may_only_stop_lists_while_the_event_says_no(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        live = await make_shared_list(created_by=manager)
        paused = await make_shared_list(created_by=manager, status="paused")
        test_event.managers_share_lists = False
        db_session.add(test_event)
        await db_session.flush()

        with act_as(app, manager):
            resume = await async_client.post(f"/api/v1/shared-lists/{paused.id}/resume")
            rotate = await async_client.post(f"/api/v1/shared-lists/{live.id}/rotate")
            edit = await async_client.patch(
                f"/api/v1/shared-lists/{live.id}", json={"title": "x"}
            )
            pause = await async_client.post(f"/api/v1/shared-lists/{live.id}/pause")
            end = await async_client.post(f"/api/v1/shared-lists/{paused.id}/end")

        for refused in (resume, rotate, edit):
            _problem(refused, 403, "shared_list.managers_disabled")
        assert pause.status_code == 200, pause.text
        assert end.status_code == 200, end.text


@pytest.mark.asyncio
class TestBulk:
    async def test_each_list_succeeds_or_is_skipped_on_its_own(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_private_event: Event,
        test_task: Task,
        bar: Task,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        mine = await make_shared_list(created_by=manager)
        already = await make_shared_list(created_by=manager, status="paused")
        ended = await make_shared_list(created_by=manager, status="ended")
        mixed = await make_shared_list(tasks=[test_task, bar])
        theirs = await make_shared_list(tasks=[bar])
        elsewhere = await make_shared_list(event=test_private_event, tasks=[])
        unknown = uuid.uuid4()
        ids = [
            mine.id,
            already.id,
            ended.id,
            mixed.id,
            theirs.id,
            elsewhere.id,
            unknown,
        ]

        with act_as(app, manager):
            r = await async_client.post(
                f"/api/v1/events/{mine.event_id}/shared-lists/bulk",
                json={"action": "pause", "list_ids": [str(i) for i in ids]},
            )

        assert r.status_code == 200, r.text
        assert r.json()["changed"] == [str(mine.id)]
        skipped = {uuid.UUID(s["id"]): s["code"] for s in r.json()["skipped"]}
        assert skipped == {
            ended.id: "shared_list.ended",
            mixed.id: "shared_list.forbidden",
            theirs.id: "shared_list.not_found",
            elsewhere.id: "shared_list.not_found",
            unknown: "shared_list.not_found",
        }

    async def test_resume_and_end_in_bulk(
        self,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_event: Event,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        paused = [await make_shared_list(status="paused") for _ in range(2)]
        url = f"/api/v1/events/{test_event.id}/shared-lists/bulk"
        ids = [str(p.id) for p in paused]

        resumed = await async_client.post(
            url, json={"action": "resume", "list_ids": ids}
        )
        ended = await async_client.post(url, json={"action": "end", "list_ids": ids})

        assert sorted(resumed.json()["changed"]) == sorted(ids)
        assert sorted(ended.json()["changed"]) == sorted(ids)
        assert ended.json()["skipped"] == []

    async def test_a_plain_member_is_refused_outright(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_shared_list: SharedList,
    ) -> None:
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/shared-lists/bulk",
            json={"action": "end", "list_ids": [str(test_shared_list.id)]},
        )

        _problem(r, 403, "shared_list.forbidden")

    async def test_with_sharing_off_a_person_in_charge_may_only_stop(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        live = await make_shared_list(created_by=manager)
        paused = await make_shared_list(created_by=manager, status="paused")
        test_event.managers_share_lists = False
        db_session.add(test_event)
        await db_session.flush()
        url = f"/api/v1/events/{test_event.id}/shared-lists/bulk"

        with act_as(app, manager):
            resume = await async_client.post(
                url, json={"action": "resume", "list_ids": [str(paused.id)]}
            )
            pause = await async_client.post(
                url, json={"action": "pause", "list_ids": [str(live.id)]}
            )

        assert resume.json() == {
            "changed": [],
            "skipped": [
                {"id": str(paused.id), "code": "shared_list.managers_disabled"}
            ],
        }
        assert pause.json() == {"changed": [str(live.id)], "skipped": []}

    async def test_more_lists_cost_no_more_statements(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_event: Event,
        manager: User,
        shifts: list[Shift],
        count_queries: CountQueries,
    ) -> None:
        """As a person in charge, whose access is worked out per list."""
        url = f"/api/v1/events/{test_event.id}/shared-lists/bulk"

        async def pause(lists: int) -> list[str]:
            ids = [
                str((await make_shared_list(created_by=manager, title=f"L{n}")).id)
                for n in range(lists)
            ]
            with act_as(app, manager), count_queries() as statements:
                r = await async_client.post(
                    url, json={"action": "pause", "list_ids": ids}
                )
            assert sorted(r.json()["changed"]) == sorted(ids)
            return statements

        one = await pause(1)
        ten = await pause(10)
        assert one
        assert len(ten) == len(one)

    async def test_more_than_a_hundred_ids_are_refused(
        self, async_client: AsyncClient, test_event: Event, as_event_admin: None
    ) -> None:
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/shared-lists/bulk",
            json={"action": "end", "list_ids": [str(uuid.uuid4()) for _ in range(101)]},
        )

        assert r.status_code == 422


@pytest.mark.asyncio
class TestPauseAll:
    async def test_every_open_list_stops_expired_ones_included(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        live = await make_shared_list()
        expired = await make_shared_list(
            ends_mode="date", ends_on=TODAY - dt.timedelta(days=1)
        )
        paused = await make_shared_list(status="paused")
        ended = await make_shared_list(status="ended")
        paused_at = paused.paused_at

        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/shared-lists/pause-all", json={}
        )

        assert r.status_code == 200, r.text
        assert sorted(r.json()["changed"]) == sorted([str(live.id), str(expired.id)])
        for shared_list in (live, expired, paused, ended):
            await db_session.refresh(shared_list)
        assert live.status == expired.status == paused.status == "paused"
        assert paused.paused_at == paused_at
        assert ended.status == "ended"
        await db_session.refresh(test_event)
        assert test_event.managers_share_lists is True

    async def test_locking_people_in_charge_out_keeps_their_lists_paused(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_event_admin_user: User,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        theirs = await make_shared_list(created_by=manager)

        with act_as(app, test_event_admin_user):
            r = await async_client.post(
                f"/api/v1/events/{test_event.id}/shared-lists/pause-all",
                json={"lock_managers": True},
            )
        with act_as(app, manager):
            resume = await async_client.post(f"/api/v1/shared-lists/{theirs.id}/resume")

        assert r.json()["changed"] == [str(theirs.id)]
        await db_session.refresh(test_event)
        assert test_event.managers_share_lists is False
        _problem(resume, 403, "shared_list.managers_disabled")

    async def test_only_event_admins_may(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        test_event: Event,
        test_shared_list: SharedList,
        manager: User,
    ) -> None:
        url = f"/api/v1/events/{test_event.id}/shared-lists/pause-all"
        with act_as(app, manager):
            _problem(await async_client.post(url, json={}), 403, "event.forbidden")
        _problem(await async_client.post(url, json={}), 403, "shared_list.forbidden")

    async def test_the_superadmin_does_not_find_a_demo_event(
        self,
        async_client: AsyncClient,
        test_sandbox: SandboxSetup,
        as_admin: None,
    ) -> None:
        r = await async_client.post(
            f"/api/v1/events/{test_sandbox.event.id}/shared-lists/pause-all", json={}
        )

        _problem(r, 404, "event.not_found")


@pytest.mark.asyncio
class TestEventSetting:
    async def test_an_event_lets_people_in_charge_share_by_default(
        self, async_client: AsyncClient, test_event: Event
    ) -> None:
        r = await async_client.get(f"/api/v1/events/{test_event.id}")

        assert r.json()["managers_share_lists"] is True

    async def test_an_admin_switches_it_and_null_leaves_it(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        as_event_admin: None,
    ) -> None:
        url = f"/api/v1/events/{test_event.id}"

        off = await async_client.patch(url, json={"managers_share_lists": False})
        kept = await async_client.patch(
            url, json={"name": "Umbenannt", "managers_share_lists": None}
        )

        assert off.status_code == 200, off.text
        assert off.json()["managers_share_lists"] is False
        assert kept.json()["managers_share_lists"] is False
        await db_session.refresh(test_event)
        assert test_event.managers_share_lists is False

    async def test_a_member_cannot(
        self, async_client: AsyncClient, test_event: Event
    ) -> None:
        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}", json={"managers_share_lists": False}
        )

        _problem(r, 403, "event.forbidden")

    async def test_a_clone_keeps_it(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_shared_list: SharedList,
        as_event_admin: None,
    ) -> None:
        test_event.managers_share_lists = False
        db_session.add(test_event)
        await db_session.flush()

        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/clone",
            json={"name": "Nächstes Jahr", "start_date": "2027-06-10"},
        )

        assert r.status_code == 201, r.text
        assert r.json()["event"]["managers_share_lists"] is False
        cloned_lists = await db_session.execute(
            select(SharedList).where(
                col(SharedList.event_id) == uuid.UUID(r.json()["event"]["id"])
            )
        )
        assert cloned_lists.first() is None


@pytest.mark.asyncio
class TestManagedTaskCount:
    async def test_it_counts_the_callers_tasks_in_each_event(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        bar: Task,
        manager: User,
    ) -> None:
        db_session.add(TaskManager(task_id=bar.id, user_id=manager.id))
        await db_session.flush()

        with act_as(app, manager):
            one = await async_client.get(f"/api/v1/events/{test_event.id}")
            listed = await async_client.get("/api/v1/events/")
        plain = await async_client.get(f"/api/v1/events/{test_event.id}")

        assert one.json()["managed_task_count"] == 2
        assert [e["managed_task_count"] for e in listed.json()["items"]] == [2]
        assert plain.json()["managed_task_count"] == 0


@pytest.mark.asyncio
class TestLifecycle:
    async def test_moving_the_event_moves_the_closing_day(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        on_a_day = await make_shared_list(ends_mode="date", ends_on=DAY2)
        with_last_shift = await make_shared_list()

        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/shift-dates",
            json={"new_start_date": "2026-06-17"},
        )

        assert r.status_code == 200, r.text
        await db_session.refresh(on_a_day)
        await db_session.refresh(with_last_shift)
        assert on_a_day.ends_on == DAY2 + dt.timedelta(days=7)
        assert with_last_shift.ends_on is None

    async def test_deleting_a_task_or_a_shift_takes_its_rows_off_the_list(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_task: Task,
        bar: Task,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        shared_list = await make_shared_list(
            tasks=[test_task, bar], excluded=[shifts[0]]
        )

        task_gone = await async_client.delete(f"/api/v1/tasks/{bar.id}")
        shift_gone = await async_client.delete(f"/api/v1/shifts/{shifts[0].id}")

        assert task_gone.status_code == shift_gone.status_code == 204
        linked = await db_session.execute(
            select(col(SharedListTask.task_id)).where(
                col(SharedListTask.shared_list_id) == shared_list.id
            )
        )
        assert list(linked.scalars()) == [test_task.id]
        excluded = await db_session.execute(
            select(SharedListExcludedShift).where(
                col(SharedListExcludedShift.shared_list_id) == shared_list.id
            )
        )
        assert excluded.first() is None
