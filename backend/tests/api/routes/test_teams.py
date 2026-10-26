"""Teams inside an event, and the booking gate they put on a task (#179)."""

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, time, timedelta
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.event_team import event_team as crud_team
from app.models.booking import Booking
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.event_team import EventTeam, EventTeamMember, EventTeamRequirement
from app.models.location import Location
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from tests.fixtures.client import (
    _restore,  # pyright: ignore[reportPrivateUsage]
    _swap_identity,  # pyright: ignore[reportPrivateUsage]
)


@contextmanager
def act_as(app: FastAPI, user: User) -> Generator[None]:
    """Switch identity for part of a test, then switch back."""
    originals = _swap_identity(app, user, superuser=False)
    try:
        yield
    finally:
        _restore(app, originals)


@pytest_asyncio.fixture
async def team(db_session: AsyncSession, test_event: Event) -> EventTeam:
    """A restricted team in ``test_event``."""
    row = EventTeam(
        event_id=test_event.id,
        name="Kasse",
        description="Cash desk",
        contact="Anna, 0151 000000",
        requires_approval=True,
    )
    db_session.add(row)
    await db_session.flush()
    await db_session.refresh(row)
    return row


@pytest_asyncio.fixture
async def open_team(db_session: AsyncSession, test_event: Event) -> EventTeam:
    row = EventTeam(event_id=test_event.id, name="Aufbau", requires_approval=False)
    db_session.add(row)
    await db_session.flush()
    await db_session.refresh(row)
    return row


@pytest_asyncio.fixture
async def gated_shift(db_session: AsyncSession, test_task: Task, team: EventTeam):
    """A shift in ``test_task``, with the task gated on ``team``."""
    test_task.team_id = team.id
    db_session.add(test_task)
    shift = Shift(
        task_id=test_task.id,
        title="Kasse früh",
        date=date(2026, 6, 11),
        start_time=time(9, 0),
        end_time=time(12, 0),
        max_bookings=3,
    )
    db_session.add(shift)
    await db_session.flush()
    await db_session.refresh(shift)
    return shift


async def _member_row(
    db_session: AsyncSession,
    team: EventTeam,
    user: User,
    *,
    status: str = "approved",
    role: str = "member",
) -> EventTeamMember:
    row = EventTeamMember(team_id=team.id, user_id=user.id, status=status, role=role)
    db_session.add(row)
    await db_session.flush()
    return row


def _teams_url(event: Event) -> str:
    return f"/api/v1/events/{event.id}/teams"


