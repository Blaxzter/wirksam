"""Inviting people in charge by e-mail, and what accepting does.

``POST /tasks/{id}/managers/invite`` takes an address. A member's is put in
charge at once; anyone else, with an account or without, is invited into the
event with the task linked (``event_invitation_tasks``) and is put in charge
when they accept. The dispatchers are replaced by recorders, so each test
asserts what was *queued*: a "you're in charge" notice or an invitation.

The cast, all in ``test_event`` unless noted:

- ``admin``: ``test_event_admin_user``, an event admin (also admin of
  ``test_draft_event``, so they may move tasks there);
- ``superadmin``: ``test_admin_user``, the platform superadmin and owner;
- ``member``: ``test_user``, a plain member;
- ``manager``: a member in charge of ``task``;
- ``outsider``: ``test_outsider_user``, an account in no event;
- ``task`` (``test_task``) and ``other_task``, both published.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.api.routes.tasks import managers as managers_routes
from app.api.routes.tasks import shifts as shifts_routes
from app.core.config import settings
from app.crud.event_invitation import event_invitation as crud_invitation
from app.logic import clock, invitations
from app.logic.notifications import triggers
from app.models.event import Event
from app.models.event_invitation import EventInvitation
from app.models.event_invitation_task import EventInvitationTask
from app.models.event_membership import EventMembership
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from tests.fixtures.client import act_as

API = "/api/v1"
STRANGER = "new.person@example.org"

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
    other_event: Event
    task: Task
    other_task: Task
    admin: User
    superadmin: User
    member: User
    manager: User
    outsider: User


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> Calls:
    """Record the notices and invitations the routes queue instead of sending.

    The task routes import the dispatchers by name; the event routes import
    ``dispatch_event_invitation`` lazily from the trigger module, so the
    recorders go onto all three.
    """
    calls: Calls = {"added": [], "invitation": []}

    async def _added(
        *, task_id: uuid.UUID, user_ids: list[uuid.UUID], actor_id: uuid.UUID
    ) -> None:
        calls["added"].append(
            {"task_id": task_id, "user_ids": user_ids, "actor_id": actor_id}
        )

    async def _invitation(*, invitation_id: uuid.UUID) -> None:
        calls["invitation"].append({"invitation_id": invitation_id})

    for module in (managers_routes, shifts_routes, triggers):
        monkeypatch.setattr(module, "dispatch_task_manager_added", _added)
        monkeypatch.setattr(module, "dispatch_event_invitation", _invitation)
    return calls


async def _user(db: AsyncSession, key: str) -> User:
    user = User(
        subject=f"local|{key}-invite",
        email=f"{key}.invite@example.com",
        name=key.capitalize(),
        roles=[],
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def cast(
    db_session: AsyncSession,
    test_event: Event,
    test_draft_event: Event,
    test_task: Task,
    test_event_admin_user: User,
    test_admin_user: User,
    test_user: User,
    test_outsider_user: User,
) -> Cast:
    manager = await _user(db_session, "manager")
    db_session.add(EventMembership(user_id=manager.id, event_id=test_event.id))
    db_session.add(TaskManager(task_id=test_task.id, user_id=manager.id))
    other_task = Task(
        name="Grill",
        start_date=dt.date(2026, 6, 12),
        end_date=dt.date(2026, 6, 12),
        status="published",
        created_by_id=test_user.id,
        event_id=test_event.id,
    )
    db_session.add(other_task)
    await db_session.flush()
    return Cast(
        event=test_event,
        other_event=test_draft_event,
        task=test_task,
        other_task=other_task,
        admin=test_event_admin_user,
        superadmin=test_admin_user,
        member=test_user,
        manager=manager,
        outsider=test_outsider_user,
    )


async def _invite(client: AsyncClient, task: Task, email: str) -> Response:
    return await client.post(
        f"{API}/tasks/{task.id}/managers/invite", json={"email": email}
    )


async def _invitations(db: AsyncSession, email: str) -> list[EventInvitation]:
    rows = await db.execute(
        select(EventInvitation)
        .where(col(EventInvitation.email) == email.lower())
        .order_by(col(EventInvitation.created_at))
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars())


async def _linked(db: AsyncSession, invitation_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await db.execute(
        select(col(EventInvitationTask.task_id)).where(
            col(EventInvitationTask.invitation_id) == invitation_id
        )
    )
    return set(rows.scalars())


async def _managers(db: AsyncSession, task: Task) -> set[uuid.UUID]:
    rows = await db.execute(
        select(col(TaskManager.user_id)).where(col(TaskManager.task_id) == task.id)
    )
    return set(rows.scalars())


async def _pending(
    db: AsyncSession,
    event: Event,
    inviter: User,
    email: str,
    tasks: list[Task],
    *,
    for_tasks_only: bool = True,
    expires_in_days: int | None = 14,
) -> EventInvitation:
    """An open invitation with task links, written directly."""
    invitation = await crud_invitation.create(
        db,
        event_id=event.id,
        email=email,
        role="member",
        invited_by_id=inviter.id,
        expires_in_days=expires_in_days,
        for_tasks_only=for_tasks_only,
    )
    for task in tasks:
        db.add(
            EventInvitationTask(
                invitation_id=invitation.id,
                task_id=task.id,
                added_by_id=inviter.id,
                added_by_name=inviter.name,
            )
        )
    await db.flush()
    return invitation


async def _expire(db: AsyncSession, invitation: EventInvitation) -> None:
    invitation.expires_at = clock.utc_now() - dt.timedelta(days=1)
    db.add(invitation)
    await db.flush()


@pytest.fixture
def limits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """The daily limits are off under TESTING; these tests switch them on."""
    monkeypatch.setattr(settings, "TESTING", False)


# ── Inviting ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestInvite:
    async def test_a_members_address_in_any_case_puts_them_in_charge(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
    ) -> None:
        with act_as(app, cast.admin):
            r = await _invite(async_client, cast.task, "TEST@Example.com")
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "added"
        assert body["manager"]["user_id"] == str(cast.member.id)
        assert body["emailed"] is False
        assert cast.member.id in await _managers(db_session, cast.task)
        assert queued["added"] == [
            {
                "task_id": cast.task.id,
                "user_ids": [cast.member.id],
                "actor_id": cast.admin.id,
            }
        ]
        assert queued["invitation"] == []
        assert await _invitations(db_session, "test@example.com") == []

    async def test_the_callers_own_address_adds_them_quietly(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
    ) -> None:
        with act_as(app, cast.admin):
            r = await _invite(async_client, cast.task, cast.admin.email or "")
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "added"
        assert cast.admin.id in await _managers(db_session, cast.task)
        assert queued == {"added": [], "invitation": []}

    async def test_an_account_and_a_stranger_get_the_same_answer(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
    ) -> None:
        """The dialog must not tell an organiser who has an account."""
        with act_as(app, cast.admin):
            account = await _invite(async_client, cast.task, cast.outsider.email or "")
            stranger = await _invite(async_client, cast.task, STRANGER)
        assert account.status_code == stranger.status_code == 201

        def _shape(body: dict[str, Any]) -> dict[str, Any]:
            invitation = dict(body["invitation"])
            for volatile in ("id", "email", "created_at", "expires_at", "last_sent_at"):
                assert invitation.pop(volatile) is not None
            return {**body, "invitation": invitation, "email": None}

        assert _shape(account.json()) == _shape(stranger.json())
        assert stranger.json()["status"] == "invited"
        assert stranger.json()["emailed"] is True
        assert stranger.json()["registration_may_fail"] is False

        for email, response in (
            (cast.outsider.email or "", account),
            (STRANGER, stranger),
        ):
            [invitation] = await _invitations(db_session, email)
            assert str(invitation.id) == response.json()["invitation"]["id"]
            assert invitation.for_tasks_only is True
            assert invitation.role == "member"
            assert invitation.last_sent_at is not None
            assert invitation.invited_by_id == cast.admin.id
            assert await _linked(db_session, invitation.id) == {cast.task.id}
        assert len(queued["invitation"]) == 2
        assert queued["added"] == []
        assert cast.outsider.id not in await _managers(db_session, cast.task)

    async def test_someone_already_in_charge_is_a_conflict(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        with act_as(app, cast.admin):
            r = await _invite(async_client, cast.task, cast.manager.email or "")
        assert r.status_code == 409
        assert r.json()["code"] == "task.manager_already"
        assert queued["added"] == []

    async def test_the_same_address_for_the_same_task_is_a_conflict(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, queued: Calls
    ) -> None:
        with act_as(app, cast.admin):
            assert (await _invite(async_client, cast.task, STRANGER)).status_code == 201
            r = await _invite(async_client, cast.task, STRANGER.upper())
        assert r.status_code == 409
        assert r.json()["code"] == "task.manager_already_invited"
        assert len(queued["invitation"]) == 1

    async def test_a_second_task_within_ten_minutes_joins_the_invitation_quietly(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
    ) -> None:
        with act_as(app, cast.admin):
            first = await _invite(async_client, cast.task, STRANGER)
            second = await _invite(async_client, cast.other_task, STRANGER)
        assert second.status_code == 201, second.text
        assert second.json()["emailed"] is False
        assert second.json()["invitation"]["id"] == first.json()["invitation"]["id"]
        [invitation] = await _invitations(db_session, STRANGER)
        assert await _linked(db_session, invitation.id) == {
            cast.task.id,
            cast.other_task.id,
        }
        assert len(queued["invitation"]) == 1

    async def test_after_ten_minutes_it_is_mailed_again_and_lasts_longer(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
    ) -> None:
        invitation = await _pending(
            db_session, cast.event, cast.admin, STRANGER, [cast.task]
        )
        now = clock.utc_now()
        invitation.last_sent_at = now - dt.timedelta(minutes=11)
        invitation.expires_at = now + dt.timedelta(days=1)
        db_session.add(invitation)
        await db_session.flush()

        with act_as(app, cast.admin):
            r = await _invite(async_client, cast.other_task, STRANGER)
        assert r.status_code == 201, r.text
        assert r.json()["emailed"] is True
        await db_session.refresh(invitation)
        assert invitation.last_sent_at is not None
        assert invitation.last_sent_at > now - dt.timedelta(minutes=1)
        assert invitation.expires_at is not None
        assert invitation.expires_at > now + dt.timedelta(days=13)
        assert queued["invitation"] == [{"invitation_id": invitation.id}]

    async def test_an_open_plain_invitation_takes_the_task_and_stays_plain(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        plain = await _pending(
            db_session, cast.event, cast.superadmin, STRANGER, [], for_tasks_only=False
        )
        plain.role = "admin"
        db_session.add(plain)
        await db_session.flush()

        with act_as(app, cast.admin):
            r = await _invite(async_client, cast.task, STRANGER)
        assert r.status_code == 201, r.text
        [invitation] = await _invitations(db_session, STRANGER)
        assert invitation.id == plain.id
        assert invitation.for_tasks_only is False
        assert invitation.role == "admin"
        assert await _linked(db_session, plain.id) == {cast.task.id}
        assert r.json()["invitation"]["invited_by_name"] == cast.superadmin.name

    async def test_an_expired_invitation_is_replaced_and_its_tasks_move_over(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
    ) -> None:
        old = await _pending(
            db_session, cast.event, cast.admin, STRANGER, [cast.other_task]
        )
        await _expire(db_session, old)

        with act_as(app, cast.admin):
            r = await _invite(async_client, cast.task, STRANGER)
        assert r.status_code == 201, r.text
        assert r.json()["emailed"] is True
        old_row, new_row = await _invitations(db_session, STRANGER)
        assert old_row.id == old.id
        assert old_row.revoked_at is not None
        assert str(new_row.id) == r.json()["invitation"]["id"]
        assert new_row.for_tasks_only is True
        assert await _linked(db_session, old.id) == set()
        assert await _linked(db_session, new_row.id) == {
            cast.task.id,
            cast.other_task.id,
        }
        assert queued["invitation"] == [{"invitation_id": new_row.id}]

    async def test_inviting_again_from_an_expired_row_joins_a_valid_invitation(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        """The expired row's task moves onto the open invitation, once."""
        expired = await _pending(
            db_session, cast.event, cast.admin, STRANGER, [cast.task]
        )
        await _expire(db_session, expired)
        plain = await _pending(
            db_session, cast.event, cast.superadmin, STRANGER, [], for_tasks_only=False
        )

        with act_as(app, cast.admin):
            r = await _invite(async_client, cast.task, STRANGER)
        assert r.status_code == 201, r.text
        assert r.json()["invitation"]["id"] == str(plain.id)
        await db_session.refresh(expired)
        assert expired.revoked_at is not None
        assert await _linked(db_session, plain.id) == {cast.task.id}

    async def test_a_member_of_another_event_is_invited(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
    ) -> None:
        """Membership elsewhere does not count: the address is invited here."""
        elsewhere = await _user(db_session, "elsewhere")
        db_session.add(
            EventMembership(user_id=elsewhere.id, event_id=cast.other_event.id)
        )
        await db_session.flush()

        with act_as(app, cast.admin):
            r = await _invite(async_client, cast.task, elsewhere.email or "")
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "invited"

    @pytest.mark.parametrize("role", ["member", "manager", "outsider"])
    async def test_only_event_admins_invite(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
        role: str,
    ) -> None:
        with act_as(app, getattr(cast, role)):
            r = await _invite(async_client, cast.task, STRANGER)
        assert r.status_code == 403
        assert r.json()["code"] == "event.forbidden"
        assert await _invitations(db_session, STRANGER) == []

    async def test_an_unknown_task_is_404(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                f"{API}/tasks/{uuid.uuid4()}/managers/invite", json={"email": STRANGER}
            )
        assert r.status_code == 404
        assert r.json()["code"] == "task.not_found"

    async def test_a_demo_event_cannot_invite_but_can_add_a_member(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
    ) -> None:
        cast.event.is_sandbox = True
        db_session.add(cast.event)
        await db_session.flush()

        with act_as(app, cast.admin):
            refused = await _invite(async_client, cast.task, STRANGER)
            added = await _invite(async_client, cast.task, cast.member.email or "")
        assert refused.status_code == 403
        assert refused.json()["code"] == "sandbox.invitations_disabled"
        assert await _invitations(db_session, STRANGER) == []
        assert added.status_code == 201
        assert added.json()["status"] == "added"

    async def test_adding_a_member_drops_the_task_from_their_open_invitation(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        """Someone who joined another way is added; their invitation lets go."""
        joined = await _user(db_session, "joined")
        invitation = await _pending(
            db_session, cast.event, cast.admin, joined.email or "", [cast.task]
        )
        db_session.add(EventMembership(user_id=joined.id, event_id=cast.event.id))
        await db_session.flush()

        with act_as(app, cast.admin):
            r = await _invite(async_client, cast.task, joined.email or "")
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "added"
        await db_session.refresh(invitation)
        assert await _linked(db_session, invitation.id) == set()
        assert invitation.revoked_at is not None


# ── Daily limits ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestLimits:
    async def test_a_fourth_invitation_to_one_address_in_a_day_is_refused(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        test_private_event: Event,
        limits_on: None,
    ) -> None:
        """Counted across events, so several organisers cannot fill one inbox."""
        for event in (cast.other_event, test_private_event, cast.other_event):
            await crud_invitation.create(
                db_session,
                event_id=event.id,
                email=STRANGER,
                role="member",
                invited_by_id=cast.superadmin.id,
                expires_in_days=14,
            )
        # Revoke them all: the count is of mail sent, not of what is open.
        for invitation in await _invitations(db_session, STRANGER):
            await crud_invitation.revoke(db_session, invitation=invitation)

        with act_as(app, cast.admin):
            r = await _invite(async_client, cast.task, STRANGER)
        assert r.status_code == 429
        assert r.json()["code"] == "invitation.address_limited"

    async def test_an_organiser_has_a_daily_cap(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        limits_on: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(invitations, "INVITATIONS_PER_INVITER_PER_DAY", 2)
        with act_as(app, cast.admin):
            for n in range(2):
                r = await _invite(async_client, cast.task, f"guest{n}@example.org")
                assert r.status_code == 201, r.text
            r = await _invite(async_client, cast.task, STRANGER)
            assert r.status_code == 429
            assert r.json()["code"] == "invitation.rate_limited"
            # The same cap guards the event settings' invitation.
            r = await async_client.post(
                f"{API}/events/{cast.event.id}/invitations", json={"email": STRANGER}
            )
            assert r.status_code == 429
            assert r.json()["code"] == "invitation.rate_limited"

    async def test_adding_a_task_to_an_open_invitation_is_not_counted(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        cast: Cast,
        limits_on: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(invitations, "INVITATIONS_PER_INVITER_PER_DAY", 1)
        with act_as(app, cast.admin):
            assert (await _invite(async_client, cast.task, STRANGER)).status_code == 201
            r = await _invite(async_client, cast.other_task, STRANGER)
        assert r.status_code == 201, r.text

    async def test_the_superadmin_is_exempt(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        limits_on: None,
    ) -> None:
        for _ in range(3):
            invitation = await crud_invitation.create(
                db_session,
                event_id=cast.other_event.id,
                email=STRANGER,
                role="member",
                invited_by_id=cast.admin.id,
                expires_in_days=14,
            )
            await crud_invitation.revoke(db_session, invitation=invitation)

        with act_as(app, cast.superadmin):
            r = await _invite(async_client, cast.task, STRANGER)
        assert r.status_code == 201, r.text

    async def test_bulk_reports_refused_addresses_instead_of_failing(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        limits_on: None,
        queued: Calls,
    ) -> None:
        for _ in range(3):
            invitation = await crud_invitation.create(
                db_session,
                event_id=cast.other_event.id,
                email=STRANGER,
                role="member",
                invited_by_id=cast.superadmin.id,
                expires_in_days=14,
            )
            await crud_invitation.revoke(db_session, invitation=invitation)

        with act_as(app, cast.admin):
            r = await async_client.post(
                f"{API}/events/{cast.event.id}/invitations/bulk",
                json={"emails": [STRANGER, "fine@example.org"]},
            )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["skipped_rate_limited"] == [STRANGER]
        assert [i["email"] for i in body["created"]] == ["fine@example.org"]
        assert body["created"][0]["last_sent_at"] is not None
        assert len(queued["invitation"]) == 1


# ── Registration warning ──────────────────────────────────────────


@pytest.mark.asyncio
class TestRegistrationMayFail:
    @pytest.mark.parametrize(
        ("bypass", "expected"),
        [(False, True), (True, False)],
    )
    async def test_follows_the_domain_rule_not_the_account(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        cast: Cast,
        monkeypatch: pytest.MonkeyPatch,
        queued: Calls,
        bypass: bool,
        expected: bool,
    ) -> None:
        monkeypatch.setattr(settings, "REGISTRATION_ALLOWED_DOMAINS", ["example.org"])
        monkeypatch.setattr(settings, "REGISTRATION_INVITE_BYPASS", bypass)
        with act_as(app, cast.admin):
            # outsider@example.com has an account, x@other.com has none.
            for email in (cast.outsider.email or "", "x@other.com"):
                r = await _invite(async_client, cast.task, email)
                assert r.status_code == 201, r.text
                assert r.json()["registration_may_fail"] is expected
            allowed = await _invite(async_client, cast.task, STRANGER)
        assert allowed.json()["registration_may_fail"] is False


# ── The dialog's list, re-send and withdraw ───────────────────────


@pytest.mark.asyncio
class TestList:
    async def test_admins_see_open_invitations_with_their_state(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        joined = await _user(db_session, "joined")
        db_session.add(EventMembership(user_id=joined.id, event_id=cast.event.id))
        fresh = await _pending(
            db_session, cast.event, cast.admin, STRANGER, [cast.task]
        )
        stale = await _pending(
            db_session, cast.event, cast.admin, "late@example.org", [cast.task]
        )
        await _expire(db_session, stale)
        member_now = await _pending(
            db_session, cast.event, cast.admin, joined.email or "", [cast.task]
        )
        elsewhere = await _pending(
            db_session, cast.event, cast.admin, "grill@example.org", [cast.other_task]
        )
        gone = await _pending(
            db_session, cast.event, cast.admin, "gone@example.org", [cast.task]
        )
        await crud_invitation.revoke(db_session, invitation=gone)

        with act_as(app, cast.admin):
            r = await async_client.get(
                f"{API}/tasks/{cast.task.id}/managers/invitations"
            )
        assert r.status_code == 200, r.text
        rows = {row["id"]: row for row in r.json()}
        assert set(rows) == {str(fresh.id), str(stale.id), str(member_now.id)}
        assert str(elsewhere.id) not in rows
        assert rows[str(fresh.id)]["expired"] is False
        assert rows[str(fresh.id)]["is_member_now"] is False
        assert rows[str(fresh.id)]["invited_by_name"] == cast.admin.name
        assert rows[str(stale.id)]["expired"] is True
        assert rows[str(member_now.id)]["is_member_now"] is True

    @pytest.mark.parametrize("role", ["manager", "member"])
    async def test_people_in_charge_and_members_may_not_look(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast, role: str
    ) -> None:
        with act_as(app, getattr(cast, role)):
            r = await async_client.get(
                f"{API}/tasks/{cast.task.id}/managers/invitations"
            )
        assert r.status_code == 403
        assert r.json()["code"] == "event.forbidden"


@pytest.mark.asyncio
class TestPickingAnInvitedMember:
    """Someone invited to run a task joins the event another way, and an
    organiser then picks them from the member list rather than "Add now"."""

    async def test_their_invitation_loses_the_task(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
    ) -> None:
        joined = await _user(db_session, "joined")
        db_session.add(EventMembership(user_id=joined.id, event_id=cast.event.id))
        task_only = await _pending(
            db_session, cast.event, cast.admin, joined.email or "", [cast.task]
        )
        plain = await _pending(
            db_session,
            cast.event,
            cast.superadmin,
            joined.email or "",
            [cast.task, cast.other_task],
            for_tasks_only=False,
        )

        with act_as(app, cast.admin):
            r = await async_client.post(
                f"{API}/tasks/{cast.task.id}/managers",
                json={"user_id": str(joined.id)},
            )
            assert r.status_code == 201, r.text
            listed = await async_client.get(
                f"{API}/tasks/{cast.task.id}/managers/invitations"
            )
        assert joined.id in await _managers(db_session, cast.task)
        # No row left offering an "Add now" that could only fail.
        assert listed.json() == []
        for invitation in (task_only, plain):
            await db_session.refresh(invitation)
        # Asked only for this task: withdrawn. The other keeps its other task.
        assert task_only.revoked_at is not None
        assert await _linked(db_session, task_only.id) == set()
        assert plain.revoked_at is None
        assert await _linked(db_session, plain.id) == {cast.other_task.id}

    async def test_a_refused_pick_leaves_the_invitation_alone(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        """Already in charge: the 409 rolls the whole request back."""
        invitation = await _pending(
            db_session, cast.event, cast.admin, cast.manager.email or "", [cast.task]
        )
        with act_as(app, cast.admin):
            r = await async_client.post(
                f"{API}/tasks/{cast.task.id}/managers",
                json={"user_id": str(cast.manager.id)},
            )
        assert r.status_code == 409
        assert r.json()["code"] == "task.manager_already"
        await db_session.refresh(invitation)
        assert invitation.revoked_at is None
        assert await _linked(db_session, invitation.id) == {cast.task.id}


@pytest.mark.asyncio
class TestEventSettingsExpiry:
    """The event settings' invitations expire when asked; only sending a task
    invitation again moves an expiry out."""

    async def test_a_short_expiry_is_kept(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
    ) -> None:
        with act_as(app, cast.admin):
            single = await async_client.post(
                f"{API}/events/{cast.event.id}/invitations",
                json={"email": STRANGER, "expires_in_days": 3},
            )
            bulk = await async_client.post(
                f"{API}/events/{cast.event.id}/invitations/bulk",
                json={"emails": ["two@example.org"], "expires_in_days": 3},
            )
        assert single.status_code == 201, single.text
        assert bulk.status_code == 201, bulk.text
        expected = clock.utc_now() + dt.timedelta(days=3)
        for read in (single.json(), bulk.json()["created"][0]):
            # Naive UTC, whether or not the serialiser marks it as UTC.
            expires_at = dt.datetime.fromisoformat(read["expires_at"]).replace(
                tzinfo=None
            )
            assert abs(expires_at - expected) < dt.timedelta(minutes=5)
            assert read["last_sent_at"] is not None
        assert len(queued["invitation"]) == 2


@pytest.mark.asyncio
class TestWithdraw:
    async def test_the_last_task_takes_a_task_only_invitation_with_it(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        invitation = await _pending(
            db_session, cast.event, cast.admin, STRANGER, [cast.task, cast.other_task]
        )
        with act_as(app, cast.admin):
            first = await async_client.delete(
                f"{API}/tasks/{cast.task.id}/managers/invitations/{invitation.id}"
            )
            assert first.status_code == 204, first.text
            await db_session.refresh(invitation)
            assert await _linked(db_session, invitation.id) == {cast.other_task.id}
            assert invitation.revoked_at is None

            last = await async_client.delete(
                f"{API}/tasks/{cast.other_task.id}/managers/invitations/{invitation.id}"
            )
        assert last.status_code == 204, last.text
        await db_session.refresh(invitation)
        assert invitation.revoked_at is not None

    async def test_a_plain_invitation_stays_valid(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        invitation = await _pending(
            db_session,
            cast.event,
            cast.admin,
            STRANGER,
            [cast.task],
            for_tasks_only=False,
        )
        with act_as(app, cast.admin):
            r = await async_client.delete(
                f"{API}/tasks/{cast.task.id}/managers/invitations/{invitation.id}"
            )
        assert r.status_code == 204, r.text
        await db_session.refresh(invitation)
        assert invitation.revoked_at is None
        assert await _linked(db_session, invitation.id) == set()

    async def test_an_unknown_or_unlinked_invitation_is_404(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        other = await _pending(
            db_session, cast.event, cast.admin, STRANGER, [cast.other_task]
        )
        with act_as(app, cast.admin):
            for invitation_id in (uuid.uuid4(), other.id):
                r = await async_client.delete(
                    f"{API}/tasks/{cast.task.id}/managers/invitations/{invitation_id}"
                )
                assert r.status_code == 404
                assert r.json()["code"] == "task.manager_invitation_not_found"

    async def test_only_event_admins_withdraw(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        invitation = await _pending(
            db_session, cast.event, cast.admin, STRANGER, [cast.task]
        )
        with act_as(app, cast.manager):
            r = await async_client.delete(
                f"{API}/tasks/{cast.task.id}/managers/invitations/{invitation.id}"
            )
        assert r.status_code == 403


@pytest.mark.asyncio
class TestResend:
    async def test_within_ten_minutes_it_is_too_soon(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        cast: Cast,
        queued: Calls,
    ) -> None:
        with act_as(app, cast.admin):
            invited = await _invite(async_client, cast.task, STRANGER)
            invitation_id = invited.json()["invitation"]["id"]
            r = await async_client.post(
                f"{API}/tasks/{cast.task.id}/managers/invitations/{invitation_id}/resend"
            )
        assert r.status_code == 429
        assert r.json()["code"] == "invitation.resend_too_soon"
        assert len(queued["invitation"]) == 1

    async def test_an_expired_invitation_asks_for_a_new_one(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        invitation = await _pending(
            db_session, cast.event, cast.admin, STRANGER, [cast.task]
        )
        await _expire(db_session, invitation)
        with act_as(app, cast.admin):
            r = await async_client.post(
                f"{API}/tasks/{cast.task.id}/managers/invitations/{invitation.id}/resend"
            )
        assert r.status_code == 409
        assert r.json()["code"] == "invitation.expired"

    async def test_later_it_goes_out_again(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
    ) -> None:
        invitation = await _pending(
            db_session, cast.event, cast.admin, STRANGER, [cast.task]
        )
        invitation.last_sent_at = clock.utc_now() - dt.timedelta(minutes=30)
        db_session.add(invitation)
        await db_session.flush()
        with act_as(app, cast.admin):
            r = await async_client.post(
                f"{API}/tasks/{cast.task.id}/managers/invitations/{invitation.id}/resend"
            )
        assert r.status_code == 200, r.text
        assert r.json()["id"] == str(invitation.id)
        assert queued["invitation"] == [{"invitation_id": invitation.id}]
        await db_session.refresh(invitation)
        assert invitation.last_sent_at is not None
        assert invitation.last_sent_at > clock.utc_now() - dt.timedelta(minutes=1)

    async def test_an_unknown_invitation_is_404(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                f"{API}/tasks/{cast.task.id}/managers/invitations/{uuid.uuid4()}/resend"
            )
        assert r.status_code == 404
        assert r.json()["code"] == "task.manager_invitation_not_found"


# ── Accepting ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAccept:
    async def test_accepting_applies_every_open_invitation_to_the_address(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Two organisers inviting at once can leave two; one token takes both."""
        accepted: list[dict[str, Any]] = []

        async def _accepted(**kwargs: Any) -> None:
            accepted.append(kwargs)

        monkeypatch.setattr(triggers, "dispatch_event_invitation_accepted", _accepted)
        invitee = await _user(db_session, "invitee")
        email = invitee.email or ""
        first = await _pending(db_session, cast.event, cast.admin, email, [cast.task])
        second = await _pending(
            db_session,
            cast.event,
            cast.superadmin,
            email,
            [cast.other_task],
            for_tasks_only=False,
        )

        with act_as(app, invitee):
            r = await async_client.post(f"{API}/invitations/{first.token}/accept")
        assert r.status_code == 200, r.text
        assert r.json()["my_role"] == "member"
        assert invitee.id in await _managers(db_session, cast.task)
        assert invitee.id in await _managers(db_session, cast.other_task)
        for invitation in (first, second):
            await db_session.refresh(invitation)
            assert invitation.accepted_at is not None
            assert invitation.accepted_by_id == invitee.id
        [call] = accepted
        assert call["user_id"] == invitee.id
        assert set(call["task_ids"]) == {cast.task.id, cast.other_task.id}
        # Put in charge by the organiser who asked, not by the invitee.
        rows = await db_session.execute(
            select(TaskManager).where(col(TaskManager.user_id) == invitee.id)
        )
        asked_by = {m.task_id: (m.added_by_id, m.added_by_name) for m in rows.scalars()}
        assert asked_by == {
            cast.task.id: (cast.admin.id, cast.admin.name),
            cast.other_task.id: (cast.superadmin.id, cast.superadmin.name),
        }

    async def test_an_organiser_invitation_is_not_used_up_as_a_plain_one(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        invitee = await _user(db_session, "invitee")
        email = invitee.email or ""
        task_only = await _pending(
            db_session, cast.event, cast.admin, email, [cast.task]
        )
        organiser = await _pending(
            db_session, cast.event, cast.superadmin, email, [], for_tasks_only=False
        )
        organiser.role = "admin"
        db_session.add(organiser)
        await db_session.flush()

        with act_as(app, invitee):
            r = await async_client.post(f"{API}/invitations/{task_only.token}/accept")
        assert r.status_code == 200, r.text
        assert r.json()["my_role"] == "admin"

    async def test_a_member_accepting_gets_the_tasks_and_closes_it(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        """A targeted invitation no longer stays open forever for a member."""
        invitation = await _pending(
            db_session, cast.event, cast.admin, cast.member.email or "", [cast.task]
        )
        with act_as(app, cast.member):
            r = await async_client.post(f"{API}/invitations/{invitation.token}/accept")
        assert r.status_code == 200, r.text
        assert cast.member.id in await _managers(db_session, cast.task)
        await db_session.refresh(invitation)
        assert invitation.accepted_at is not None

    async def test_being_in_charge_already_is_no_error(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        invitation = await _pending(
            db_session,
            cast.event,
            cast.admin,
            cast.manager.email or "",
            [cast.task, cast.other_task],
        )
        with act_as(app, cast.manager):
            r = await async_client.post(f"{API}/invitations/{invitation.token}/accept")
        assert r.status_code == 200, r.text
        rows = await db_session.execute(
            select(TaskManager).where(col(TaskManager.user_id) == cast.manager.id)
        )
        assert sorted(str(m.task_id) for m in rows.scalars()) == sorted(
            [str(cast.task.id), str(cast.other_task.id)]
        )

    async def test_a_deleted_task_withdraws_a_task_only_invitation(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        invitee = await _user(db_session, "invitee")
        task_only = await _pending(
            db_session, cast.event, cast.admin, invitee.email or "", [cast.other_task]
        )
        plain = await _pending(
            db_session,
            cast.event,
            cast.admin,
            "plain@example.org",
            [cast.other_task],
            for_tasks_only=False,
        )
        with act_as(app, cast.admin):
            r = await async_client.delete(f"{API}/tasks/{cast.other_task.id}")
            assert r.status_code == 204, r.text
        for invitation in (task_only, plain):
            await db_session.refresh(invitation)
        assert task_only.revoked_at is not None
        assert plain.revoked_at is None

        with act_as(app, invitee):
            r = await async_client.post(f"{API}/invitations/{task_only.token}/accept")
        assert r.status_code == 410
        assert r.json()["code"] == "invitation.revoked"

    async def test_a_task_moved_to_another_event_is_not_applied(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        invitee = await _user(db_session, "invitee")
        invitation = await _pending(
            db_session,
            cast.event,
            cast.admin,
            invitee.email or "",
            [cast.task, cast.other_task],
        )
        with act_as(app, cast.admin):
            r = await async_client.patch(
                f"{API}/tasks/{cast.other_task.id}",
                json={"event_id": str(cast.other_event.id)},
            )
            assert r.status_code == 200, r.text
        assert await _linked(db_session, invitation.id) == {cast.task.id}

        with act_as(app, invitee):
            r = await async_client.post(f"{API}/invitations/{invitation.token}/accept")
        assert r.status_code == 200, r.text
        assert invitee.id in await _managers(db_session, cast.task)
        assert invitee.id not in await _managers(db_session, cast.other_task)

    async def test_a_moved_tasks_only_invitation_is_withdrawn(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        invitation = await _pending(
            db_session, cast.event, cast.admin, STRANGER, [cast.other_task]
        )
        with act_as(app, cast.admin):
            r = await async_client.patch(
                f"{API}/tasks/{cast.other_task.id}",
                json={"event_id": str(cast.other_event.id)},
            )
        assert r.status_code == 200, r.text
        await db_session.refresh(invitation)
        assert invitation.revoked_at is not None


@pytest.mark.asyncio
class TestPreview:
    async def test_the_addressee_sees_the_tasks(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        invitee = await _user(db_session, "invitee")
        invitation = await _pending(
            db_session,
            cast.event,
            cast.admin,
            invitee.email or "",
            [cast.task, cast.other_task],
        )
        with act_as(app, invitee):
            r = await async_client.get(f"{API}/invitations/{invitation.token}")
        assert r.status_code == 200, r.text
        assert [t["name"] for t in r.json()["tasks"]] == sorted(
            [cast.task.name, cast.other_task.name]
        )
        [first] = [t for t in r.json()["tasks"] if t["task_id"] == str(cast.task.id)]
        assert first["start_date"] == cast.task.start_date.isoformat()

    async def test_someone_else_sees_no_tasks(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        invitation = await _pending(
            db_session, cast.event, cast.admin, STRANGER, [cast.task]
        )
        with act_as(app, cast.outsider):
            r = await async_client.get(f"{API}/invitations/{invitation.token}")
        assert r.status_code == 200, r.text
        assert r.json()["invalid_reason"] == "email_mismatch"
        assert r.json()["tasks"] == []

    async def test_the_event_settings_list_names_the_tasks(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        invitation = await _pending(
            db_session, cast.event, cast.admin, STRANGER, [cast.task]
        )
        with act_as(app, cast.admin):
            r = await async_client.get(f"{API}/events/{cast.event.id}/invitations")
        assert r.status_code == 200, r.text
        [row] = [i for i in r.json() if i["id"] == str(invitation.id)]
        assert row["for_tasks_only"] is True
        assert [t["task_id"] for t in row["tasks"]] == [str(cast.task.id)]


# ── Create with people in charge by address ───────────────────────


def _create_body(event: Event, **extra: Any) -> dict[str, Any]:
    return {
        "name": "Kuchenbuffet",
        "start_date": "2026-06-11",
        "end_date": "2026-06-11",
        "event_id": str(event.id),
        "schedule": SCHEDULE,
        **extra,
    }


@pytest.mark.asyncio
class TestCreateWithShifts:
    async def test_a_member_is_added_and_a_stranger_invited(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                f"{API}/tasks/with-shifts",
                json=_create_body(
                    cast.event,
                    manager_ids=[str(cast.manager.id)],
                    manager_emails=[
                        cast.member.email,
                        STRANGER,
                        STRANGER.upper(),
                        cast.manager.email,
                    ],
                ),
            )
        assert r.status_code == 201, r.text
        task_id = uuid.UUID(r.json()["task"]["id"])
        results = {i["email"]: i for i in r.json()["manager_invites"]}
        # The manager, already named by id, is left out silently.
        assert set(results) == {cast.member.email, STRANGER}
        assert results[cast.member.email]["status"] == "added"
        assert results[STRANGER]["status"] == "invited"
        rows = await db_session.execute(
            select(col(TaskManager.user_id)).where(col(TaskManager.task_id) == task_id)
        )
        assert set(rows.scalars()) == {cast.member.id, cast.manager.id}
        [invitation] = await _invitations(db_session, STRANGER)
        assert await _linked(db_session, invitation.id) == {task_id}
        # One notice for everyone put in charge, one invitation.
        [added] = queued["added"]
        assert set(added["user_ids"]) == {cast.member.id, cast.manager.id}
        assert queued["invitation"] == [{"invitation_id": invitation.id}]

    async def test_a_demo_event_skips_the_invitation_and_keeps_the_task(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        queued: Calls,
    ) -> None:
        cast.event.is_sandbox = True
        db_session.add(cast.event)
        await db_session.flush()
        with act_as(app, cast.admin):
            r = await async_client.post(
                f"{API}/tasks/with-shifts",
                json=_create_body(cast.event, manager_emails=[STRANGER]),
            )
        assert r.status_code == 201, r.text
        assert r.json()["manager_invites"] == [
            {
                "status": "skipped",
                "manager": None,
                "invitation": None,
                "emailed": False,
                "registration_may_fail": False,
                "skipped_reason": "sandbox",
                "email": STRANGER,
            }
        ]
        assert await db_session.get(Task, uuid.UUID(r.json()["task"]["id"]))
        assert await _invitations(db_session, STRANGER) == []
        assert queued["invitation"] == []

    async def test_a_daily_limit_skips_instead_of_failing(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        cast: Cast,
        limits_on: None,
    ) -> None:
        for _ in range(3):
            invitation = await crud_invitation.create(
                db_session,
                event_id=cast.other_event.id,
                email=STRANGER,
                role="member",
                invited_by_id=cast.superadmin.id,
                expires_in_days=14,
            )
            await crud_invitation.revoke(db_session, invitation=invitation)
        with act_as(app, cast.admin):
            r = await async_client.post(
                f"{API}/tasks/with-shifts",
                json=_create_body(cast.event, manager_emails=[STRANGER]),
            )
        assert r.status_code == 201, r.text
        [result] = r.json()["manager_invites"]
        assert (result["status"], result["skipped_reason"]) == (
            "skipped",
            "address_limited",
        )

    async def test_a_new_event_has_nobody_to_invite_into(
        self, app: FastAPI, async_client: AsyncClient, cast: Cast
    ) -> None:
        body = _create_body(cast.event, manager_emails=[STRANGER])
        del body["event_id"]
        body["new_event"] = {
            "name": "Neu",
            "start_date": "2026-06-11",
            "end_date": "2026-06-12",
        }
        # Only the superadmin may create a task outside an existing event.
        with act_as(app, cast.superadmin):
            r = await async_client.post(f"{API}/tasks/with-shifts", json=body)
        assert r.status_code == 422
        assert r.json()["code"] == "task.manager_not_event_member"
