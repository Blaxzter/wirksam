"""The shared-list management views of an event: the lists table, the tasks
table, the figures above them, and the wizard's choices of tasks and shifts.

They are filtered, sorted and paged on the server, so these pin the filter
counts against ``q``, every sort key in both directions with pages that never
overlap, who sees which list, the issues that need someone's attention, and
that the lists table costs the same number of statements for 1 list as for 20.

The event's clock stands at 2026-06-10 12:00, the day before the shifts. The
cast is that of ``test_shared_lists.py``: the event admin, ``manager`` in
charge of ``test_task``, and ``test_user``, a plain member.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.event_team import EventTeam
from app.models.shared_list import SharedList
from app.models.shift import Shift
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from tests.fixtures.client import act_as
from tests.fixtures.clock import set_wall_clock
from tests.fixtures.sandbox import SandboxSetup
from tests.fixtures.shared_lists import (
    CountQueries,
    ListGuestFactory,
    SharedListFactory,
)

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
    location: str | None = None,
    vouchers_per_shift: int = 0,
) -> Task:
    task = Task(
        name=name,
        start_date=DAY1,
        end_date=DAY3,
        status=status,
        created_by_id=creator.id,
        event_id=event.id,
        team_id=team_id,
        location=location,
        vouchers_per_shift=vouchers_per_shift,
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


async def _in_charge(db: AsyncSession, task: Task, user: User) -> None:
    db.add(TaskManager(task_id=task.id, user_id=user.id))
    await db.flush()


def _problem(r: Response, status: int, code: str) -> None:
    assert r.status_code == status, r.text
    assert r.json()["code"] == code, r.json()


@pytest_asyncio.fixture
async def shifts(db_session: AsyncSession, test_task: Task) -> list[Shift]:
    """Three shifts of ``test_task``, one a day, two places each."""
    return [await _shift(db_session, test_task, day) for day in (DAY1, DAY2, DAY3)]


@pytest_asyncio.fixture
async def bar(db_session: AsyncSession, test_event: Event, test_user: User) -> Task:
    """A second published task in ``test_event``, with one shift ahead."""
    task = await _task(db_session, test_event, test_user, "Bar", location="Foyer")
    await _shift(db_session, task, DAY1, dt.time(18))
    return task


@pytest_asyncio.fixture
async def manager(db_session: AsyncSession, test_event: Event, test_task: Task) -> User:
    """A member of ``test_event`` in charge of ``test_task``."""
    user = await _member(db_session, test_event, "manager")
    await _in_charge(db_session, test_task, user)
    return user


async def _lists(client: AsyncClient, event: Event, **params: Any) -> Response:
    return await client.get(f"/api/v1/events/{event.id}/shared-lists", params=params)


#: How each sort key reads a row of the lists table, and its default direction.
_LIST_KEYS: dict[str, tuple[Callable[[dict[str, Any]], Any], str]] = {
    "status": (
        lambda r: ["live", "paused", "expired", "ended"].index(r["effective_status"]),
        "asc",
    ),
    "created_at": (lambda r: dt.datetime.fromisoformat(r["created_at"]), "desc"),
    "title": (lambda r: r["title"].casefold(), "asc"),
    "signups": (lambda r: r["signup_count"], "desc"),
    "free": (lambda r: r["free"], "desc"),
    "closes": (
        lambda r: r["closes_at"] and dt.datetime.fromisoformat(r["closes_at"]),
        "asc",
    ),
}


def _assert_sorted(
    rows: list[dict[str, Any]], key: Callable[[dict[str, Any]], Any], *, desc: bool
) -> None:
    """In ``key`` order, ties by id ascending, rows without a value last."""
    values = [key(r) for r in rows]
    present = [v for v in values if v is not None]
    assert values == present + [None] * (len(values) - len(present))
    assert present == sorted(present, reverse=desc)
    for a, b in zip(rows, rows[1:], strict=False):
        if key(a) == key(b):
            assert uuid.UUID(a["id"]) < uuid.UUID(b["id"])


@pytest.mark.asyncio
class TestListsTable:
    @pytest_asyncio.fixture
    async def board(
        self,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_task: Task,
        bar: Task,
        shifts: list[Shift],
    ) -> dict[str, SharedList]:
        """One list of each kind:

        - ``live`` offers ``test_task``;
        - ``paused`` too, so its places are on a live list: no issue;
        - ``expired`` offers ``Bar``, closed yesterday, on no live list: to do;
        - two ended ones, one of them about the "Theke".
        """
        return {
            "live": await make_shared_list(title="Alpha"),
            "paused": await make_shared_list(title="Beta", status="paused"),
            "expired": await make_shared_list(
                title="Gamma",
                tasks=[bar],
                ends_mode="date",
                ends_on=TODAY - dt.timedelta(days=1),
            ),
            "ended": await make_shared_list(title="Delta", status="ended"),
            "ended_theke": await make_shared_list(title="Theke alt", status="ended"),
        }

    async def test_the_filter_counts_ignore_the_search(
        self,
        async_client: AsyncClient,
        test_event: Event,
        board: dict[str, SharedList],
        as_event_admin: None,
    ) -> None:
        expected = {"active": 3, "todo": 1, "live": 1, "paused": 1, "ended": 2}

        plain = await _lists(async_client, test_event)
        searched = await _lists(async_client, test_event, q="theke")

        assert plain.status_code == 200, plain.text
        assert plain.json()["counts"] == expected
        assert searched.json()["counts"] == expected
        assert plain.json()["total"] == 3
        assert plain.json()["ended_matching"] == 2
        # "Theke" matches only an ended list, which "active" hides.
        assert searched.json()["total"] == 0
        assert searched.json()["ended_matching"] == 1

    @pytest.mark.parametrize(
        ("status_filter", "titles"),
        [
            ("active", {"Alpha", "Beta", "Gamma"}),
            ("todo", {"Gamma"}),
            ("live", {"Alpha"}),
            ("paused", {"Beta"}),
            ("ended", {"Delta", "Theke alt"}),
        ],
    )
    async def test_each_filter(
        self,
        async_client: AsyncClient,
        test_event: Event,
        board: dict[str, SharedList],
        as_event_admin: None,
        status_filter: str,
        titles: set[str],
    ) -> None:
        r = await _lists(async_client, test_event, status_filter=status_filter)

        assert {row["title"] for row in r.json()["items"]} == titles
        assert r.json()["total"] == len(titles)

    async def test_the_search_finds_a_task_name(
        self,
        async_client: AsyncClient,
        test_event: Event,
        board: dict[str, SharedList],
        as_event_admin: None,
    ) -> None:
        r = await _lists(async_client, test_event, q="  BAR ")

        assert [row["title"] for row in r.json()["items"]] == ["Gamma"]
        issue = r.json()["items"][0]["issue"]
        assert issue == {
            "kind": "stranded",
            "free": 2,
            "task_names": ["Bar"],
            "days_left": None,
        }

    @pytest.mark.parametrize("sort_by", list(_LIST_KEYS))
    @pytest.mark.parametrize("sort_dir", ["asc", "desc", None])
    async def test_every_sort_pages_without_overlap(
        self,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        test_event: Event,
        test_task: Task,
        bar: Task,
        shifts: list[Shift],
        as_event_admin: None,
        sort_by: str,
        sort_dir: str | None,
    ) -> None:
        """Ties on purpose: two "Same" titles, several lists without sign-ups,
        several with the same free places, and two that close only by hand."""
        lists = [
            await make_shared_list(title="Same"),
            await make_shared_list(title="same", tasks=[bar]),
            await make_shared_list(title="Zeta", status="paused"),
            await make_shared_list(title="Eta", ends_mode="manual"),
            await make_shared_list(title="Theta", ends_mode="manual", status="ended"),
            await make_shared_list(title="Iota", ends_mode="date", ends_on=DAY2),
            await make_shared_list(title="Kappa", excluded=shifts[:2]),
        ]
        await make_list_guest(lists[0], shifts=[shifts[0]])
        await make_list_guest(lists[0], name="Gast Zwei", shifts=[shifts[1]])
        await make_list_guest(lists[3], shifts=[shifts[2]])
        params: dict[str, Any] = {"status_filter": "active", "sort_by": sort_by}
        if sort_dir:
            params["sort_dir"] = sort_dir
        key, default_dir = _LIST_KEYS[sort_by]

        whole = await _lists(async_client, test_event, **params, limit=100)
        pages = [
            await _lists(async_client, test_event, **params, skip=s, limit=2)
            for s in (0, 2, 4)
        ]

        rows = whole.json()["items"]
        assert whole.json()["total"] == len(rows) == 6
        _assert_sorted(rows, key, desc=(sort_dir or default_dir) == "desc")
        paged = [row["id"] for page in pages for row in page.json()["items"]]
        assert paged == [row["id"] for row in rows]
        assert all(page.json()["total"] == 6 for page in pages)

    async def test_a_page_past_the_end_is_empty(
        self,
        async_client: AsyncClient,
        test_event: Event,
        board: dict[str, SharedList],
        as_event_admin: None,
    ) -> None:
        r = await _lists(async_client, test_event, skip=10, limit=5)

        assert r.json()["items"] == []
        assert (r.json()["total"], r.json()["skip"], r.json()["limit"]) == (3, 10, 5)

    async def test_sign_ups_are_counted_per_list(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_list_guest: ListGuestFactory,
        test_event: Event,
        test_shared_list: SharedList,
        test_user: User,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        await make_list_guest(test_shared_list, shifts=[shifts[0], shifts[1]])
        # A member's booking that carries the list's id counts as a sign-up,
        # not as a guest.
        db_session.add(
            Booking(
                shift_id=shifts[2].id,
                user_id=test_user.id,
                status="confirmed",
                shared_list_id=test_shared_list.id,
            )
        )
        await db_session.flush()

        r = await _lists(async_client, test_event)

        row = r.json()["items"][0]
        assert (row["signup_count"], row["guest_count"]) == (3, 2)
        assert (row["capacity"], row["free"]) == (6, 3)

    async def test_a_task_moved_away_takes_its_sign_ups_out_of_the_counts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        test_event: Event,
        test_private_event: Event,
        test_task: Task,
        bar: Task,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        """As in the table of the list's sign-ups, which the counts open."""
        shared_list = await make_shared_list(tasks=[test_task, bar])
        bar_shift = await _shift(db_session, bar, DAY1)
        await make_list_guest(shared_list, shifts=[bar_shift])
        bar.event_id = test_private_event.id
        db_session.add(bar)
        await db_session.flush()

        row = (await _lists(async_client, test_event)).json()["items"][0]
        summary = (
            await async_client.get(
                f"/api/v1/events/{test_event.id}/shared-lists/overview"
            )
        ).json()["summary"]
        signups = (
            await async_client.get(f"/api/v1/shared-lists/{shared_list.id}/signups")
        ).json()

        assert (row["signup_count"], row["guest_count"]) == (0, 0)
        assert (summary["signups"], summary["guests"]) == (0, 0)
        assert signups["total"] == 0

    async def test_people_in_charge_see_the_lists_of_their_tasks(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        bar: Task,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        mine = await make_shared_list(title="Meine")
        # Paused with Bar's places on no live list: an admin would see an issue.
        mixed = await make_shared_list(
            title="Gemischt", tasks=[test_task, bar], status="paused"
        )
        await make_shared_list(title="Fremd", tasks=[bar])

        with act_as(app, manager):
            r = await _lists(async_client, test_event, sort_by="title")

        assert r.status_code == 200, r.text
        rows = {row["id"]: row for row in r.json()["items"]}
        assert set(rows) == {str(mine.id), str(mixed.id)}
        assert rows[str(mine.id)]["access"] == "manager"
        assert rows[str(mixed.id)]["access"] == "viewer"
        assert rows[str(mixed.id)]["issue"] is None
        assert r.json()["counts"]["active"] == 2

    @pytest.mark.parametrize("view", ["", "/overview", "/tasks", "/candidates"])
    async def test_a_plain_member_is_refused(
        self, async_client: AsyncClient, test_event: Event, view: str
    ) -> None:
        r = await async_client.get(f"/api/v1/events/{test_event.id}/shared-lists{view}")

        _problem(r, 403, "shared_list.forbidden")

    @pytest.mark.parametrize(
        "view",
        ["", "/overview", "/tasks", "/candidates", "/candidate-shifts?task_id={task}"],
    )
    async def test_the_superadmin_does_not_find_a_demo_event(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
        as_admin: None,
        view: str,
    ) -> None:
        task = await _task(db_session, test_sandbox.event, test_sandbox.guest, "Demo")

        r = await async_client.get(
            f"/api/v1/events/{test_sandbox.event.id}/shared-lists"
            + view.format(task=task.id)
        )

        _problem(r, 404, "event.not_found")

    async def test_an_unknown_event_is_not_found(
        self, async_client: AsyncClient, as_admin: None
    ) -> None:
        r = await async_client.get(f"/api/v1/events/{uuid.uuid4()}/shared-lists")

        _problem(r, 404, "event.not_found")

    async def test_more_lists_cost_no_more_statements(
        self,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        test_event: Event,
        test_task: Task,
        bar: Task,
        manager: User,
        app: FastAPI,
        shifts: list[Shift],
        count_queries: CountQueries,
    ) -> None:
        """As a person in charge, whose access is worked out per list."""

        async def add(i: int) -> None:
            shared_list = await make_shared_list(
                title=f"Liste {i}",
                tasks=[test_task, bar] if i % 2 else [test_task],
                excluded=shifts[:1],
                status="paused" if i % 3 == 0 else "live",
            )
            await make_list_guest(shared_list, name=f"Gast {i}", shifts=[shifts[1]])

        await add(0)
        with act_as(app, manager), count_queries() as one:
            assert (await _lists(async_client, test_event)).status_code == 200

        for i in range(1, 20):
            await add(i)
        with act_as(app, manager), count_queries() as twenty:
            r = await _lists(async_client, test_event, limit=100)

        assert r.json()["total"] == 20
        assert one
        assert len(twenty) == len(one)


@pytest.mark.asyncio
class TestIssues:
    async def _issue(
        self, client: AsyncClient, event: Event, list_id: uuid.UUID
    ) -> Any:
        r = await _lists(client, event, limit=100)
        return next(
            row["issue"] for row in r.json()["items"] if row["id"] == str(list_id)
        )

    async def test_a_paused_list_whose_places_a_live_list_offers_is_fine(
        self,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_event: Event,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        await make_shared_list()
        paused = await make_shared_list(status="paused")

        assert await self._issue(async_client, test_event, paused.id) is None

    async def test_a_paused_list_strands_places_no_live_list_offers(
        self,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        bar: Task,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        # The live list offers the first day only.
        await make_shared_list(excluded=shifts[1:])
        paused = await make_shared_list(tasks=[bar, test_task], status="paused")

        issue = await self._issue(async_client, test_event, paused.id)

        assert issue == {
            "kind": "stranded",
            "free": 2 + 4,
            "task_names": ["Bar", test_task.name],
            "days_left": None,
        }

    async def test_a_list_closing_in_two_days_with_free_places(
        self,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        closing = await make_shared_list(ends_mode="date", ends_on=DAY2)

        issue = await self._issue(async_client, test_event, closing.id)

        assert issue == {
            "kind": "expires_soon",
            "free": 6,
            "task_names": [test_task.name],
            "days_left": 2,
        }

    async def test_a_full_list_has_nothing_to_do(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        test_user: User,
        as_event_admin: None,
    ) -> None:
        full = await _shift(db_session, test_task, DAY1, max_bookings=1)
        await _book(db_session, full, test_user)
        closing = await make_shared_list(ends_mode="date", ends_on=DAY1)
        paused = await make_shared_list(status="paused")

        assert await self._issue(async_client, test_event, closing.id) is None
        assert await self._issue(async_client, test_event, paused.id) is None
        r = await _lists(async_client, test_event)
        assert all(row["is_full"] for row in r.json()["items"])


async def _tasks(client: AsyncClient, event: Event, **params: Any) -> Response:
    return await client.get(
        f"/api/v1/events/{event.id}/shared-lists/tasks", params=params
    )


@pytest.mark.asyncio
class TestTasksTable:
    async def test_stranded_and_unlisted_places(
        self,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        """Day 1 is on a live list, day 2 only on a paused one, day 3 on none."""
        live = await make_shared_list(title="Offen", excluded=shifts[1:])
        paused = await make_shared_list(
            title="Pause", status="paused", excluded=[shifts[0], shifts[2]]
        )
        await make_shared_list(title="Vorbei", status="ended")

        r = await _tasks(async_client, test_event)

        assert r.status_code == 200, r.text
        row = r.json()["items"][0]
        assert row["id"] == str(test_task.id)
        assert (row["shift_count"], row["capacity"], row["free"]) == (3, 6, 6)
        assert row["dates"] == [d.isoformat() for d in (DAY1, DAY2, DAY3)]
        assert (row["stranded_free"], row["unlisted_free"]) == (4, 2)
        assert {chip["id"]: chip["effective_status"] for chip in row["lists"]} == {
            str(live.id): "live",
            str(paused.id): "paused",
        }
        assert row["ended_list_count"] == 1
        assert row["can_share"] is True
        assert r.json()["counts"] == {"all": 1, "todo": 1}

    async def test_a_team_task_cannot_be_shared(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        as_event_admin: None,
    ) -> None:
        team = EventTeam(event_id=test_event.id, name="Sanitäter")
        db_session.add(team)
        await db_session.flush()
        sani = await _task(db_session, test_event, test_user, "Sani", team_id=team.id)
        await _shift(db_session, sani, DAY1)

        r = await _tasks(async_client, test_event, status_filter="todo")
        everything = await _tasks(async_client, test_event)

        assert r.json()["items"] == []
        row = everything.json()["items"][0]
        assert row["team"] == {"id": str(team.id), "name": "Sanitäter"}
        assert row["can_share"] is False
        assert (row["stranded_free"], row["unlisted_free"]) == (0, 0)
        assert row["free"] == 2

    async def test_people_in_charge_see_their_tasks_only(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        bar: Task,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        test_event.managers_share_lists = False
        db_session.add(test_event)
        await db_session.flush()

        with act_as(app, manager):
            r = await _tasks(async_client, test_event)

        assert [row["id"] for row in r.json()["items"]] == [str(test_task.id)]
        assert r.json()["items"][0]["manager_names"] == ["Manager"]
        assert r.json()["items"][0]["can_share"] is False

    async def test_tasks_without_shifts_ahead_are_left_out(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        as_event_admin: None,
    ) -> None:
        over = await _task(db_session, test_event, test_user, "Vorbei")
        await _shift(db_session, over, TODAY, dt.time(8))
        draft = await _task(
            db_session, test_event, test_user, "Entwurf", status="draft"
        )
        await _shift(db_session, draft, DAY1)

        r = await _tasks(async_client, test_event)

        assert r.json()["items"] == []
        assert r.json()["counts"] == {"all": 0, "todo": 0}

    @pytest.mark.parametrize(
        ("sort_by", "sort_dir", "expected"),
        [
            ("name", None, ["Alpha", "Bar", "Zelt"]),
            ("name", "desc", ["Zelt", "Bar", "Alpha"]),
            ("free", None, ["Zelt", "Alpha", "Bar"]),
            ("free", "asc", ["Bar", "Alpha", "Zelt"]),
            ("unlisted_free", None, ["Zelt", "Bar", "Alpha"]),
            ("unlisted_free", "asc", ["Alpha", "Bar", "Zelt"]),
        ],
    )
    async def test_sorting(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_user: User,
        bar: Task,
        as_event_admin: None,
        sort_by: str,
        sort_dir: str | None,
        expected: list[str],
    ) -> None:
        """Alpha: 3 free, all on a live list. Bar: 2 free, none listed.
        Zelt: 5 free, none listed."""
        alpha = await _task(db_session, test_event, test_user, "Alpha")
        await _shift(db_session, alpha, DAY1, max_bookings=3)
        zelt = await _task(db_session, test_event, test_user, "Zelt")
        await _shift(db_session, zelt, DAY2, max_bookings=5)
        await make_shared_list(tasks=[alpha])
        params: dict[str, Any] = {"sort_by": sort_by}
        if sort_dir:
            params["sort_dir"] = sort_dir

        r = await _tasks(async_client, test_event, **params)

        assert [row["name"] for row in r.json()["items"]] == expected

    async def test_the_search_finds_the_place_and_the_people_in_charge(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_task: Task,
        bar: Task,
        manager: User,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        by_place = await _tasks(async_client, test_event, q="foyer")
        by_person = await _tasks(async_client, test_event, q="MANAG")

        assert [row["name"] for row in by_place.json()["items"]] == ["Bar"]
        assert [row["id"] for row in by_person.json()["items"]] == [str(test_task.id)]
        assert by_person.json()["counts"] == {"all": 2, "todo": 2}


@pytest.mark.asyncio
class TestOverview:
    async def test_the_figures_and_what_an_admin_may_do(
        self,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        test_event: Event,
        test_task: Task,
        bar: Task,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        first = await make_shared_list()
        # The same shifts on a second live list count once.
        await make_shared_list(excluded=shifts[:1])
        await make_list_guest(first, shifts=[shifts[0]])
        await make_shared_list(status="paused")
        await make_shared_list(status="ended")

        r = await async_client.get(
            f"/api/v1/events/{test_event.id}/shared-lists/overview"
        )

        assert r.status_code == 200, r.text
        assert r.json() == {
            "summary": {
                "live_lists": 2,
                "active_lists": 3,
                "signups": 1,
                "guests": 1,
                "free_in_live": 5,
            },
            "unshared": {"task_count": 1, "free": 2, "task_names": ["Bar"]},
            "can_create": True,
            "can_pause_all": True,
            "is_admin": True,
            "managers_share_lists": True,
            "event_timezone": test_event.timezone,
        }

    async def test_the_unshared_tasks_are_named_in_order(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        bar: Task,
        as_event_admin: None,
    ) -> None:
        for name in ("Zelt", "Aufbau"):
            task = await _task(db_session, test_event, test_user, name)
            await _shift(db_session, task, DAY2)

        r = await async_client.get(
            f"/api/v1/events/{test_event.id}/shared-lists/overview"
        )

        assert r.json()["unshared"] == {
            "task_count": 3,
            "free": 6,
            "task_names": ["Aufbau", "Bar"],
        }
        assert r.json()["can_pause_all"] is False

    async def test_what_a_person_in_charge_may_do(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        await make_shared_list()
        url = f"/api/v1/events/{test_event.id}/shared-lists/overview"

        with act_as(app, manager):
            allowed = await async_client.get(url)
            test_event.managers_share_lists = False
            db_session.add(test_event)
            await db_session.flush()
            locked = await async_client.get(url)

        assert allowed.json()["can_create"] is True
        assert allowed.json()["can_pause_all"] is False
        assert allowed.json()["is_admin"] is False
        assert locked.json()["can_create"] is False
        assert locked.json()["managers_share_lists"] is False

    async def test_a_person_in_charge_of_a_team_task_only_cannot_create(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        team = EventTeam(event_id=test_event.id, name="Sanitäter")
        db_session.add(team)
        await db_session.flush()
        test_task.team_id = team.id
        db_session.add(test_task)
        await db_session.flush()

        with act_as(app, manager):
            r = await async_client.get(
                f"/api/v1/events/{test_event.id}/shared-lists/overview"
            )

        assert r.json()["can_create"] is False


async def _candidates(client: AsyncClient, event: Event, **params: Any) -> Response:
    return await client.get(
        f"/api/v1/events/{event.id}/shared-lists/candidates", params=params
    )


@pytest.mark.asyncio
class TestCandidates:
    @pytest_asyncio.fixture
    async def team(self, db_session: AsyncSession, test_event: Event) -> EventTeam:
        team = EventTeam(event_id=test_event.id, name="Sanitäter")
        db_session.add(team)
        await db_session.flush()
        return team

    async def test_team_tasks_show_up_only_in_a_search(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_user: User,
        bar: Task,
        team: EventTeam,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        for name in ("Sani Nord", "Sani Süd", "Sani West", "Sani Ost"):
            task = await _task(db_session, test_event, test_user, name, team_id=team.id)
            await _shift(db_session, task, DAY1)

        plain = await _candidates(async_client, test_event)
        searched = await _candidates(async_client, test_event, q="sani n")

        assert [c["name"] for c in plain.json()["items"]] == ["Bar", test_task.name]
        assert plain.json()["total"] == 2
        assert plain.json()["locked_count"] == 4
        assert plain.json()["locked_names"] == ["Sani Nord", "Sani Ost", "Sani Süd"]
        assert [c["name"] for c in searched.json()["items"]] == ["Sani Nord"]
        assert searched.json()["items"][0]["team"] == {
            "id": str(team.id),
            "name": "Sanitäter",
        }

    async def test_a_candidate_carries_its_shifts_ahead(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_user: User,
        manager: User,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        test_task.vouchers_per_shift = 2
        test_task.location = "Kirche"
        db_session.add(test_task)
        await _shift(db_session, test_task, TODAY, dt.time(8))  # has started
        await _book(db_session, shifts[0], test_user)

        r = await _candidates(async_client, test_event, q="kirche")

        assert r.json()["items"] == [
            {
                "id": str(test_task.id),
                "name": test_task.name,
                "location": "Kirche",
                "manager_names": ["Manager"],
                "shift_count": 3,
                "dates": [d.isoformat() for d in (DAY1, DAY2, DAY3)],
                "capacity": 6,
                "free": 5,
                "team": None,
                "earns_vouchers": True,
            }
        ]

    async def test_only_tasks_with_shifts_ahead_and_published(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        bar: Task,
        as_event_admin: None,
    ) -> None:
        over = await _task(db_session, test_event, test_user, "Vorbei")
        await _shift(db_session, over, TODAY, dt.time(8))
        draft = await _task(
            db_session, test_event, test_user, "Entwurf", status="draft"
        )
        await _shift(db_session, draft, DAY1)
        await _task(db_session, test_event, test_user, "Ohne Schichten")

        r = await _candidates(async_client, test_event)

        assert [c["name"] for c in r.json()["items"]] == ["Bar"]

    async def test_people_in_charge_choose_from_their_tasks(
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
            r = await _candidates(async_client, test_event)

        assert [c["id"] for c in r.json()["items"]] == [str(test_task.id)]

    async def test_paging(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        as_event_admin: None,
    ) -> None:
        for name in ("A", "B", "C"):
            task = await _task(db_session, test_event, test_user, name)
            await _shift(db_session, task, DAY1)

        r = await _candidates(async_client, test_event, skip=1, limit=1)
        too_many = await _candidates(async_client, test_event, limit=51)

        assert [c["name"] for c in r.json()["items"]] == ["B"]
        assert r.json()["total"] == 3
        assert too_many.status_code == 422


async def _candidate_shifts(
    client: AsyncClient, event: Event, task_ids: list[uuid.UUID]
) -> Response:
    return await client.get(
        f"/api/v1/events/{event.id}/shared-lists/candidate-shifts",
        params={"task_id": [str(t) for t in task_ids]},
    )


@pytest.mark.asyncio
class TestCandidateShifts:
    async def test_the_shifts_ahead_by_start(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_private_event: Event,
        test_task: Task,
        test_user: User,
        bar: Task,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        await _shift(db_session, test_task, TODAY, dt.time(8))  # has started
        untimed = await _shift(db_session, test_task, DAY1, None)
        elsewhere = await _task(db_session, test_private_event, test_user, "Anderswo")
        await _shift(db_session, elsewhere, DAY1)
        await _book(db_session, shifts[0], test_user)

        r = await _candidate_shifts(
            async_client, test_event, [test_task.id, bar.id, elsewhere.id]
        )

        assert r.status_code == 200, r.text
        rows = r.json()
        assert [row["id"] for row in rows[:3]] == [
            str(untimed.id),
            str(shifts[0].id),
            rows[2]["id"],
        ]
        assert rows[2]["task_id"] == str(bar.id)
        assert len(rows) == 5
        assert (rows[1]["capacity"], rows[1]["free"]) == (2, 1)

    async def test_between_one_and_fifty_tasks(
        self, async_client: AsyncClient, test_event: Event, as_event_admin: None
    ) -> None:
        none = await async_client.get(
            f"/api/v1/events/{test_event.id}/shared-lists/candidate-shifts"
        )
        too_many = await _candidate_shifts(
            async_client, test_event, [uuid.uuid4() for _ in range(51)]
        )

        assert none.status_code == too_many.status_code == 422

    async def test_people_in_charge_read_their_tasks_only(
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
            mine = await _candidate_shifts(async_client, test_event, [test_task.id])
            theirs = await _candidate_shifts(async_client, test_event, [bar.id])

        assert len(mine.json()) == 3
        _problem(theirs, 403, "shared_list.tasks_forbidden")


async def _reusable(
    client: AsyncClient,
    event: Event,
    task_ids: list[uuid.UUID],
    *,
    covering: bool = False,
) -> Response:
    return await client.get(
        f"/api/v1/events/{event.id}/shared-lists/reusable",
        params={"task_id": [str(t) for t in task_ids], "covering": covering},
    )


async def _created(
    db: AsyncSession, shared_list: SharedList, when: dt.datetime
) -> SharedList:
    shared_list.created_at = when
    db.add(shared_list)
    await db.flush()
    return shared_list


@pytest.mark.asyncio
class TestReusable:
    """The list a printed notice of some tasks reuses: managed by the caller,
    not ended, open if one is, and holding exactly those tasks, or at least
    them for a whole event's print."""

    async def test_the_newest_open_list_with_exactly_these_tasks(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        bar: Task,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        await _created(
            db_session, await make_shared_list(title="Älter"), NOW - dt.timedelta(2)
        )
        newer = await _created(
            db_session, await make_shared_list(title="Neuer"), NOW - dt.timedelta(1)
        )
        # Newer still, and none of them the one to print.
        for shared_list in [
            await make_shared_list(tasks=[test_task, bar]),
            await make_shared_list(status="paused"),
            await make_shared_list(status="ended"),
            await make_shared_list(ends_mode="date", ends_on=TODAY - dt.timedelta(1)),
        ]:
            await _created(db_session, shared_list, NOW)

        r = await _reusable(async_client, test_event, [test_task.id])

        assert r.status_code == 200, r.text
        assert r.json()["list"]["id"] == str(newer.id)
        assert r.json()["list"]["access"] == "admin"

    async def test_the_set_of_tasks_is_compared_in_any_order(
        self,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        bar: Task,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        both = await make_shared_list(tasks=[test_task, bar])

        one = await _reusable(async_client, test_event, [test_task.id])
        swapped = await _reusable(async_client, test_event, [bar.id, test_task.id])

        assert one.status_code == 200, one.text
        assert one.json() == {"list": None}
        assert swapped.json()["list"]["id"] == str(both.id)

    @pytest.mark.parametrize(
        "stopped",
        [
            {"status": "paused"},
            {"ends_mode": "date", "ends_on": TODAY - dt.timedelta(1)},
        ],
        ids=["paused", "expired"],
    )
    async def test_a_stopped_list_when_none_is_open(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        shifts: list[Shift],
        as_event_admin: None,
        stopped: dict[str, Any],
    ) -> None:
        # The notice of a paused list offers to resume it: printing again
        # must not put a second list of the same shifts beside it.
        older = await _created(
            db_session, await make_shared_list(**stopped), NOW - dt.timedelta(2)
        )
        await _created(db_session, await make_shared_list(status="ended"), NOW)

        r = await _reusable(async_client, test_event, [test_task.id])

        assert r.status_code == 200, r.text
        assert r.json()["list"]["id"] == str(older.id)
        assert r.json()["list"]["effective_status"] != "live"

    async def test_covering_finds_a_list_with_more_tasks(
        self,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        bar: Task,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        # Printing every task once "bar" has nothing left to offer: the list
        # made for both is still the event's.
        both = await make_shared_list(tasks=[test_task, bar])
        await make_shared_list(tasks=[bar])

        covered = await _reusable(
            async_client, test_event, [test_task.id], covering=True
        )
        # No list holds a third task as well.
        missing = await _reusable(
            async_client,
            test_event,
            [test_task.id, bar.id, uuid.uuid4()],
            covering=True,
        )

        assert covered.status_code == 200, covered.text
        assert covered.json()["list"]["id"] == str(both.id)
        assert missing.json() == {"list": None}

    async def test_a_task_moved_away_no_longer_counts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_private_event: Event,
        test_task: Task,
        bar: Task,
        shifts: list[Shift],
        as_event_admin: None,
    ) -> None:
        shared_list = await make_shared_list(tasks=[test_task, bar])
        bar.event_id = test_private_event.id
        db_session.add(bar)
        await db_session.flush()

        r = await _reusable(async_client, test_event, [test_task.id])

        assert r.json()["list"]["id"] == str(shared_list.id)

    async def test_a_person_in_charge_finds_the_lists_of_their_tasks(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        bar: Task,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        mine = await make_shared_list()
        await make_shared_list(tasks=[test_task, bar])

        with act_as(app, manager):
            found = await _reusable(async_client, test_event, [test_task.id])
            mixed = await _reusable(async_client, test_event, [test_task.id, bar.id])

        assert found.json()["list"]["id"] == str(mine.id)
        assert found.json()["list"]["access"] == "manager"
        # Bar is someone else's: no list of it is theirs to print.
        _problem(mixed, 403, "shared_list.tasks_forbidden")

    async def test_not_for_people_in_charge_while_the_event_says_no(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        test_event_admin_user: User,
        manager: User,
        shifts: list[Shift],
    ) -> None:
        shared_list = await make_shared_list()
        test_event.managers_share_lists = False
        db_session.add(test_event)
        await db_session.flush()

        with act_as(app, manager):
            refused = await _reusable(async_client, test_event, [test_task.id])
        with act_as(app, test_event_admin_user):
            allowed = await _reusable(async_client, test_event, [test_task.id])

        _problem(refused, 403, "shared_list.managers_disabled")
        assert allowed.json()["list"]["id"] == str(shared_list.id)

    async def test_a_plain_member_is_refused(
        self,
        async_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        shifts: list[Shift],
    ) -> None:
        await make_shared_list()

        r = await _reusable(async_client, test_event, [test_task.id])

        _problem(r, 403, "shared_list.tasks_forbidden")

    async def test_the_superadmin_does_not_find_a_demo_event(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
        as_admin: None,
    ) -> None:
        task = await _task(db_session, test_sandbox.event, test_sandbox.guest, "Demo")

        r = await _reusable(async_client, test_sandbox.event, [task.id])

        _problem(r, 404, "event.not_found")

    async def test_between_one_and_fifty_tasks(
        self, async_client: AsyncClient, test_event: Event, as_event_admin: None
    ) -> None:
        none = await async_client.get(
            f"/api/v1/events/{test_event.id}/shared-lists/reusable"
        )
        too_many = await _reusable(
            async_client, test_event, [uuid.uuid4() for _ in range(51)]
        )

        assert none.status_code == too_many.status_code == 422