@pytest.mark.asyncio
class TestTeamManagement:
    async def test_event_admin_creates_a_team(
        self, async_client: AsyncClient, test_event: Event, as_event_admin: None
    ):
        r = await async_client.post(
            _teams_url(test_event),
            json={"name": " Küche ", "description": "Kitchen", "contact": "Ben"},
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["name"] == "Küche"
        assert data["requires_approval"] is True
        assert data["can_manage"] is True

    async def test_member_cannot_create_a_team(
        self, async_client: AsyncClient, test_event: Event
    ):
        r = await async_client.post(_teams_url(test_event), json={"name": "Küche"})
        assert r.status_code == 403

    async def test_names_are_unique_per_event_ignoring_case(
        self,
        async_client: AsyncClient,
        test_event: Event,
        team: EventTeam,
        as_event_admin: None,
    ):
        r = await async_client.post(_teams_url(test_event), json={"name": "KASSE"})
        assert r.status_code == 409
        assert r.json()["code"] == "team.name_taken"

    async def test_outsider_cannot_list_teams(
        self,
        async_client: AsyncClient,
        test_private_event: Event,
        as_outsider: None,
    ):
        r = await async_client.get(_teams_url(test_private_event))
        assert r.status_code == 403

    async def test_list_shows_my_standing(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        open_team: EventTeam,
        test_user: User,
    ):
        await _member_row(db_session, team, test_user, status="pending")
        r = await async_client.get(_teams_url(test_event))
        assert r.status_code == 200
        by_name = {t["name"]: t for t in r.json()}
        assert by_name["Kasse"]["my_status"] == "pending"
        assert by_name["Kasse"]["can_manage"] is False
        # A plain member is not told how many requests are queued.
        assert by_name["Kasse"]["pending_count"] == 0
        assert by_name["Aufbau"]["my_status"] is None

    async def test_team_from_another_event_is_not_found(
        self,
        async_client: AsyncClient,
        test_draft_event: Event,
        team: EventTeam,
        as_event_admin: None,
    ):
        r = await async_client.patch(
            f"{_teams_url(test_draft_event)}/{team.id}", json={"name": "x"}
        )
        assert r.status_code == 404

    async def test_deleting_a_team_opens_its_tasks(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        gated_shift: Shift,
        test_task: Task,
        as_event_admin: None,
    ):
        r = await async_client.delete(f"{_teams_url(test_event)}/{team.id}")
        assert r.status_code == 204
        await db_session.refresh(test_task)
        assert test_task.team_id is None


@pytest.mark.asyncio
class TestJoining:
    async def test_open_team_joins_at_once(
        self, async_client: AsyncClient, test_event: Event, open_team: EventTeam
    ):
        r = await async_client.post(
            f"{_teams_url(test_event)}/{open_team.id}/join", json={}
        )
        assert r.status_code == 201
        assert r.json()["status"] == "approved"

    async def test_restricted_team_opens_a_request(
        self, async_client: AsyncClient, test_event: Event, team: EventTeam
    ):
        url = f"{_teams_url(test_event)}/{team.id}/join"
        r = await async_client.post(url, json={"message": "I did this last year"})
        assert r.status_code == 201
        assert r.json()["status"] == "pending"

        again = await async_client.post(url, json={})
        assert again.status_code == 409
        assert again.json()["code"] == "team.request_pending"

    async def test_declined_request_can_be_reopened(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        test_user: User,
    ):
        await _member_row(db_session, team, test_user, status="declined")
        r = await async_client.post(f"{_teams_url(test_event)}/{team.id}/join", json={})
        assert r.status_code == 201
        assert r.json()["status"] == "pending"

    async def test_non_member_of_event_cannot_join(
        self,
        async_client: AsyncClient,
        test_event: Event,
        team: EventTeam,
        as_outsider: None,
    ):
        r = await async_client.post(f"{_teams_url(test_event)}/{team.id}/join", json={})
        assert r.status_code == 403

    async def test_leave(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        test_user: User,
    ):
        await _member_row(db_session, team, test_user)
        r = await async_client.delete(f"{_teams_url(test_event)}/{team.id}/join")
        assert r.status_code == 204
        again = await async_client.delete(f"{_teams_url(test_event)}/{team.id}/join")
        assert again.status_code == 404


@pytest.mark.asyncio
class TestDeciding:
    async def test_event_admin_approves(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        await _member_row(db_session, team, test_user, status="pending")
        base = f"{_teams_url(test_event)}/{team.id}/members"

        pending = await async_client.get(base, params={"status": "pending"})
        assert [m["user_id"] for m in pending.json()] == [str(test_user.id)]

        r = await async_client.post(
            f"{base}/{test_user.id}/decide", json={"approve": True}
        )
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

        again = await async_client.post(
            f"{base}/{test_user.id}/decide", json={"approve": False}
        )
        assert again.status_code == 409

    async def test_plain_member_cannot_decide_or_see_roster(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        test_event_admin_user: User,
    ):
        base = f"{_teams_url(test_event)}/{team.id}/members"
        assert (await async_client.get(base)).status_code == 403
        r = await async_client.post(
            f"{base}/{test_event_admin_user.id}/decide", json={"approve": True}
        )
        assert r.status_code == 403
        assert r.json()["code"] == "team.forbidden"

    async def test_lead_decides_and_adds_but_cannot_appoint_leads(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        test_user: User,
        test_outsider_user: User,
    ):
        """``test_user`` (an event member) leads the team."""
        await _member_row(db_session, team, test_user, role="lead")
        db_session.add(
            EventMembership(
                user_id=test_outsider_user.id, event_id=test_event.id, role="member"
            )
        )
        await _member_row(db_session, team, test_outsider_user, status="pending")
        base = f"{_teams_url(test_event)}/{team.id}/members"

        r = await async_client.post(
            f"{base}/{test_outsider_user.id}/decide", json={"approve": True}
        )
        assert r.status_code == 200

        lead = await async_client.post(
            base, json={"user_id": str(test_outsider_user.id), "role": "lead"}
        )
        assert lead.status_code == 403

        listing = await async_client.get(_teams_url(test_event))
        assert listing.json()[0]["can_manage"] is True

    async def test_only_event_members_can_be_added(
        self,
        async_client: AsyncClient,
        test_event: Event,
        team: EventTeam,
        test_outsider_user: User,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"{_teams_url(test_event)}/{team.id}/members",
            json={"user_id": str(test_outsider_user.id)},
        )
        assert r.status_code == 422
        assert r.json()["code"] == "team.not_event_member"

    async def test_admin_appoints_a_lead(
        self,
        async_client: AsyncClient,
        test_event: Event,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        base = f"{_teams_url(test_event)}/{team.id}/members"
        r = await async_client.post(
            base, json={"user_id": str(test_user.id), "role": "lead"}
        )
        assert r.status_code == 201
        assert r.json()["role"] == "lead"
        assert r.json()["status"] == "approved"

        demote = await async_client.patch(
            f"{base}/{test_user.id}", json={"role": "member"}
        )
        assert demote.json()["role"] == "member"


@pytest.mark.asyncio
class TestBookingGate:
    async def test_non_member_of_team_is_refused(
        self, async_client: AsyncClient, gated_shift: Shift, team: EventTeam
    ):
        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(gated_shift.id)}
        )
        assert r.status_code == 403
        body = r.json()
        assert body["code"] == "booking.team_required"
        assert body["team_id"] == str(team.id)
        assert body["team_name"] == "Kasse"

    async def test_pending_request_is_not_enough(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        gated_shift: Shift,
        team: EventTeam,
        test_user: User,
    ):
        await _member_row(db_session, team, test_user, status="pending")
        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(gated_shift.id)}
        )
        assert r.status_code == 403

    async def test_approved_member_books(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        gated_shift: Shift,
        team: EventTeam,
        test_user: User,
    ):
        await _member_row(db_session, team, test_user)
        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(gated_shift.id)}
        )
        assert r.status_code == 201, r.text

    async def test_event_admin_books_without_the_team(
        self, async_client: AsyncClient, gated_shift: Shift, as_event_admin: None
    ):
        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(gated_shift.id)}
        )
        assert r.status_code == 201

    async def test_ungated_task_is_unaffected(
        self, async_client: AsyncClient, test_shift: Shift, team: EventTeam
    ):
        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(test_shift.id)}
        )
        assert r.status_code == 201

    async def test_leaving_the_event_drops_team_access(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        test_user: User,
    ):
        await _member_row(db_session, team, test_user)
        r = await async_client.delete(
            f"/api/v1/events/{test_event.id}/members/{test_user.id}"
        )
        assert r.status_code == 204
        left = await db_session.execute(
            select(func.count())
            .select_from(EventTeamMember)
            .where(EventTeamMember.user_id == test_user.id)  # type: ignore[arg-type]
        )
        assert left.scalar_one() == 0


