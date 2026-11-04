"""Route tests for Task Feed endpoints."""

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shift import Shift
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from tests.fixtures.client import act_as


@pytest.mark.asyncio
class TestTaskFeedRoutes:
    """Test suite for /tasks/feed routes."""

    async def test_task_feed_list_view(
        self, async_client: AsyncClient, test_task: Task, test_shift: Shift
    ):
        """Test the task feed in list view mode."""
        r = await async_client.get("/api/v1/tasks/feed", params={"view": "list"})

        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert "skip" in data
        assert "limit" in data

    async def test_task_feed_cards_view(
        self, async_client: AsyncClient, test_task: Task
    ):
        """Test the task feed in cards view mode."""
        r = await async_client.get("/api/v1/tasks/feed", params={"view": "cards"})

        assert r.status_code == 200
        data = r.json()
        assert "items" in data

    async def test_task_feed_calendar_view(
        self, async_client: AsyncClient, test_task: Task
    ):
        """Test the task feed in calendar view mode."""
        r = await async_client.get(
            "/api/v1/tasks/feed",
            params={
                "view": "calendar",
                "date_from": "2026-05-01",
                "date_to": "2026-05-31",
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert "items" in data

    async def test_task_feed_with_search(
        self, async_client: AsyncClient, test_task: Task
    ):
        """Test the task feed with a search query."""
        r = await async_client.get(
            "/api/v1/tasks/feed",
            params={"search": test_task.name[:5]},
        )

        assert r.status_code == 200

    async def test_task_feed_my_bookings_filter(
        self, async_client: AsyncClient, test_booking: Booking
    ):
        """Test the my_bookings filter in task feed."""
        r = await async_client.get("/api/v1/tasks/feed", params={"my_bookings": True})

        assert r.status_code == 200

    async def test_task_feed_pagination(self, async_client: AsyncClient):
        """Test task feed pagination parameters."""
        r = await async_client.get(
            "/api/v1/tasks/feed",
            params={"skip": 0, "limit": 5},
        )

        assert r.status_code == 200
        data = r.json()
        assert data["skip"] == 0
        assert data["limit"] == 5

    async def test_task_feed_empty(self, async_client: AsyncClient):
        """Test task feed when no tasks match."""
        r = await async_client.get(
            "/api/v1/tasks/feed",
            params={"search": "zzz_nonexistent_zzz"},
        )

        assert r.status_code == 200
        assert r.json()["total"] == 0
        assert r.json()["items"] == []

    async def test_task_feed_focus_mode_first_available(
        self, async_client: AsyncClient, test_task: Task, test_shift: Shift
    ):
        """Test the task feed with first_available focus mode."""
        r = await async_client.get(
            "/api/v1/tasks/feed",
            params={"view": "list", "focus_mode": "first_available"},
        )

        assert r.status_code == 200

    async def test_task_active_dates(
        self, async_client: AsyncClient, test_task: Task, test_shift: Shift
    ):
        """Test the active dates endpoint."""
        r = await async_client.get(
            "/api/v1/tasks/active-dates",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )

        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_task_shift_window(
        self, async_client: AsyncClient, test_task: Task, test_shift: Shift
    ):
        """Test the shift window endpoint for a specific task."""
        r = await async_client.get(
            f"/api/v1/tasks/{test_task.id}/shift-window",
            params={"start_date": "2026-05-01", "days": 7},
        )

        assert r.status_code == 200
        data = r.json()
        assert "shifts" in data
        assert "start_date" in data
        assert "days" in data


# ---------------------------------------------------------------------------
# Fully booked tasks and the counts over the whole task
# ---------------------------------------------------------------------------

#: The event wall clock for the tests below: before ``test_event`` (10-14 June).
FEED_NOW = dt.datetime(2026, 6, 1, 10, 0)


async def _feed_user(db: AsyncSession, key: str) -> User:
    user = User(
        subject=f"local|feed-{key}",
        email=f"{key}.feed@example.com",
        name=key.capitalize(),
        roles=[],
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _feed_task(
    db: AsyncSession,
    event: Event,
    creator: User,
    *,
    name: str,
    start: dt.date = dt.date(2026, 6, 1),
    end: dt.date = dt.date(2026, 6, 14),
    status: str = "published",
) -> Task:
    task = Task(
        name=name,
        start_date=start,
        end_date=end,
        status=status,
        created_by_id=creator.id,
        event_id=event.id,
    )
    db.add(task)
    await db.flush()
    return task


async def _feed_shift(
    db: AsyncSession,
    task: Task,
    day: dt.date,
    *,
    start: dt.time = dt.time(9, 0),
    end: dt.time = dt.time(11, 0),
    booked_by: list[User] | None = None,
    capacity: int = 1,
) -> Shift:
    shift = Shift(
        task_id=task.id,
        title=f"{task.name} {day.isoformat()} {start.isoformat()}",
        date=day,
        start_time=start,
        end_time=end,
        max_bookings=capacity,
    )
    db.add(shift)
    await db.flush()
    for user in booked_by or []:
        db.add(Booking(shift_id=shift.id, user_id=user.id, status="confirmed"))
    await db.flush()
    return shift


@dataclass
class FeedCast:
    member: User
    admin: User
    manager: User
    #: Every shift still to come is taken, like the Cafetheke of the bug report.
    full: Task
    #: Over before the clock: its end date has passed.
    past: Task
    #: One open shift ten days out, beyond the five days the list shows.
    later: Task


@pytest_asyncio.fixture
async def feed_cast(
    db_session: AsyncSession,
    test_event: Event,
    test_user: User,
    test_event_admin_user: User,
    wall_clock: Callable[[dt.datetime], None],
) -> FeedCast:
    wall_clock(FEED_NOW)
    manager = await _feed_user(db_session, "manager")
    helper = await _feed_user(db_session, "helper")
    for user in (manager, helper):
        db_session.add(
            EventMembership(user_id=user.id, event_id=test_event.id, role="member")
        )
    await db_session.flush()

    full = await _feed_task(db_session, test_event, test_user, name="Theke")
    await _feed_shift(db_session, full, dt.date(2026, 6, 3), booked_by=[helper])
    await _feed_shift(
        db_session,
        full,
        dt.date(2026, 6, 5),
        booked_by=[helper, test_user],
        capacity=2,
    )
    db_session.add(TaskManager(task_id=full.id, user_id=manager.id))

    past = await _feed_task(
        db_session,
        test_event,
        test_user,
        name="Vorbei",
        start=dt.date(2026, 5, 20),
        end=dt.date(2026, 5, 30),
    )
    await _feed_shift(db_session, past, dt.date(2026, 5, 29))
    db_session.add(TaskManager(task_id=past.id, user_id=manager.id))

    later = await _feed_task(db_session, test_event, test_user, name="Spaeter")
    await _feed_shift(db_session, later, dt.date(2026, 6, 11))
    await db_session.flush()
    return FeedCast(
        member=test_user,
        admin=test_event_admin_user,
        manager=manager,
        full=full,
        past=past,
        later=later,
    )


async def _feed_items(
    client: AsyncClient, app: FastAPI, user: User, view: str = "list"
) -> dict[str, dict[str, Any]]:
    with act_as(app, user):
        r = await client.get("/api/v1/tasks/feed", params={"view": view})
    assert r.status_code == 200, r.text
    return {item["name"]: item for item in r.json()["items"]}


@pytest.mark.asyncio
class TestFeedFullyBooked:
    """Who still finds a task once every shift still to come is taken."""

    @pytest.mark.parametrize("view", ["list", "cards"])
    async def test_a_plain_member_does_not_get_it(
        self, async_client: AsyncClient, app: FastAPI, feed_cast: FeedCast, view: str
    ) -> None:
        items = await _feed_items(async_client, app, feed_cast.member, view)
        assert "Theke" not in items
        assert "Spaeter" in items

    @pytest.mark.parametrize("view", ["list", "cards"])
    @pytest.mark.parametrize("role", ["manager", "admin"])
    async def test_the_ones_who_run_it_do(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        feed_cast: FeedCast,
        role: str,
        view: str,
    ) -> None:
        """Its person in charge and an organiser: the bug the product owner hit."""
        items = await _feed_items(async_client, app, getattr(feed_cast, role), view)
        assert "Theke" in items
        assert items["Theke"]["can_manage"] is True

    @pytest.mark.parametrize("role", ["member", "manager", "admin"])
    async def test_a_task_that_is_over_shows_for_nobody(
        self, async_client: AsyncClient, app: FastAPI, feed_cast: FeedCast, role: str
    ) -> None:
        items = await _feed_items(async_client, app, getattr(feed_cast, role))
        assert "Vorbei" not in items

    async def test_the_count_covers_the_whole_task_not_the_window(
        self, async_client: AsyncClient, app: FastAPI, feed_cast: FeedCast
    ) -> None:
        later = (await _feed_items(async_client, app, feed_cast.member))["Spaeter"]
        assert later["shifts"] == []
        assert later["open_shifts"] == 1
        assert later["next_shift_date"] == "2026-06-11"
        assert later["next_open_shift_date"] == "2026-06-11"

    async def test_a_full_task_says_so(
        self, async_client: AsyncClient, app: FastAPI, feed_cast: FeedCast
    ) -> None:
        full = (await _feed_items(async_client, app, feed_cast.admin))["Theke"]
        assert full["open_shifts"] == 0
        assert full["next_shift_date"] == "2026-06-03"
        assert full["next_open_shift_date"] is None
        assert len(full["shifts"]) == 2

    async def test_a_shift_that_has_started_is_not_coming_up(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        feed_cast: FeedCast,
        test_event: Event,
        wall_clock: Callable[[dt.datetime], None],
    ) -> None:
        """Started an hour ago on the event clock: in the window, not counted."""
        running = await _feed_task(
            db_session, test_event, feed_cast.member, name="Laeuft"
        )
        await _feed_shift(
            db_session, running, dt.date(2026, 6, 2), start=dt.time(9), end=dt.time(12)
        )
        await _feed_shift(db_session, running, dt.date(2026, 6, 4))
        wall_clock(dt.datetime(2026, 6, 2, 10, 0))

        item = (await _feed_items(async_client, app, feed_cast.member))["Laeuft"]
        assert item["open_shifts"] == 1
        assert item["next_shift_date"] == "2026-06-04"
        assert [s["date"] for s in item["shifts"]] == ["2026-06-02", "2026-06-04"]

    async def test_cards_carry_no_list_counts(
        self, async_client: AsyncClient, app: FastAPI, feed_cast: FeedCast
    ) -> None:
        items = await _feed_items(async_client, app, feed_cast.member, "cards")
        assert items["Spaeter"]["open_shifts"] is None
        assert items["Spaeter"]["available_shifts"] == 1
