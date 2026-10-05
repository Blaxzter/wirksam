"""Tests for the three registration modes a self-hosted deployment can choose.

``REGISTRATION_MODE``, ``REGISTRATION_ALLOWED_DOMAINS`` and
``REGISTRATION_INVITE_BYPASS`` decide who may sign up and whether the new
account works at once. Like ``test_auth.py`` these drive the real endpoints
through ``unauthenticated_client``, because the part worth testing is the whole
chain: the refusal a form can render, the account that is or is not written,
and the gate in ``CurrentUser`` that keeps a pending account out of the app
while ``GET /users/me`` still tells it why.
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import auth as auth_routes
from app.core.config import settings
from app.crud.event_invitation import event_invitation as crud_invitation
from app.crud.notification_type import notification_type as crud_notification_type
from app.crud.user import user as crud_user
from app.logic.notifications import triggers
from app.logic.notifications.registry import ALL_NOTIFICATION_TYPES
from app.models.event import Event
from app.models.event_invitation import EventInvitation
from app.models.user import User

Calls = list[tuple[str, Any]]
Configure = Callable[..., None]

AUTH = f"{settings.API_V1_STR}/auth"
USERS = f"{settings.API_V1_STR}/users"
PASSWORD = "a-perfectly-fine-password"


@pytest.fixture(autouse=True)
def quiet_side_effects(monkeypatch: pytest.MonkeyPatch) -> Calls:
    """Record the mails and notifications a signup schedules instead of sending them."""
    calls: list[tuple[str, Any]] = []

    async def _verify_mail(**kwargs: Any) -> bool:
        calls.append(("verify_email", kwargs))
        return True

    def _recorder(name: str):
        async def _record(**kwargs: Any) -> None:
            calls.append((name, kwargs))

        return _record

    monkeypatch.setattr(auth_routes, "send_verify_email", _verify_mail)
    monkeypatch.setattr(
        auth_routes, "dispatch_user_registered", _recorder("user.registered")
    )
    monkeypatch.setattr(triggers, "dispatch_user_approved", _recorder("user.approved"))
    monkeypatch.setattr(triggers, "dispatch_user_rejected", _recorder("user.rejected"))
    return calls


@pytest.fixture
def registration(monkeypatch: pytest.MonkeyPatch) -> Configure:
    """Set the three registration settings for one test."""

    def configure(
        mode: str = "open",
        domains: list[str] | None = None,
        invite_bypass: bool = True,
        superadmins: list[str] | None = None,
    ) -> None:
        monkeypatch.setattr(settings, "REGISTRATION_MODE", mode)
        monkeypatch.setattr(settings, "REGISTRATION_ALLOWED_DOMAINS", domains or [])
        monkeypatch.setattr(settings, "REGISTRATION_INVITE_BYPASS", invite_bypass)
        monkeypatch.setattr(settings, "SUPERADMIN_EMAILS", superadmins or [])

    return configure


async def _register(
    client: AsyncClient, *, email: str, invitation_token: str | None = None
) -> Response:
    body: dict[str, Any] = {"email": email, "password": PASSWORD, "name": "New Comer"}
    if invitation_token is not None:
        body["invitation_token"] = invitation_token
    return await client.post(f"{AUTH}/register", json=body)


def _code(response: Response) -> str | None:
    return response.json().get("code")


async def _invite(
    db_session: AsyncSession,
    event: Event,
    inviter: User,
    *,
    email: str | None,
) -> EventInvitation:
    invitation = await crud_invitation.create(
        db_session,
        event_id=event.id,
        email=email,
        role="member",
        invited_by_id=inviter.id,
        expires_in_days=14,
    )
    await db_session.commit()
    return invitation


@pytest.mark.asyncio
class TestRegistrationPolicy:
    async def test_is_public_and_mirrors_the_settings(
        self, unauthenticated_client: AsyncClient, registration: Configure
    ) -> None:
        registration(mode="approval", domains=["example.org"], invite_bypass=False)

        response = await unauthenticated_client.get(f"{AUTH}/registration-policy")

        assert response.status_code == 200
        assert response.json() == {
            "mode": "approval",
            "allowed_domains": ["example.org"],
            "invite_bypass": False,
        }


@pytest.mark.asyncio
class TestOpenMode:
    async def test_account_works_immediately(
        self,
        unauthenticated_client: AsyncClient,
        registration: Configure,
        quiet_side_effects: Calls,
    ) -> None:
        registration(mode="open")

        response = await _register(unauthenticated_client, email="open@example.com")

        assert response.status_code == 201, response.text
        assert response.json()["user"]["approval_status"] == "approved"
        assert not [c for c in quiet_side_effects if c[0] == "user.registered"]


@pytest.mark.asyncio
class TestApprovalMode:
    async def test_new_account_waits_and_admins_are_told(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        registration: Configure,
        quiet_side_effects: Calls,
    ) -> None:
        registration(mode="approval")

        response = await _register(unauthenticated_client, email="wait@example.com")

        assert response.status_code == 201, response.text
        assert response.json()["user"]["approval_status"] == "pending"
        created = await crud_user.get_by_email(db_session, email="wait@example.com")
        assert created is not None and created.approval_status == "pending"
        assert [
            c[1]["user_id"] for c in quiet_side_effects if c[0] == "user.registered"
        ] == [created.id]

    async def test_pending_account_can_read_its_profile_but_nothing_else(
        self, unauthenticated_client: AsyncClient, registration: Configure
    ) -> None:
        """The session exists so the UI can say "you are waiting", nothing more."""
        registration(mode="approval")
        token = (
            await _register(unauthenticated_client, email="peek@example.com")
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me = await unauthenticated_client.get(f"{USERS}/me", headers=headers)
        events = await unauthenticated_client.get(
            f"{settings.API_V1_STR}/events/", headers=headers
        )

        assert me.status_code == 200
        assert me.json()["approval_status"] == "pending"
        assert events.status_code == 403
        assert _code(events) == "auth.account_pending"

    async def test_superadmin_address_skips_the_queue(
        self, unauthenticated_client: AsyncClient, registration: Configure
    ) -> None:
        """Otherwise a fresh approval deployment has nobody who could approve."""
        registration(mode="approval", superadmins=["boss@example.com"])

        response = await _register(unauthenticated_client, email="boss@example.com")

        assert response.status_code == 201, response.text
        assert response.json()["user"]["approval_status"] == "approved"
        assert response.json()["user"]["is_admin"] is True

    async def test_invited_address_skips_the_queue(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_admin_user: User,
        registration: Configure,
    ) -> None:
        registration(mode="approval")
        await _invite(
            db_session, test_event, test_admin_user, email="guest@example.com"
        )

        response = await _register(unauthenticated_client, email="guest@example.com")

        assert response.status_code == 201, response.text
        assert response.json()["user"]["approval_status"] == "approved"

    async def test_invitation_waits_too_when_bypass_is_off(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_admin_user: User,
        registration: Configure,
    ) -> None:
        registration(mode="approval", invite_bypass=False)
        await _invite(db_session, test_event, test_admin_user, email="slow@example.com")

        response = await _register(unauthenticated_client, email="slow@example.com")

        assert response.json()["user"]["approval_status"] == "pending"


@pytest.mark.asyncio
class TestInviteMode:
    async def test_refuses_a_signup_without_an_invitation(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        registration: Configure,
    ) -> None:
        registration(mode="invite")

        response = await _register(unauthenticated_client, email="walkin@example.com")

        assert response.status_code == 403
        assert _code(response) == "auth.invitation_required"
        assert (
            await crud_user.get_by_email(db_session, email="walkin@example.com") is None
        )

    async def test_accepts_the_link_the_visitor_arrived_through(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_admin_user: User,
        registration: Configure,
    ) -> None:
        registration(mode="invite")
        link = await _invite(db_session, test_event, test_admin_user, email=None)

        response = await _register(
            unauthenticated_client,
            email="linked@example.com",
            invitation_token=link.token,
        )

        assert response.status_code == 201, response.text
        assert response.json()["user"]["approval_status"] == "approved"

    async def test_accepts_an_invitation_sent_to_the_address(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_admin_user: User,
        registration: Configure,
    ) -> None:
        registration(mode="invite")
        await _invite(
            db_session, test_event, test_admin_user, email="Mailed@Example.com"
        )

        response = await _register(unauthenticated_client, email="mailed@example.com")

        assert response.status_code == 201, response.text

    async def test_an_invitation_for_someone_else_is_no_use(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_admin_user: User,
        registration: Configure,
    ) -> None:
        registration(mode="invite")
        theirs = await _invite(
            db_session, test_event, test_admin_user, email="intended@example.com"
        )

        response = await _register(
            unauthenticated_client,
            email="thief@example.com",
            invitation_token=theirs.token,
        )

        assert response.status_code == 403
        assert _code(response) == "auth.invitation_required"

    async def test_a_revoked_invitation_is_no_use(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_admin_user: User,
        registration: Configure,
    ) -> None:
        registration(mode="invite")
        link = await _invite(db_session, test_event, test_admin_user, email=None)
        await crud_invitation.revoke(db_session, invitation=link)
        await db_session.commit()

        response = await _register(
            unauthenticated_client,
            email="late@example.com",
            invitation_token=link.token,
        )

        assert _code(response) == "auth.invitation_required"

    async def test_a_demo_event_invitation_opens_nothing(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_admin_user: User,
        registration: Configure,
    ) -> None:
        """Anyone can start a demo, so its invitations cannot be a door."""
        registration(mode="invite")
        test_event.is_sandbox = True
        db_session.add(test_event)
        link = await _invite(db_session, test_event, test_admin_user, email=None)

        response = await _register(
            unauthenticated_client,
            email="demo@example.com",
            invitation_token=link.token,
        )

        assert _code(response) == "auth.invitation_required"

    async def test_superadmin_address_needs_no_invitation(
        self, unauthenticated_client: AsyncClient, registration: Configure
    ) -> None:
        registration(mode="invite", superadmins=["boss@example.com"])

        response = await _register(unauthenticated_client, email="boss@example.com")

        assert response.status_code == 201, response.text


@pytest.mark.asyncio
class TestAllowedDomains:
    async def test_refuses_an_address_outside_the_list(
        self, unauthenticated_client: AsyncClient, registration: Configure
    ) -> None:
        registration(domains=["gemeinde.de"])

        response = await _register(unauthenticated_client, email="x@gmail.com")

        assert response.status_code == 403
        assert _code(response) == "auth.email_domain_not_allowed"

    async def test_accepts_an_address_on_the_list_in_any_case(
        self, unauthenticated_client: AsyncClient, registration: Configure
    ) -> None:
        registration(domains=["gemeinde.de"])

        response = await _register(unauthenticated_client, email="Pfarrer@Gemeinde.DE")

        assert response.status_code == 201, response.text

    async def test_a_subdomain_is_a_different_domain(
        self, unauthenticated_client: AsyncClient, registration: Configure
    ) -> None:
        registration(domains=["gemeinde.de"])

        response = await _register(
            unauthenticated_client, email="x@evil.gemeinde.de.com"
        )

        assert _code(response) == "auth.email_domain_not_allowed"

    async def test_an_invitation_lets_an_outside_address_in(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_admin_user: User,
        registration: Configure,
    ) -> None:
        registration(domains=["gemeinde.de"])
        await _invite(db_session, test_event, test_admin_user, email="helper@gmail.com")

        response = await _register(unauthenticated_client, email="helper@gmail.com")

        assert response.status_code == 201, response.text

    async def test_without_bypass_the_list_holds_even_for_invitees(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_admin_user: User,
        registration: Configure,
    ) -> None:
        registration(mode="invite", domains=["gemeinde.de"], invite_bypass=False)
        await _invite(db_session, test_event, test_admin_user, email="helper@gmail.com")

        response = await _register(unauthenticated_client, email="helper@gmail.com")

        assert _code(response) == "auth.email_domain_not_allowed"


async def _queued_user(db_session: AsyncSession, *, status: str = "pending") -> User:
    user = User(
        subject=f"local|{uuid.uuid4().hex}",
        email=f"{uuid.uuid4().hex[:10]}@example.com",
        name="Queued",
        approval_status=status,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
class TestApproveAndReject:
    async def test_approve_lets_the_account_in_and_tells_them(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_admin: None,
        quiet_side_effects: Calls,
    ) -> None:
        queued = await _queued_user(db_session)

        response = await async_client.post(f"{USERS}/{queued.id}/approve")

        assert response.status_code == 200, response.text
        assert response.json()["approval_status"] == "approved"
        assert ("user.approved", {"user_id": queued.id}) in quiet_side_effects

    async def test_reject_keeps_the_account_and_records_why(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_admin: None,
        quiet_side_effects: Calls,
    ) -> None:
        queued = await _queued_user(db_session)

        response = await async_client.post(
            f"{USERS}/{queued.id}/reject", json={"reason": "  Not a member  "}
        )

        assert response.status_code == 200, response.text
        assert response.json()["approval_status"] == "rejected"
        assert response.json()["rejection_reason"] == "Not a member"
        assert (
            "user.rejected",
            {"user_id": queued.id, "reason": "Not a member"},
        ) in quiet_side_effects

    async def test_a_rejected_registration_can_still_be_approved(
        self, async_client: AsyncClient, db_session: AsyncSession, as_admin: None
    ) -> None:
        queued = await _queued_user(db_session, status="rejected")

        response = await async_client.post(f"{USERS}/{queued.id}/approve")

        assert response.json()["approval_status"] == "approved"
        assert response.json()["rejection_reason"] is None

    async def test_only_a_waiting_registration_can_be_rejected(
        self,
        async_client: AsyncClient,
        test_user: User,
        as_admin: None,
    ) -> None:
        response = await async_client.post(f"{USERS}/{test_user.id}/reject", json={})

        assert response.status_code == 409
        assert _code(response) == "user.not_pending"

    async def test_approving_twice_notifies_once(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_admin: None,
        quiet_side_effects: Calls,
    ) -> None:
        queued = await _queued_user(db_session)

        await async_client.post(f"{USERS}/{queued.id}/approve")
        await async_client.post(f"{USERS}/{queued.id}/approve")

        assert [c for c in quiet_side_effects if c[0] == "user.approved"] == [
            ("user.approved", {"user_id": queued.id})
        ]

    async def test_is_superadmin_only(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
    ) -> None:
        queued = await _queued_user(db_session)

        response = await async_client.post(f"{USERS}/{queued.id}/approve")

        assert response.status_code == 403


@pytest.mark.asyncio
class TestApprovalNotificationTypes:
    async def test_hidden_unless_the_queue_is_on(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_admin: None,
        registration: Configure,
    ) -> None:
        await crud_notification_type.upsert_from_registry(
            db_session, types=[t.to_dict() for t in ALL_NOTIFICATION_TYPES]
        )
        await db_session.commit()
        codes = {"user.registered", "user.approved", "user.rejected"}

        registration(mode="open")
        listed_open = {
            t["code"]
            for t in (
                await async_client.get(f"{settings.API_V1_STR}/notifications/types")
            ).json()
        }
        registration(mode="approval")
        listed_approval = {
            t["code"]
            for t in (
                await async_client.get(f"{settings.API_V1_STR}/notifications/types")
            ).json()
        }

        assert not listed_open & codes
        assert codes <= listed_approval


@pytest.mark.asyncio
class TestPolicyOverrideHeader:
    """The per-request policy the E2E suite uses instead of flipping settings.

    Its backend runs several worker processes, so changing ``settings`` from a
    test would only reach one of them. The header carries the policy with the
    request instead, and must mean nothing outside ``TESTING``.
    """

    HEADER = {
        "X-Test-Registration-Policy": (
            '{"mode": "invite", "allowed_domains": ["@Gemeinde.de"], '
            '"invite_bypass": false}'
        )
    }

    async def test_overrides_the_policy_while_testing(
        self, unauthenticated_client: AsyncClient, registration: Configure
    ) -> None:
        registration(mode="open")

        policy = await unauthenticated_client.get(
            f"{AUTH}/registration-policy", headers=self.HEADER
        )
        signup = await unauthenticated_client.post(
            f"{AUTH}/register",
            json={"email": "x@gemeinde.de", "password": PASSWORD, "name": "X"},
            headers=self.HEADER,
        )

        assert policy.json() == {
            "mode": "invite",
            "allowed_domains": ["gemeinde.de"],
            "invite_bypass": False,
        }
        assert _code(signup) == "auth.invitation_required"

    async def test_is_ignored_outside_testing(
        self,
        unauthenticated_client: AsyncClient,
        registration: Configure,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        registration(mode="open")
        monkeypatch.setattr(settings, "TESTING", False)

        policy = await unauthenticated_client.get(
            f"{AUTH}/registration-policy", headers=self.HEADER
        )
        signup = await _register(unauthenticated_client, email="free@example.com")

        assert policy.json()["mode"] == "open"
        assert signup.status_code == 201, signup.text

    async def test_a_malformed_header_is_refused(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        response = await unauthenticated_client.get(
            f"{AUTH}/registration-policy",
            headers={"X-Test-Registration-Policy": '{"mode": "closed"}'},
        )

        assert response.status_code == 400
        assert _code(response) == "testing.invalid_registration_policy"