@pytest.mark.asyncio
class TestTaskTeamField:
    async def test_set_team_on_task(
        self,
        async_client: AsyncClient,
        test_task: Task,
        team: EventTeam,
        as_event_admin: None,
    ):
        r = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}", json={"team_id": str(team.id)}
        )
        assert r.status_code == 200, r.text
        assert r.json()["team_id"] == str(team.id)

    async def test_team_from_another_event_is_refused(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_draft_event: Event,
        as_event_admin: None,
    ):
        foreign = EventTeam(event_id=test_draft_event.id, name="Fremd")
        db_session.add(foreign)
        await db_session.flush()
        r = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}", json={"team_id": str(foreign.id)}
        )
        assert r.status_code == 422
        assert r.json()["code"] == "task.team_not_in_event"

    async def test_moving_a_task_drops_its_team(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        gated_shift: Shift,
        test_draft_event: Event,
        as_event_admin: None,
    ):
        r = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}",
            json={"event_id": str(test_draft_event.id)},
        )
        assert r.status_code == 200, r.text
        assert r.json()["team_id"] is None


@pytest.mark.asyncio
class TestClone:
    async def test_clone_copies_teams_and_remaps_tasks(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        gated_shift: Shift,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        await _member_row(db_session, team, test_user)
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/clone",
            json={
                "name": "Kirchentags Woche 2027",
                "start_date": "2027-06-09",
                "copy_members": True,
                "tasks": [{"source_task_id": str(test_task.id)}],
            },
        )
        assert r.status_code == 201, r.text
        new_event_id = uuid.UUID(r.json()["event"]["id"])

        new_team = (
            await db_session.execute(
                select(EventTeam).where(EventTeam.event_id == new_event_id)  # type: ignore[arg-type]
            )
        ).scalar_one()
        assert new_team.id != team.id
        assert new_team.name == "Kasse"

        new_task = (
            await db_session.execute(
                select(Task).where(Task.event_id == new_event_id)  # type: ignore[arg-type]
            )
        ).scalar_one()
        assert new_task.team_id == new_team.id

        carried = (
            await db_session.execute(
                select(EventTeamMember).where(
                    EventTeamMember.team_id == new_team.id  # type: ignore[arg-type]
                )
            )
        ).scalar_one()
        assert carried.user_id == test_user.id


