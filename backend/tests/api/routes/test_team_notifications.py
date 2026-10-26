"""The team routes queue the right notification at the right moment (#179).

The dispatchers themselves are covered in ``tests/logic/test_notification_
triggers.py``. Here they are replaced by recorders, so each test asserts what
the background task was *asked* to do: who asked to join, who was decided on
and which way, and that nothing is queued when nobody needs telling.
"""

import uuid
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import teams as teams_routes
from app.models.event import Event
from app.models.event_team import EventTeam, EventTeamMember
from app.models.user import User

Calls = dict[str, list[dict[str, Any]]]


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> Calls:
    """Record the team dispatches instead of running them.

    ``teams.py`` imports the dispatchers by name, so the recorders go onto that
    module rather than onto the trigger module.
    """
    calls: Calls = {"requested": [], "decided": []}

    async def _requested(*, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
        calls["requested"].append({"team_id": team_id, "user_id": user_id})

    async def _decided(
        *, team_id: uuid.UUID, user_id: uuid.UUID, approved: bool
    ) -> None:
        calls["decided"].append(
            {"team_id": team_id, "user_id": user_id, "approved": approved}
        )

    monkeypatch.setattr(teams_routes, "dispatch_team_join_requested", _requested)
    monkeypatch.setattr(teams_routes, "dispatch_team_join_decided", _decided)
    return calls


@pytest_asyncio.fixture
async def team(db_session: AsyncSession, test_event: Event) -> EventTeam:
    row = EventTeam(event_id=test_event.id, name="Kasse", requires_approval=True)
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


async def _pending(db_session: AsyncSession, team: EventTeam, user: User) -> None:
    db_session.add(EventTeamMember(team_id=team.id, user_id=user.id, status="pending"))
    await db_session.flush()


def _url(team: EventTeam) -> str:
    return f"/api/v1/events/{team.event_id}/teams/{team.id}"


@pytest.mark.asyncio
class TestJoinNotifications:
    async def test_request_to_a_restricted_team_is_announced(
        self,
        async_client: AsyncClient,
        team: EventTeam,
        test_user: User,
        queued: Calls,
    ):
        r = await async_client.post(f"{_url(team)}/join", json={})

        assert r.status_code == 201, r.text
        assert queued["requested"] == [{"team_id": team.id, "user_id": test_user.id}]
        assert queued["decided"] == []

    async def test_joining_an_open_team_tells_nobody(
        self,
        async_client: AsyncClient,
        open_team: EventTeam,
        queued: Calls,
    ):
        """Nothing is waiting on anyone, so there is nothing to say."""
        r = await async_client.post(f"{_url(open_team)}/join", json={})

        assert r.status_code == 201
        assert r.json()["status"] == "approved"
        assert queued == {"requested": [], "decided": []}

    async def test_a_refused_request_tells_nobody(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        test_user: User,
        queued: Calls,
    ):
        """Asking twice is a 409, not a second ping to the leads."""
        await _pending(db_session, team, test_user)

        r = await async_client.post(f"{_url(team)}/join", json={})

        assert r.status_code == 409
        assert queued["requested"] == []


@pytest.mark.asyncio
class TestDecisionNotifications:
    @pytest.mark.parametrize("approve", [True, False])
    async def test_decision_is_sent_to_the_requester(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
        queued: Calls,
        approve: bool,
    ):
        await _pending(db_session, team, test_user)

        r = await async_client.post(
            f"{_url(team)}/members/{test_user.id}/decide", json={"approve": approve}
        )

        assert r.status_code == 200, r.text
        assert queued["decided"] == [
            {"team_id": team.id, "user_id": test_user.id, "approved": approve}
        ]

    async def test_refused_decision_tells_nobody(
        self,
        async_client: AsyncClient,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
        queued: Calls,
    ):
        r = await async_client.post(
            f"{_url(team)}/members/{test_user.id}/decide", json={"approve": True}
        )

        assert r.status_code == 404
        assert queued["decided"] == []

    async def test_adding_someone_who_had_asked_approves_their_request(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
        queued: Calls,
    ):
        await _pending(db_session, team, test_user)

        r = await async_client.post(
            f"{_url(team)}/members", json={"user_id": str(test_user.id)}
        )

        assert r.status_code == 201, r.text
        assert queued["decided"] == [
            {"team_id": team.id, "user_id": test_user.id, "approved": True}
        ]

    async def test_adding_someone_who_never_asked_is_not_a_decision(
        self,
        async_client: AsyncClient,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
        queued: Calls,
    ):
        r = await async_client.post(
            f"{_url(team)}/members", json={"user_id": str(test_user.id)}
        )

        assert r.status_code == 201, r.text
        assert queued["decided"] == []

    async def test_opening_a_team_tells_everyone_who_was_waiting(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        test_user: User,
        test_outsider_user: User,
        as_event_admin: None,
        queued: Calls,
    ):
        """Turning approval off lets the queue in; each of them hears so."""
        await _pending(db_session, team, test_user)
        await _pending(db_session, team, test_outsider_user)

        r = await async_client.patch(_url(team), json={"requires_approval": False})

        assert r.status_code == 200, r.text
        assert sorted(queued["decided"], key=lambda c: str(c["user_id"])) == sorted(
            [
                {"team_id": team.id, "user_id": test_user.id, "approved": True},
                {
                    "team_id": team.id,
                    "user_id": test_outsider_user.id,
                    "approved": True,
                },
            ],
            key=lambda c: str(c["user_id"]),
        )

    async def test_other_edits_tell_nobody(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        team: EventTeam,
        test_user: User,
        as_event_admin: None,
        queued: Calls,
    ):
        await _pending(db_session, team, test_user)

        r = await async_client.patch(_url(team), json={"description": "Cash desk"})

        assert r.status_code == 200, r.text
        assert queued["decided"] == []
