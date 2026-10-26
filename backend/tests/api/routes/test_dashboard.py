"""Route tests for Dashboard endpoints."""

import datetime as dt

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.event import Event
from app.models.event_team import EventTeam, EventTeamMember
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User

TOMORROW = dt.date.today() + dt.timedelta(days=1)
YESTERDAY = dt.date.today() - dt.timedelta(days=1)


async def _add_shift(
    db_session: AsyncSession,
    task: Task,
    *,
    title: str = "Einlass",
    date: dt.date = TOMORROW,
    start: dt.time | None = dt.time(9, 0),
    end: dt.time | None = dt.time(12, 30),
    capacity: int = 2,
) -> Shift:
    shift = Shift(
        task_id=task.id,
        title=title,
        date=date,
        start_time=start,
        end_time=end,
        location="Haupteingang",
        max_bookings=capacity,
    )
    db_session.add(shift)
    await db_session.flush()
    await db_session.refresh(shift)
    return shift


async def _book(db_session: AsyncSession, shift: Shift, user: User) -> Booking:
    booking = Booking(shift_id=shift.id, user_id=user.id, status="confirmed")
    db_session.add(booking)
    await db_session.flush()
    await db_session.refresh(booking)
    return booking


@pytest.mark.asyncio
class TestDashboardFeed:
    """The one request /app/home is built from."""

    async def test_returns_every_section(self, async_client: AsyncClient):
        r = await async_client.get("/api/v1/dashboard/feed")

        assert r.status_code == 200
        data = r.json()
        for key in (
            "my_shifts",
            "my_shift_count",
            "my_minutes",
            "open_shifts",
            "open_shift_count",
            "open_places",
            "attention",
            "pending_join_request_count",
            "pending_team_request_count",
        ):
            assert key in data

    async def test_my_shift_carries_its_job_and_event(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_event: Event,
        test_user: User,
    ):
        """A booked shift arrives with everything the row renders."""
        shift = await _add_shift(db_session, test_task)
        await _book(db_session, shift, test_user)

        r = await async_client.get("/api/v1/dashboard/feed")

        assert r.status_code == 200
        data = r.json()
        assert data["my_shift_count"] == 1
        mine = data["my_shifts"][0]
        assert mine["shift_id"] == str(shift.id)
        assert mine["task_name"] == test_task.name
        assert mine["event_name"] == test_event.name
        assert mine["location"] == "Haupteingang"
        assert mine["taken"] == 1
        assert mine["capacity"] == 2
        # 09:00–12:30
        assert data["my_minutes"] == 210

    async def test_past_shifts_are_not_upcoming(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        shift = await _add_shift(db_session, test_task, date=YESTERDAY)
        await _book(db_session, shift, test_user)

        r = await async_client.get("/api/v1/dashboard/feed")

        assert r.json()["my_shift_count"] == 0

    async def test_open_shifts_offer_what_still_has_room(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
    ):
        shift = await _add_shift(db_session, test_task, title="Kuchentheke")

        r = await async_client.get("/api/v1/dashboard/feed")

        data = r.json()
        assert data["open_shift_count"] == 1
        assert data["open_places"] == 2
        offered = data["open_shifts"][0]
        assert offered["shift_id"] == str(shift.id)
        assert offered["places_left"] == 2
        assert offered["task_name"] == test_task.name

    async def test_open_shifts_skip_the_ones_i_am_already_on(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        """Offering somebody a shift they already hold reads as a bug."""
        mine = await _add_shift(db_session, test_task, title="Meine")
        await _book(db_session, mine, test_user)
        other = await _add_shift(db_session, test_task, title="Andere")

        r = await async_client.get("/api/v1/dashboard/feed")

        data = r.json()
        offered_ids = [s["shift_id"] for s in data["open_shifts"]]
        assert offered_ids == [str(other.id)]

    async def test_open_shifts_skip_full_ones(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_admin_user: User,
        test_event_admin_user: User,
    ):
        full = await _add_shift(db_session, test_task, title="Voll", capacity=2)
        await _book(db_session, full, test_admin_user)
        await _book(db_session, full, test_event_admin_user)

        r = await async_client.get("/api/v1/dashboard/feed")

        assert r.json()["open_shift_count"] == 0

    async def test_open_shifts_skip_draft_tasks(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_draft_task: Task,
    ):
        """A draft is the organiser's workbench, not an offer."""
        await _add_shift(db_session, test_draft_task, title="Noch nicht fertig")

        r = await async_client.get("/api/v1/dashboard/feed")

        assert r.json()["open_shift_count"] == 0

    async def test_selected_event_scopes_the_open_shifts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_draft_event: Event,
        test_user: User,
    ):
        """Two events, one selected: only that one's work is offered."""
        elsewhere = Task(
            name="Anderes Event",
            start_date=TOMORROW,
            end_date=TOMORROW,
            status="published",
            event_id=test_draft_event.id,
            created_by_id=test_user.id,
        )
        db_session.add(elsewhere)
        await db_session.flush()
        await _add_shift(db_session, elsewhere, title="Woanders")
        await _add_shift(db_session, test_task, title="Hier")

        test_user.selected_event_id = test_task.event_id
        db_session.add(test_user)
        await db_session.flush()

        r = await async_client.get("/api/v1/dashboard/feed")

        data = r.json()
        assert data["event_id"] == str(test_task.event_id)
        assert [s["title"] for s in data["open_shifts"]] == ["Hier"]

    async def test_my_shifts_ignore_the_selected_event(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_draft_event: Event,
        test_user: User,
    ):
        """A duty you promised to turn up to is never hidden by the switcher."""
        elsewhere = Task(
            name="Anderes Event",
            start_date=TOMORROW,
            end_date=TOMORROW,
            status="published",
            event_id=test_draft_event.id,
            created_by_id=test_user.id,
        )
        db_session.add(elsewhere)
        await db_session.flush()
        shift = await _add_shift(db_session, elsewhere, title="Woanders")
        await _book(db_session, shift, test_user)

        test_user.selected_event_id = test_task.event_id
        db_session.add(test_user)
        await db_session.flush()

        r = await async_client.get("/api/v1/dashboard/feed")

        data = r.json()
        assert [s["title"] for s in data["my_shifts"]] == ["Woanders"]

    async def test_a_plain_member_gets_no_attention_block(
        self,
        async_client: AsyncClient,
        test_task: Task,
    ):
        """``test_user`` is a member of the fixture event, not an admin."""
        r = await async_client.get("/api/v1/dashboard/feed")

        assert r.json()["attention"] is None

    async def test_attention_counts_the_gaps_for_an_organiser(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_admin_user: User,
        test_user: User,
        as_event_admin: None,
    ):
        # The ``test_draft_task`` fixture is dated in the past, and a draft
        # nobody can still run is not something to chase anyone about.
        db_session.add(
            Task(
                name="Noch nicht veroeffentlicht",
                start_date=TOMORROW,
                end_date=TOMORROW,
                status="draft",
                event_id=test_task.event_id,
                created_by_id=test_user.id,
            )
        )
        empty = await _add_shift(db_session, test_task, title="Niemand", capacity=2)
        short = await _add_shift(db_session, test_task, title="Halb", capacity=2)
        await _book(db_session, short, test_admin_user)
        assert empty.id != short.id

        r = await async_client.get("/api/v1/dashboard/feed")

        attention = r.json()["attention"]
        assert attention is not None
        assert attention["empty_shifts_soon"] == 1
        assert attention["short_shifts_soon"] == 1
        assert attention["draft_tasks"] == 1

    async def test_attention_horizon_excludes_the_far_future(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        as_event_admin: None,
    ):
        """A gap a month out is not yet anybody's problem."""
        await _add_shift(
            db_session,
            test_task,
            title="Weit weg",
            date=dt.date.today() + dt.timedelta(days=30),
        )

        r = await async_client.get("/api/v1/dashboard/feed")

        assert r.json()["attention"]["empty_shifts_soon"] == 0

    async def test_reports_pending_join_requests(
        self, async_client: AsyncClient, as_admin: None
    ):
        """The dashboard surfaces join requests waiting on this user."""
        r = await async_client.get("/api/v1/dashboard/feed")

        assert r.status_code == 200
        assert r.json()["pending_join_request_count"] == 0

    async def test_someone_in_no_event_sees_nothing_on_offer(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        as_outsider: None,
    ):
        """An empty visibility list means nothing, never everything."""
        await _add_shift(db_session, test_task, title="Nicht fuer dich")

        r = await async_client.get("/api/v1/dashboard/feed")

        data = r.json()
        assert data["open_shift_count"] == 0
        assert data["attention"] is None


@pytest.mark.asyncio
class TestDashboardSidebar:
    async def test_dashboard_sidebar(self, async_client: AsyncClient):
        """Test the sidebar data endpoint."""
        r = await async_client.get("/api/v1/dashboard/sidebar")

        assert r.status_code == 200
        data = r.json()
        assert "events" in data
        assert "tasks" in data
        assert "bookings" in data


# ---------------------------------------------------------------------------
# Teams (#179)
# ---------------------------------------------------------------------------


async def _team(
    db_session: AsyncSession, event: Event, name: str = "Kasse"
) -> EventTeam:
    team = EventTeam(event_id=event.id, name=name, requires_approval=True)
    db_session.add(team)
    await db_session.flush()
    await db_session.refresh(team)
    return team


async def _in_team(
    db_session: AsyncSession,
    team: EventTeam,
    user: User,
    *,
    status: str = "approved",
    role: str = "member",
) -> None:
    db_session.add(
        EventTeamMember(team_id=team.id, user_id=user.id, status=status, role=role)
    )
    await db_session.flush()


async def _applicant(db_session: AsyncSession, tag: str) -> User:
    user = User(
        subject=f"local|{tag}",
        email=f"{tag}@example.com",
        name=f"Applicant {tag}",
        roles=[],
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
class TestDashboardTeams:
    """Team gates on the open list, and the team requests waiting on the user."""

    async def test_open_shifts_leave_out_what_a_team_locks(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_event: Event,
    ):
        """A suggestion the user cannot take is a dead end, so it is not made."""
        team = await _team(db_session, test_event)
        test_task.team_id = team.id
        db_session.add(test_task)
        await _add_shift(db_session, test_task, title="Nur fuer die Kasse")

        r = await async_client.get("/api/v1/dashboard/feed")

        data = r.json()
        assert data["open_shift_count"] == 0
        assert data["open_shifts"] == []

    async def test_open_shifts_include_a_team_the_user_is_in(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_event: Event,
        test_user: User,
    ):
        team = await _team(db_session, test_event)
        await _in_team(db_session, team, test_user)
        test_task.team_id = team.id
        db_session.add(test_task)
        shift = await _add_shift(db_session, test_task, title="Kasse frueh")

        r = await async_client.get("/api/v1/dashboard/feed")

        assert [s["shift_id"] for s in r.json()["open_shifts"]] == [str(shift.id)]

    async def test_a_pending_request_does_not_unlock_the_shift(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_event: Event,
        test_user: User,
    ):
        team = await _team(db_session, test_event)
        await _in_team(db_session, team, test_user, status="pending")
        test_task.team_id = team.id
        db_session.add(test_task)
        await _add_shift(db_session, test_task)

        r = await async_client.get("/api/v1/dashboard/feed")

        assert r.json()["open_shift_count"] == 0

    async def test_event_admin_still_sees_locked_shifts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_event: Event,
        as_event_admin: None,
    ):
        """An event admin passes every team gate, so nothing is hidden from them."""
        team = await _team(db_session, test_event)
        test_task.team_id = team.id
        db_session.add(test_task)
        await _add_shift(db_session, test_task)

        r = await async_client.get("/api/v1/dashboard/feed")

        assert r.json()["open_shift_count"] == 1

    async def test_event_admin_counts_every_team_request(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        as_event_admin: None,
    ):
        kasse = await _team(db_session, test_event, "Kasse")
        bar = await _team(db_session, test_event, "Bar")
        await _in_team(
            db_session, kasse, await _applicant(db_session, "a1"), status="pending"
        )
        await _in_team(
            db_session, bar, await _applicant(db_session, "a2"), status="pending"
        )
        # Already decided: nothing left to do about these.
        await _in_team(db_session, bar, await _applicant(db_session, "a3"))
        await _in_team(
            db_session, bar, await _applicant(db_session, "a4"), status="declined"
        )

        r = await async_client.get("/api/v1/dashboard/feed")

        data = r.json()
        assert data["pending_team_request_count"] == 2
        assert data["attention"]["pending_team_requests"] == 2

    async def test_team_lead_counts_only_their_own_team(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ):
        """``test_user`` is a plain event member who leads one team."""
        kasse = await _team(db_session, test_event, "Kasse")
        bar = await _team(db_session, test_event, "Bar")
        await _in_team(db_session, kasse, test_user, role="lead")
        await _in_team(
            db_session, kasse, await _applicant(db_session, "b1"), status="pending"
        )
        await _in_team(
            db_session, bar, await _applicant(db_session, "b2"), status="pending"
        )

        r = await async_client.get("/api/v1/dashboard/feed")

        data = r.json()
        assert data["pending_team_request_count"] == 1
        # A lead is not an organiser: the count, but no attention block.
        assert data["attention"] is None

    async def test_plain_member_has_no_team_requests_to_decide(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ):
        kasse = await _team(db_session, test_event)
        # Being an ordinary member of the team is not enough to decide.
        await _in_team(db_session, kasse, test_user)
        await _in_team(
            db_session, kasse, await _applicant(db_session, "c1"), status="pending"
        )

        r = await async_client.get("/api/v1/dashboard/feed")

        assert r.json()["pending_team_request_count"] == 0

    async def test_attention_is_scoped_to_the_event_in_view(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_draft_event: Event,
        test_event_admin_user: User,
        as_event_admin: None,
    ):
        """The to-do list is about the event in view; the badge is about all."""
        here = await _team(db_session, test_event, "Hier")
        there = await _team(db_session, test_draft_event, "Dort")
        await _in_team(
            db_session, here, await _applicant(db_session, "d1"), status="pending"
        )
        await _in_team(
            db_session, there, await _applicant(db_session, "d2"), status="pending"
        )
        test_event_admin_user.selected_event_id = test_event.id
        db_session.add(test_event_admin_user)
        await db_session.flush()

        r = await async_client.get("/api/v1/dashboard/feed")

        data = r.json()
        assert data["pending_team_request_count"] == 2
        assert data["attention"]["pending_team_requests"] == 1

    async def test_superadmin_counts_requests_outside_demo_events(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        as_admin: None,
    ):
        team = await _team(db_session, test_event)
        await _in_team(
            db_session, team, await _applicant(db_session, "e1"), status="pending"
        )

        r = await async_client.get("/api/v1/dashboard/feed")

        assert r.json()["pending_team_request_count"] == 1