@pytest.mark.asyncio
class TestDeletionCascades:
    async def test_deleting_the_event_owner_with_a_gated_task(
        self,
        db_session: AsyncSession,
        gated_shift: Shift,
        team: EventTeam,
        test_admin_user: User,
        test_user: User,
    ):
        """Regression guard for the deferred ``tasks.team_id`` check.

        Deleting the owner cascades to the event and from there to its teams,
        while the events->tasks SET NULL rewrites the task and re-checks
        team_id against a team the same statement already removed.
        """
        await _member_row(db_session, team, test_user)
        await db_session.delete(test_admin_user)
        await db_session.flush()
        # The test never commits, so make the deferred checks run now.
        await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

        remaining = await db_session.execute(
            select(func.count()).select_from(EventTeam)
        )
        assert remaining.scalar_one() == 0

    async def test_deleting_a_decider_keeps_the_membership(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        test_user: User,
        test_event_admin_user: User,
        app: FastAPI,
    ):
        """The approver deleting their account must not revoke the approval.

        ``decided_by_id`` has no foreign key for exactly this reason (a
        CASCADE would delete the row, SET NULL is the models/CLAUDE.md trap);
        the name stays for display.
        """
        await _member_row(db_session, team, test_user, status="pending")
        with act_as(app, test_event_admin_user):
            r = await async_client.post(
                f"/api/v1/events/{team.event_id}/teams/{team.id}/members/"
                f"{test_user.id}/decide",
                json={"approve": True},
            )
        assert r.status_code == 200, r.text

        await db_session.delete(test_event_admin_user)
        await db_session.flush()
        await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

        row = (
            await db_session.execute(
                select(EventTeamMember)
                .where(EventTeamMember.user_id == test_user.id)  # type: ignore[arg-type]
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert row.status == "approved"
        assert row.decided_by_name == "Manager User"


@pytest.mark.asyncio
class TestShiftFlags:
    async def test_shift_says_it_is_locked(
        self, async_client: AsyncClient, gated_shift: Shift, team: EventTeam
    ):
        r = await async_client.get(f"/api/v1/shifts/{gated_shift.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["team_id"] == str(team.id)
        assert data["team_name"] == "Kasse"
        assert data["locked_by_team"] is True

    async def test_listing_unlocks_for_an_approved_member(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        gated_shift: Shift,
        test_task: Task,
        team: EventTeam,
        test_user: User,
    ):
        await _member_row(db_session, team, test_user)
        r = await async_client.get(
            "/api/v1/shifts/", params={"task_id": str(test_task.id)}
        )
        assert r.status_code == 200
        (item,) = [i for i in r.json()["items"] if i["id"] == str(gated_shift.id)]
        assert item["team_name"] == "Kasse"
        assert item["locked_by_team"] is False

    async def test_event_admin_is_never_locked(
        self, async_client: AsyncClient, gated_shift: Shift, as_event_admin: None
    ):
        r = await async_client.get(f"/api/v1/shifts/{gated_shift.id}")
        assert r.json()["locked_by_team"] is False


# --- Review follow-ups --------------------------------------------------


SCHEDULE: dict[str, Any] = {
    "default_start_time": "10:00:00",
    "default_end_time": "12:00:00",
    "shift_duration_minutes": 60,
    "people_per_shift": 2,
}


async def _event_member(
    db_session: AsyncSession, user: User, event: Event, role: str = "member"
) -> None:
    db_session.add(EventMembership(user_id=user.id, event_id=event.id, role=role))
    await db_session.flush()


async def _future_shift(db_session: AsyncSession, task: Task, days: int = 7) -> Shift:
    shift = Shift(
        task_id=task.id,
        title="Später",
        date=date.today() + timedelta(days=days),
        start_time=time(9, 0),
        end_time=time(12, 0),
        max_bookings=2,
    )
    db_session.add(shift)
    await db_session.flush()
    return shift


def _team_url(team: EventTeam) -> str:
    return f"/api/v1/events/{team.event_id}/teams/{team.id}"


@pytest.mark.asyncio
class TestTeamEditing:
    async def test_admin_edits_a_team(
        self,
        async_client: AsyncClient,
        team: EventTeam,
        as_event_admin: None,
    ):
        r = await async_client.patch(
            _team_url(team),
            json={"name": " Kasse 2 ", "requires_approval": False, "contact": None},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "Kasse 2"
        assert data["requires_approval"] is False
        assert data["contact"] is None

    @pytest.mark.parametrize(
        "body", [{"name": None}, {"requires_approval": None}, {"name": "   "}]
    )
    async def test_null_or_blank_is_refused(
        self,
        async_client: AsyncClient,
        team: EventTeam,
        as_event_admin: None,
        body: dict[str, Any],
    ):
        r = await async_client.patch(_team_url(team), json=body)
        assert r.status_code == 422

    async def test_blank_name_on_create_is_refused(
        self, async_client: AsyncClient, test_event: Event, as_event_admin: None
    ):
        r = await async_client.post(_teams_url(test_event), json={"name": "  "})
        assert r.status_code == 422

    async def test_renaming_onto_another_team_is_409(
        self,
        async_client: AsyncClient,
        team: EventTeam,
        open_team: EventTeam,
        as_event_admin: None,
    ):
        r = await async_client.patch(_team_url(open_team), json={"name": "kasse"})
        assert r.status_code == 409
        assert r.json()["code"] == "team.name_taken"

    async def test_recasing_own_name_is_allowed(
        self, async_client: AsyncClient, team: EventTeam, as_event_admin: None
    ):
        r = await async_client.patch(_team_url(team), json={"name": "KASSE"})
        assert r.status_code == 200
        assert r.json()["name"] == "KASSE"

    async def test_member_cannot_edit(self, async_client: AsyncClient, team: EventTeam):
        r = await async_client.patch(_team_url(team), json={"name": "x"})
        assert r.status_code == 403

    async def test_lost_race_on_the_name_is_409(
        self,
        async_client: AsyncClient,
        test_event: Event,
        team: EventTeam,
        as_event_admin: None,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """The pre-check passes, the unique index catches it: still a 409."""

        async def no_clash(*_args: Any, **_kwargs: Any) -> None:
            return None

        monkeypatch.setattr(crud_team, "get_by_name_ci", no_clash)
        r = await async_client.post(_teams_url(test_event), json={"name": "kasse"})
        assert r.status_code == 409
        assert r.json()["code"] == "team.name_taken"
        # The savepoint kept the transaction usable.
        listing = await async_client.get(_teams_url(test_event))
        assert listing.status_code == 200

    async def test_opening_a_team_approves_waiting_requests(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        row = await _member_row(db_session, team, test_user, status="pending")
        r = await async_client.patch(_team_url(team), json={"requires_approval": False})
        assert r.status_code == 200
        await db_session.refresh(row)
        assert row.status == "approved"
        assert row.decided_by_name == "Manager User"

    async def test_pending_row_on_an_opened_team_can_join(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        open_team: EventTeam,
        test_user: User,
    ):
        """A request stranded by a switch made elsewhere is let through."""
        await _member_row(db_session, open_team, test_user, status="pending")
        r = await async_client.post(f"{_team_url(open_team)}/join", json={})
        assert r.status_code == 201
        assert r.json()["status"] == "approved"


@pytest.mark.asyncio
class TestScopedLookups:
    @pytest.mark.parametrize(
        ("method", "suffix"),
        [
            ("POST", "/join"),
            ("DELETE", "/join"),
            ("GET", "/members"),
            ("POST", "/members/{uid}/decide"),
            ("DELETE", "/members/{uid}"),
            ("PUT", "/members/{uid}/checks"),
            ("GET", "/members/{uid}/documents/{uid}"),
            ("DELETE", ""),
            ("PATCH", ""),
        ],
    )
    async def test_team_from_another_event_is_404_everywhere(
        self,
        async_client: AsyncClient,
        test_draft_event: Event,
        team: EventTeam,
        test_user: User,
        as_admin: None,
        method: str,
        suffix: str,
    ):
        """As the superadmin, so a 404 can only come from the scoped lookup."""
        url = f"{_teams_url(test_draft_event)}/{team.id}" + suffix.format(
            uid=test_user.id
        )
        body: dict[str, Any] = {"approve": True, "name": "x"}
        if method == "PUT":
            body = {"checks": [{"requirement_id": str(uuid.uuid4())}]}
        if method in ("POST", "PATCH", "PUT"):
            r = await async_client.request(method, url, json=body)
        else:
            r = await async_client.request(method, url)
        assert r.status_code == 404, r.text
        assert r.json()["code"] == "team.not_found"


@pytest.mark.asyncio
class TestRemoving:
    async def test_lead_removes_a_plain_member(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        test_user: User,
        test_outsider_user: User,
    ):
        await _member_row(db_session, team, test_user, role="lead")
        await _event_member(db_session, test_outsider_user, test_event)
        await _member_row(db_session, team, test_outsider_user)
        r = await async_client.delete(
            f"{_team_url(team)}/members/{test_outsider_user.id}"
        )
        assert r.status_code == 204
        gone = await crud_team.get_member(
            db_session, team_id=team.id, user_id=test_outsider_user.id
        )
        assert gone is None

    async def test_lead_cannot_remove_another_lead(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        test_user: User,
        test_outsider_user: User,
    ):
        await _member_row(db_session, team, test_user, role="lead")
        await _event_member(db_session, test_outsider_user, test_event)
        await _member_row(db_session, team, test_outsider_user, role="lead")
        r = await async_client.delete(
            f"{_team_url(team)}/members/{test_outsider_user.id}"
        )
        assert r.status_code == 403
        assert r.json()["code"] == "event.forbidden"
        assert await crud_team.get_member(
            db_session, team_id=team.id, user_id=test_outsider_user.id
        )

    async def test_lead_can_step_out_themselves(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        test_user: User,
    ):
        await _member_row(db_session, team, test_user, role="lead")
        r = await async_client.delete(f"{_team_url(team)}/members/{test_user.id}")
        assert r.status_code == 204

    async def test_event_admin_removes_a_lead(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        await _member_row(db_session, team, test_user, role="lead")
        r = await async_client.delete(f"{_team_url(team)}/members/{test_user.id}")
        assert r.status_code == 204

    async def test_unknown_member_is_404(
        self,
        async_client: AsyncClient,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        r = await async_client.delete(f"{_team_url(team)}/members/{test_user.id}")
        assert r.status_code == 404
        assert r.json()["code"] == "team.member_not_found"

    async def test_plain_member_cannot_remove(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        test_event_admin_user: User,
    ):
        await _member_row(db_session, team, test_event_admin_user)
        r = await async_client.delete(
            f"{_team_url(team)}/members/{test_event_admin_user.id}"
        )
        assert r.status_code == 403
        assert r.json()["code"] == "team.forbidden"


@pytest.mark.asyncio
class TestRosterGuards:
    async def test_lead_cannot_demote_a_co_lead_through_add(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        test_user: User,
        test_outsider_user: User,
    ):
        await _member_row(db_session, team, test_user, role="lead")
        await _event_member(db_session, test_outsider_user, test_event)
        co_lead = await _member_row(db_session, team, test_outsider_user, role="lead")
        r = await async_client.post(
            f"{_team_url(team)}/members",
            json={"user_id": str(test_outsider_user.id), "role": "member"},
        )
        assert r.status_code == 409
        assert r.json()["code"] == "team.already_member"
        await db_session.refresh(co_lead)
        assert co_lead.role == "lead"

    async def test_adding_approves_a_pending_request(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        await _member_row(db_session, team, test_user, status="pending")
        r = await async_client.post(
            f"{_team_url(team)}/members", json={"user_id": str(test_user.id)}
        )
        assert r.status_code == 201
        assert r.json()["status"] == "approved"

    async def test_lead_cannot_change_roles(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        test_user: User,
        test_outsider_user: User,
    ):
        await _member_row(db_session, team, test_user, role="lead")
        await _event_member(db_session, test_outsider_user, test_event)
        await _member_row(db_session, team, test_outsider_user)
        r = await async_client.patch(
            f"{_team_url(team)}/members/{test_outsider_user.id}",
            json={"role": "lead"},
        )
        assert r.status_code == 403

    async def test_pending_member_cannot_be_made_lead(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        await _member_row(db_session, team, test_user, status="pending")
        r = await async_client.patch(
            f"{_team_url(team)}/members/{test_user.id}", json={"role": "lead"}
        )
        assert r.status_code == 404
        assert r.json()["code"] == "team.member_not_found"

    async def test_status_filter_is_checked(
        self, async_client: AsyncClient, team: EventTeam, as_event_admin: None
    ):
        r = await async_client.get(
            f"{_team_url(team)}/members", params={"status": "nope"}
        )
        assert r.status_code == 422


@pytest.mark.asyncio
class TestDecidingMore:
    async def test_event_admin_declines(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        gated_shift: Shift,
        test_user: User,
        test_event_admin_user: User,
        app: FastAPI,
    ):
        await _member_row(db_session, team, test_user, status="pending")
        with act_as(app, test_event_admin_user):
            r = await async_client.post(
                f"{_team_url(team)}/members/{test_user.id}/decide",
                json={"approve": False},
            )
        assert r.status_code == 200
        assert r.json()["status"] == "declined"
        assert r.json()["decided_by_name"] == "Manager User"
        booking = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(gated_shift.id)}
        )
        assert booking.status_code == 403

    async def test_deciding_someone_without_a_request_is_404(
        self,
        async_client: AsyncClient,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"{_team_url(team)}/members/{test_user.id}/decide",
            json={"approve": True},
        )
        assert r.status_code == 404
        assert r.json()["code"] == "team.request_not_found"

    async def test_already_member_cannot_join_again(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        test_user: User,
    ):
        await _member_row(db_session, team, test_user)
        r = await async_client.post(f"{_team_url(team)}/join", json={})
        assert r.status_code == 409
        assert r.json()["code"] == "team.already_member"

    async def test_lead_sees_the_pending_count(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        test_user: User,
        test_outsider_user: User,
    ):
        await _member_row(db_session, team, test_user, role="lead")
        await _event_member(db_session, test_outsider_user, test_event)
        await _member_row(db_session, team, test_outsider_user, status="pending")
        [before] = (await async_client.get(_teams_url(test_event))).json()
        assert before["pending_count"] == 1
        assert before["lead_names"] == ["Test User"]
        r = await async_client.post(
            f"{_team_url(team)}/members/{test_outsider_user.id}/decide",
            json={"approve": True},
        )
        assert r.status_code == 200
        [after] = (await async_client.get(_teams_url(test_event))).json()
        assert after["pending_count"] == 0

    async def test_lead_of_one_team_cannot_manage_another(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        open_team: EventTeam,
        test_user: User,
    ):
        await _member_row(db_session, open_team, test_user, role="lead")
        r = await async_client.get(f"{_team_url(team)}/members")
        assert r.status_code == 403
        assert r.json()["code"] == "team.forbidden"
        listing = (await async_client.get(_teams_url(test_event))).json()
        by_name = {t["name"]: t for t in listing}
        assert by_name["Kasse"]["can_manage"] is False
        assert by_name["Aufbau"]["can_manage"] is True

    async def test_requests_across_teams(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        open_team: EventTeam,
        test_user: User,
        test_outsider_user: User,
        test_event_admin_user: User,
        app: FastAPI,
    ):
        """An admin sees every waiting request, a lead those of their team."""
        await _event_member(db_session, test_outsider_user, test_event)
        await _member_row(db_session, team, test_outsider_user, status="pending")
        await _member_row(db_session, open_team, test_outsider_user)
        await _member_row(db_session, open_team, test_user, role="lead")
        url = f"{_teams_url(test_event)}/requests"

        mine = await async_client.get(url)
        assert mine.status_code == 200
        assert mine.json() == []

        with act_as(app, test_event_admin_user):
            everything = await async_client.get(url)
        [request] = everything.json()
        assert request["team_name"] == "Kasse"
        assert request["user_name"] == "Outsider User"
        assert request["other_team_names"] == ["Aufbau"]
        assert request["booked_shift_count"] == 0

    async def test_outsider_cannot_list_requests(
        self,
        async_client: AsyncClient,
        test_private_event: Event,
        as_outsider: None,
    ):
        r = await async_client.get(f"{_teams_url(test_private_event)}/requests")
        assert r.status_code == 403


@pytest.mark.asyncio
class TestNavigationCounts:
    async def test_event_read_counts_teams_and_my_requests(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        open_team: EventTeam,
        test_user: User,
        test_outsider_user: User,
        test_event_admin_user: User,
        app: FastAPI,
    ):
        await _event_member(db_session, test_outsider_user, test_event)
        await _member_row(db_session, team, test_outsider_user, status="pending")
        url = f"/api/v1/events/{test_event.id}"

        mine = (await async_client.get(url)).json()
        assert mine["team_count"] == 2
        assert mine["pending_team_request_count"] == 0

        await _member_row(db_session, team, test_user, role="lead")
        lead = (await async_client.get(url)).json()
        assert lead["pending_team_request_count"] == 1

        with act_as(app, test_event_admin_user):
            admin = (await async_client.get(url)).json()
        assert admin["pending_team_request_count"] == 1

    async def test_visitor_is_not_told_about_teams(
        self,
        async_client: AsyncClient,
        test_event: Event,
        team: EventTeam,
        as_outsider: None,
    ):
        r = await async_client.get(f"/api/v1/events/{test_event.id}")
        assert r.status_code == 200
        assert r.json()["team_count"] == 0

    async def test_team_lists_its_tasks_and_open_shifts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        test_task: Task,
        test_draft_task: Task,
    ):
        test_task.team_id = team.id
        test_draft_task.team_id = team.id
        db_session.add_all([test_task, test_draft_task])
        await _future_shift(db_session, test_task)
        full = await _future_shift(db_session, test_task, days=8)
        full.max_bookings = 0
        await _future_shift(db_session, test_draft_task)
        await db_session.flush()

        [data] = (await async_client.get(_teams_url(test_event))).json()
        # The draft task is the admins' business.
        assert data["tasks"] == [
            {"id": str(test_task.id), "name": "Pfingsten 2026", "open_shift_count": 1}
        ]
        assert data["open_shift_count"] == 1
        assert data["task_count"] == 2


@pytest.mark.asyncio
class TestBookingGateMore:
    async def test_patch_cannot_reconfirm_a_cancelled_booking(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        gated_shift: Shift,
        team: EventTeam,
        test_user: User,
    ):
        """Cancel, leave the team, then try to PATCH the booking back."""
        await _member_row(db_session, team, test_user)
        booked = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(gated_shift.id)}
        )
        assert booked.status_code == 201
        booking_id = booked.json()["id"]
        await async_client.delete(f"/api/v1/bookings/{booking_id}")
        await async_client.delete(f"{_team_url(team)}/join")

        r = await async_client.patch(
            f"/api/v1/bookings/{booking_id}", json={"status": "confirmed"}
        )
        assert r.status_code == 422
        assert r.json()["code"] == "booking.rebook_required"
        row = await db_session.get(Booking, uuid.UUID(booking_id))
        assert row is not None and row.status == "cancelled"

        again = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(gated_shift.id)}
        )
        assert again.status_code == 403

    async def test_removal_spares_other_events(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_private_event: Event,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        await _member_row(db_session, team, test_user)
        await _event_member(db_session, test_user, test_private_event)
        elsewhere = EventTeam(event_id=test_private_event.id, name="Andere")
        db_session.add(elsewhere)
        await db_session.flush()
        await _member_row(db_session, elsewhere, test_user)

        r = await async_client.delete(
            f"/api/v1/events/{test_event.id}/members/{test_user.id}"
        )
        assert r.status_code == 204
        here = await crud_team.get_member(
            db_session, team_id=team.id, user_id=test_user.id
        )
        assert here is None
        assert await crud_team.get_member(
            db_session, team_id=elsewhere.id, user_id=test_user.id
        )

    async def test_rejoining_the_event_does_not_restore_team_access(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        gated_shift: Shift,
        test_user: User,
    ):
        await _member_row(db_session, team, test_user)
        r = await async_client.delete(
            f"/api/v1/events/{test_event.id}/members/{test_user.id}"
        )
        assert r.status_code == 204
        await _event_member(db_session, test_user, test_event)
        booking = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(gated_shift.id)}
        )
        assert booking.status_code == 403
        assert booking.json()["code"] == "booking.team_required"


@pytest.mark.asyncio
class TestTaskTeamFieldMore:
    def _task(self, event: Event, team_id: uuid.UUID) -> dict[str, Any]:
        return {
            "name": "Kasse",
            "start_date": "2026-06-11",
            "end_date": "2026-06-12",
            "event_id": str(event.id),
            "team_id": str(team_id),
        }

    async def test_create_task_with_team(
        self,
        async_client: AsyncClient,
        test_event: Event,
        team: EventTeam,
        as_event_admin: None,
    ):
        r = await async_client.post(
            "/api/v1/tasks/", json=self._task(test_event, team.id)
        )
        assert r.status_code == 201, r.text
        assert r.json()["team_id"] == str(team.id)

    async def test_create_task_with_foreign_team(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_draft_event: Event,
        as_event_admin: None,
    ):
        foreign = EventTeam(event_id=test_draft_event.id, name="Fremd")
        db_session.add(foreign)
        await db_session.flush()
        r = await async_client.post(
            "/api/v1/tasks/", json=self._task(test_event, foreign.id)
        )
        assert r.status_code == 422
        assert r.json()["code"] == "task.team_not_in_event"

    async def test_create_with_shifts_keeps_team(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        team: EventTeam,
        as_event_admin: None,
    ):
        r = await async_client.post(
            "/api/v1/tasks/with-shifts",
            json={**self._task(test_event, team.id), "schedule": SCHEDULE},
        )
        assert r.status_code == 201, r.text
        task = await db_session.get(Task, uuid.UUID(r.json()["task"]["id"]))
        assert task is not None and task.team_id == team.id

    async def test_create_with_shifts_and_new_event_refuses_a_team(
        self,
        async_client: AsyncClient,
        team: EventTeam,
        as_admin: None,
    ):
        """A brand-new event has no teams (only the superadmin may make one here)."""
        body = {
            "name": "Garderobe",
            "start_date": "2026-06-11",
            "end_date": "2026-06-12",
            "new_event": {
                "name": "Neu",
                "start_date": "2026-06-11",
                "end_date": "2026-06-12",
            },
            "team_id": str(team.id),
            "schedule": SCHEDULE,
        }
        r = await async_client.post("/api/v1/tasks/with-shifts", json=body)
        assert r.status_code == 422
        assert r.json()["code"] == "task.team_not_in_event"


@pytest.mark.asyncio
class TestCloneMore:
    async def _clone(
        self, client: AsyncClient, event: Event, task: Task, copy_members: bool
    ) -> uuid.UUID:
        r = await client.post(
            f"/api/v1/events/{event.id}/clone",
            json={
                "name": "Kirchentags Woche 2027",
                "start_date": "2027-06-09",
                "copy_members": copy_members,
                "tasks": [{"source_task_id": str(task.id)}],
            },
        )
        assert r.status_code == 201, r.text
        return uuid.UUID(r.json()["event"]["id"])

    async def test_clone_without_members_copies_empty_teams(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        gated_shift: Shift,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
    ):
        await _member_row(db_session, team, test_user)
        db_session.add(
            EventTeamRequirement(
                team_id=team.id,
                label="Führungszeugnis",
                ask_issue_date=True,
                valid_for_years=5,
            )
        )
        await db_session.flush()
        new_event_id = await self._clone(async_client, test_event, test_task, False)

        [new_team] = await crud_team.list_for_event(db_session, event_id=new_event_id)
        assert new_team.requires_approval is True
        new_task = (
            await db_session.execute(
                select(Task).where(Task.event_id == new_event_id)  # type: ignore[arg-type]
            )
        ).scalar_one()
        assert new_task.team_id == new_team.id
        members = await db_session.execute(
            select(func.count())
            .select_from(EventTeamMember)
            .where(EventTeamMember.team_id == new_team.id)  # type: ignore[arg-type]
        )
        assert members.scalar_one() == 0
        [req] = await crud_team.requirements(db_session, team_id=new_team.id)
        assert (req.label, req.ask_issue_date, req.valid_for_years) == (
            "Führungszeugnis",
            True,
            5,
        )

    async def test_clone_drops_pending_requests_and_keeps_leads(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        team: EventTeam,
        open_team: EventTeam,
        test_user: User,
        test_outsider_user: User,
        as_event_admin: None,
    ):
        """``open_team`` gates no task and is still copied."""
        await _member_row(db_session, team, test_user, role="lead")
        await _event_member(db_session, test_outsider_user, test_event)
        await _member_row(db_session, team, test_outsider_user, status="pending")
        new_event_id = await self._clone(async_client, test_event, test_task, True)

        new_teams = {
            t.name: t
            for t in await crud_team.list_for_event(db_session, event_id=new_event_id)
        }
        assert set(new_teams) == {"Kasse", "Aufbau"}
        rows = await crud_team.list_members(
            db_session, team_ids=[new_teams["Kasse"].id]
        )
        assert [(m.user_id, m.role, m.status) for m, _ in rows] == [
            (test_user.id, "lead", "approved")
        ]


@pytest.mark.asyncio
class TestShiftFlagsMore:
    async def test_shift_carries_event_and_join_hints(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        gated_shift: Shift,
        team: EventTeam,
        test_event: Event,
        test_user: User,
    ):
        await _member_row(db_session, team, test_user, status="pending")
        data = (await async_client.get(f"/api/v1/shifts/{gated_shift.id}")).json()
        assert data["event_id"] == str(test_event.id)
        assert data["team_requires_approval"] is True
        assert data["my_team_status"] == "pending"
        assert data["locked_by_team"] is True

    async def test_ungated_shift_still_names_its_event(
        self, async_client: AsyncClient, test_shift: Shift, test_event: Event
    ):
        data = (await async_client.get(f"/api/v1/shifts/{test_shift.id}")).json()
        assert data["event_id"] == str(test_event.id)
        assert data["team_id"] is None
        assert data["locked_by_team"] is False

    async def test_location_shifts_carry_the_lock(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        gated_shift: Shift,
        test_location: Location,
        team: EventTeam,
        test_user: User,
    ):
        gated_shift.location_id = test_location.id
        db_session.add(gated_shift)
        await db_session.flush()
        url = f"/api/v1/locations/{test_location.id}/shifts"
        params = {"on": gated_shift.date.isoformat()}

        [item] = (await async_client.get(url, params=params)).json()
        assert item["team_name"] == "Kasse"
        assert item["locked_by_team"] is True

        await _member_row(db_session, team, test_user)
        [item] = (await async_client.get(url, params=params)).json()
        assert item["locked_by_team"] is False

    async def test_outsider_sees_public_gated_shift_as_locked(
        self, async_client: AsyncClient, gated_shift: Shift, as_outsider: None
    ):
        r = await async_client.get(f"/api/v1/shifts/{gated_shift.id}")
        assert r.status_code == 200
        assert r.json()["locked_by_team"] is True

    async def test_outsider_cannot_read_private_gated_shift(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        gated_shift: Shift,
        test_task: Task,
        test_private_event: Event,
        as_outsider: None,
    ):
        test_task.event_id = test_private_event.id
        db_session.add(test_task)
        await db_session.flush()
        r = await async_client.get(f"/api/v1/shifts/{gated_shift.id}")
        assert r.status_code == 404
        assert r.json()["code"] == "event.not_found"


@pytest.mark.asyncio
class TestTaskReadsAndFeed:
    async def test_task_page_says_it_is_locked(
        self, async_client: AsyncClient, gated_shift: Shift, test_task: Task
    ):
        data = (await async_client.get(f"/api/v1/tasks/{test_task.id}")).json()
        assert data["team_name"] == "Kasse"
        assert data["team_requires_approval"] is True
        assert data["my_team_status"] is None
        assert data["locked_by_team"] is True

    async def test_feed_marks_locked_tasks_and_shifts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        team: EventTeam,
    ):
        test_task.team_id = team.id
        test_task.end_date = date.today() + timedelta(days=30)
        db_session.add(test_task)
        await _future_shift(db_session, test_task, days=1)
        r = await async_client.get(
            "/api/v1/tasks/feed",
            params={"event_id": str(test_event.id), "view": "list"},
        )
        assert r.status_code == 200, r.text
        [item] = [i for i in r.json()["items"] if i["id"] == str(test_task.id)]
        assert item["team_name"] == "Kasse"
        assert item["locked_by_team"] is True
        assert item["shifts"]
        assert all(s["locked_by_team"] for s in item["shifts"])

    async def test_sidebar_shows_the_lock(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
        team: EventTeam,
    ):
        """A locked task's open count is no use to the viewer; the lock is."""
        test_task.team_id = team.id
        test_task.end_date = date.today() + timedelta(days=30)
        db_session.add(test_task)
        await _future_shift(db_session, test_task, days=1)

        async def sidebar_item() -> dict[str, Any]:
            r = await async_client.get("/api/v1/dashboard/sidebar")
            assert r.status_code == 200, r.text
            [item] = [t for t in r.json()["tasks"] if t["id"] == str(test_task.id)]
            return item

        item = await sidebar_item()
        assert item["team_name"] == "Kasse"
        assert item["locked_by_team"] is True

        await _member_row(db_session, team, test_user)
        assert (await sidebar_item())["locked_by_team"] is False

    async def test_feed_can_hide_what_i_cannot_book(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_user: User,
        team: EventTeam,
    ):
        open_task = Task(
            name="Offen",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            status="published",
            event_id=test_event.id,
        )
        db_session.add(open_task)
        test_task.team_id = team.id
        test_task.end_date = date.today() + timedelta(days=30)
        db_session.add(test_task)
        await db_session.flush()
        await _future_shift(db_session, test_task, days=1)
        await _future_shift(db_session, open_task, days=1)

        params = {"event_id": str(test_event.id), "view": "cards"}
        everything = await async_client.get("/api/v1/tasks/feed", params=params)
        assert {i["name"] for i in everything.json()["items"]} == {
            "Offen",
            "Pfingsten 2026",
        }
        only = {**params, "bookable_only": "true"}
        bookable = await async_client.get("/api/v1/tasks/feed", params=only)
        assert [i["name"] for i in bookable.json()["items"]] == ["Offen"]
        assert bookable.json()["total"] == 1

        await _member_row(db_session, team, test_user)
        joined = await async_client.get("/api/v1/tasks/feed", params=only)
        assert joined.json()["total"] == 2


@pytest.mark.asyncio
class TestRaces:
    async def test_join_race_is_409(
        self,
        async_client: AsyncClient,
        team: EventTeam,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """The row appeared between the check and the insert."""

        async def racing_request(*_args: Any, **_kwargs: Any) -> EventTeamMember:
            raise IntegrityError("insert", {}, Exception("duplicate"))

        monkeypatch.setattr(crud_team, "request", racing_request)
        r = await async_client.post(f"{_team_url(team)}/join", json={})
        assert r.status_code == 409
        assert r.json()["code"] == "team.request_pending"
