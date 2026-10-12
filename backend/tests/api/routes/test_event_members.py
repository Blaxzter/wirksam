"""Route tests for event membership, invitations and join requests.

These endpoints are what replaced the admin-only ``/events/{id}/managers``
surface: an event's own owner and admins run it, and the platform superadmin
is only involved in curating the home screen.
"""

import datetime
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.event_invitation import event_invitation as crud_invitation
from app.crud.event_membership import event_membership as crud_membership
from app.models.event import Event
from app.models.event_invitation import EventInvitation
from app.models.event_join_request import EventJoinRequest
from app.models.location import Location
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User
from app.models.venue_plan import VenueMarker, VenuePlan


@pytest.mark.asyncio
class TestEventMembers:
    """GET/PATCH/DELETE on /events/{id}/members."""

    async def test_member_can_see_the_roster(
        self,
        async_client: AsyncClient,
        test_event: Event,
    ):
        """Being in an event is enough to see who else is."""
        r = await async_client.get(f"/api/v1/events/{test_event.id}/members")

        assert r.status_code == 200
        roles = {m["role"] for m in r.json()}
        assert roles == {"owner", "admin", "member"}

    async def test_non_member_cannot_see_the_roster(
        self,
        async_client: AsyncClient,
        test_private_event: Event,
        as_outsider: None,
    ):
        r = await async_client.get(f"/api/v1/events/{test_private_event.id}/members")

        assert r.status_code == 403

    async def test_event_admin_can_promote_a_member(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        as_event_admin: None,
    ):
        """An event admin can hand out admin without involving the superadmin."""
        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}/members/{test_user.id}",
            json={"role": "admin"},
        )

        assert r.status_code == 200
        assert r.json()["role"] == "admin"

        role = await crud_membership.get_role(
            db_session, user_id=test_user.id, event_id=test_event.id
        )
        assert role == "admin"

    async def test_plain_member_cannot_promote_anyone(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_event_admin_user: User,
    ):
        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}/members/{test_event_admin_user.id}",
            json={"role": "member"},
        )

        assert r.status_code == 403

    async def test_owner_role_cannot_be_changed_directly(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_admin_user: User,
        as_event_admin: None,
    ):
        """Demoting the owner would be a way to take over an event."""
        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}/members/{test_admin_user.id}",
            json={"role": "member"},
        )

        assert r.status_code == 422
        assert r.json()["code"] == "event.cannot_demote_owner"

    async def test_owner_cannot_be_removed(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_admin_user: User,
        as_event_admin: None,
    ):
        """An event must never be left with nobody in charge."""
        r = await async_client.delete(
            f"/api/v1/events/{test_event.id}/members/{test_admin_user.id}"
        )

        assert r.status_code == 422
        assert r.json()["code"] == "event.cannot_remove_owner"

    async def test_member_can_remove_themselves(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ):
        """Leaving does not need anyone's permission."""
        r = await async_client.delete(
            f"/api/v1/events/{test_event.id}/members/{test_user.id}"
        )

        assert r.status_code == 204
        assert (
            await crud_membership.get(
                db_session, user_id=test_user.id, event_id=test_event.id
            )
            is None
        )

    async def test_leaving_clears_a_stale_event_selection(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ):
        """Otherwise the user is stranded on an event they cannot open."""
        test_user.selected_event_id = test_event.id
        db_session.add(test_user)
        await db_session.flush()

        r = await async_client.delete(
            f"/api/v1/events/{test_event.id}/members/{test_user.id}"
        )

        assert r.status_code == 204
        await db_session.refresh(test_user)
        assert test_user.selected_event_id is None

    async def test_member_cannot_remove_someone_else(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_event_admin_user: User,
    ):
        r = await async_client.delete(
            f"/api/v1/events/{test_event.id}/members/{test_event_admin_user.id}"
        )

        assert r.status_code == 403


@pytest.mark.asyncio
class TestOwnershipTransfer:
    """POST /events/{id}/transfer-ownership."""

    async def test_owner_can_hand_over_and_stays_as_admin(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_admin_user: User,
        test_event_admin_user: User,
        as_admin: None,
    ):
        """The outgoing owner keeps working access rather than losing it."""
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/transfer-ownership",
            json={"new_owner_id": str(test_event_admin_user.id)},
        )

        assert r.status_code == 200
        assert (
            await crud_membership.get_role(
                db_session, user_id=test_event_admin_user.id, event_id=test_event.id
            )
            == "owner"
        )
        assert (
            await crud_membership.get_role(
                db_session, user_id=test_admin_user.id, event_id=test_event.id
            )
            == "admin"
        )

    async def test_event_admin_cannot_transfer_ownership(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_user: User,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/transfer-ownership",
            json={"new_owner_id": str(test_user.id)},
        )

        assert r.status_code == 403

    async def test_new_owner_must_already_be_a_member(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_outsider_user: User,
        as_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/transfer-ownership",
            json={"new_owner_id": str(test_outsider_user.id)},
        )

        assert r.status_code == 422
        assert r.json()["code"] == "event.new_owner_not_member"


@pytest.mark.asyncio
class TestEventInvitations:
    """Creating, listing and revoking invitations."""

    async def test_event_admin_can_invite_by_email(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/invitations",
            json={"email": "newcomer@example.com", "role": "member"},
        )

        assert r.status_code == 201
        body = r.json()
        assert body["email"] == "newcomer@example.com"
        assert body["token"]

    async def test_omitting_the_email_mints_a_share_link(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_event_admin: None,
    ):
        """A link invite has no addressee and stays reusable."""
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/invitations",
            json={"role": "member"},
        )

        assert r.status_code == 201
        assert r.json()["email"] is None
        assert r.json()["use_count"] == 0

    async def test_inviting_an_existing_member_is_refused(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_user: User,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/invitations",
            json={"email": test_user.email},
        )

        assert r.status_code == 409
        assert r.json()["code"] == "event.already_member"

    async def test_duplicate_invitation_is_refused(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_event_admin: None,
    ):
        payload = {"email": "twice@example.com"}
        first = await async_client.post(
            f"/api/v1/events/{test_event.id}/invitations", json=payload
        )
        assert first.status_code == 201

        second = await async_client.post(
            f"/api/v1/events/{test_event.id}/invitations", json=payload
        )
        assert second.status_code == 409
        assert second.json()["code"] == "event.already_invited"

    async def test_plain_member_cannot_invite(
        self,
        async_client: AsyncClient,
        test_event: Event,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/invitations",
            json={"email": "nope@example.com"},
        )

        assert r.status_code == 403

    async def test_bulk_invite_reports_skips_instead_of_failing(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_user: User,
        as_event_admin: None,
    ):
        """Pasting a team list twice should be harmless, not a 409."""
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/invitations/bulk",
            json={
                "emails": [
                    "a@example.com",
                    "b@example.com",
                    test_user.email,
                    "a@example.com",
                ],
                "role": "member",
            },
        )

        assert r.status_code == 201
        body = r.json()
        created = {i["email"] for i in body["created"]}
        assert created == {"a@example.com", "b@example.com"}
        assert body["skipped_existing_members"] == [test_user.email]

    async def test_revoked_invitation_disappears_from_the_list(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_event_admin: None,
    ):
        created = await async_client.post(
            f"/api/v1/events/{test_event.id}/invitations",
            json={"email": "revokeme@example.com"},
        )
        invitation_id = created.json()["id"]

        r = await async_client.delete(
            f"/api/v1/events/{test_event.id}/invitations/{invitation_id}"
        )
        assert r.status_code == 204

        listing = await async_client.get(f"/api/v1/events/{test_event.id}/invitations")
        assert [i["id"] for i in listing.json()] == []


@pytest.mark.asyncio
class TestInvitationRedemption:
    """GET/POST on /invitations/{token}."""

    async def test_accepting_grants_the_invited_role(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_private_event: Event,
        test_admin_user: User,
        test_user: User,
    ):
        """The whole point: an invite gets you into a private event."""
        invitation = await crud_invitation.create(
            db_session,
            event_id=test_private_event.id,
            email=test_user.email,
            role="admin",
            invited_by_id=test_admin_user.id,
            expires_in_days=14,
        )

        r = await async_client.post(f"/api/v1/invitations/{invitation.token}/accept")

        assert r.status_code == 200
        assert r.json()["my_role"] == "admin"
        assert (
            await crud_membership.get_role(
                db_session, user_id=test_user.id, event_id=test_private_event.id
            )
            == "admin"
        )

    async def test_preview_does_not_join_the_event(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_private_event: Event,
        test_admin_user: User,
        test_user: User,
    ):
        invitation = await crud_invitation.create(
            db_session,
            event_id=test_private_event.id,
            email=test_user.email,
            role="member",
            invited_by_id=test_admin_user.id,
            expires_in_days=14,
        )

        r = await async_client.get(f"/api/v1/invitations/{invitation.token}")

        assert r.status_code == 200
        body = r.json()
        assert body["event_name"] == test_private_event.name
        assert body["is_valid"] is True
        assert body["already_member"] is False
        assert (
            await crud_membership.get(
                db_session, user_id=test_user.id, event_id=test_private_event.id
            )
            is None
        )

    async def test_invitation_for_another_address_is_refused(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_private_event: Event,
        test_admin_user: User,
    ):
        """A targeted invite is not a bearer token for whoever finds it."""
        invitation = await crud_invitation.create(
            db_session,
            event_id=test_private_event.id,
            email="someone.else@example.com",
            role="member",
            invited_by_id=test_admin_user.id,
            expires_in_days=14,
        )

        r = await async_client.post(f"/api/v1/invitations/{invitation.token}/accept")

        assert r.status_code == 403
        assert r.json()["code"] == "invitation.email_mismatch"

    async def test_share_link_admits_anyone_signed_in(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_private_event: Event,
        test_admin_user: User,
        test_user: User,
    ):
        invitation = await crud_invitation.create(
            db_session,
            event_id=test_private_event.id,
            email=None,
            role="member",
            invited_by_id=test_admin_user.id,
            expires_in_days=14,
        )

        r = await async_client.post(f"/api/v1/invitations/{invitation.token}/accept")

        assert r.status_code == 200
        assert r.json()["my_role"] == "member"

    async def test_revoked_invitation_is_gone(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_private_event: Event,
        test_admin_user: User,
        test_user: User,
    ):
        invitation = await crud_invitation.create(
            db_session,
            event_id=test_private_event.id,
            email=test_user.email,
            role="member",
            invited_by_id=test_admin_user.id,
            expires_in_days=14,
        )
        await crud_invitation.revoke(db_session, invitation=invitation)

        r = await async_client.post(f"/api/v1/invitations/{invitation.token}/accept")

        assert r.status_code == 410
        assert r.json()["code"] == "invitation.revoked"

    async def test_unknown_token_is_404(self, async_client: AsyncClient):
        r = await async_client.get("/api/v1/invitations/not-a-real-token")

        assert r.status_code == 404

    async def test_targeted_invite_is_single_use(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_private_event: Event,
        test_admin_user: User,
        test_user: User,
    ):
        invitation = await crud_invitation.create(
            db_session,
            event_id=test_private_event.id,
            email=test_user.email,
            role="member",
            invited_by_id=test_admin_user.id,
            expires_in_days=14,
        )
        first = await async_client.post(
            f"/api/v1/invitations/{invitation.token}/accept"
        )
        assert first.status_code == 200

        await crud_membership.remove(
            db_session, user_id=test_user.id, event_id=test_private_event.id
        )

        second = await async_client.post(
            f"/api/v1/invitations/{invitation.token}/accept"
        )
        assert second.status_code == 410
        assert second.json()["code"] == "invitation.already_used"


@pytest.mark.asyncio
class TestJoinRequests:
    """Requesting into a public event, and deciding those requests."""

    async def test_outsider_can_request_to_join_a_public_event(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_outsider: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/join-request",
            json={"message": "I would like to help"},
        )

        assert r.status_code == 201
        assert r.json()["status"] == "pending"

    async def test_private_event_is_not_requestable(
        self,
        async_client: AsyncClient,
        test_private_event: Event,
        as_outsider: None,
    ):
        """Invitation-only means invitation-only, and stays a 404 besides."""
        r = await async_client.post(
            f"/api/v1/events/{test_private_event.id}/join-request",
            json={},
        )

        assert r.status_code == 404

    async def test_existing_member_cannot_request(
        self,
        async_client: AsyncClient,
        test_event: Event,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/join-request", json={}
        )

        assert r.status_code == 409
        assert r.json()["code"] == "event.already_member"

    async def test_event_admin_approves_and_the_applicant_becomes_a_member(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_outsider_user: User,
        as_event_admin: None,
    ):
        """The organiser decides, not the platform superadmin."""
        from app.crud.event_join_request import (
            event_join_request as crud_join_request,
        )

        request = await crud_join_request.upsert_pending(
            db_session,
            user_id=test_outsider_user.id,
            event_id=test_event.id,
            message=None,
        )

        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/join-requests/{request.id}/decide",
            json={"approve": True, "role": "member"},
        )

        assert r.status_code == 200
        assert r.json()["status"] == "approved"
        assert (
            await crud_membership.get_role(
                db_session, user_id=test_outsider_user.id, event_id=test_event.id
            )
            == "member"
        )

    async def test_declining_grants_no_membership(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_outsider_user: User,
        as_event_admin: None,
    ):
        from app.crud.event_join_request import (
            event_join_request as crud_join_request,
        )

        request = await crud_join_request.upsert_pending(
            db_session,
            user_id=test_outsider_user.id,
            event_id=test_event.id,
            message=None,
        )

        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/join-requests/{request.id}/decide",
            json={"approve": False},
        )

        assert r.status_code == 200
        assert r.json()["status"] == "declined"
        assert (
            await crud_membership.get(
                db_session, user_id=test_outsider_user.id, event_id=test_event.id
            )
            is None
        )

    async def test_a_decision_cannot_be_made_twice(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_outsider_user: User,
        as_event_admin: None,
    ):
        from app.crud.event_join_request import (
            event_join_request as crud_join_request,
        )

        request = await crud_join_request.upsert_pending(
            db_session,
            user_id=test_outsider_user.id,
            event_id=test_event.id,
            message=None,
        )
        url = f"/api/v1/events/{test_event.id}/join-requests/{request.id}/decide"

        assert (await async_client.post(url, json={"approve": True})).status_code == 200
        second = await async_client.post(url, json={"approve": False})

        assert second.status_code == 409
        assert second.json()["code"] == "event.join_request_decided"

    async def test_plain_member_cannot_see_pending_requests(
        self,
        async_client: AsyncClient,
        test_event: Event,
    ):
        r = await async_client.get(f"/api/v1/events/{test_event.id}/join-requests")

        assert r.status_code == 403


@pytest.mark.asyncio
class TestFeaturedCuration:
    """PATCH /events/{id}/featured — the superadmin's remaining editorial role."""

    async def test_superadmin_can_feature_a_public_event(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_admin: None,
    ):
        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}/featured",
            json={"is_featured": True},
        )

        assert r.status_code == 200
        assert r.json()["is_featured"] is True

    async def test_private_events_cannot_be_featured(
        self,
        async_client: AsyncClient,
        test_private_event: Event,
        as_admin: None,
    ):
        r = await async_client.patch(
            f"/api/v1/events/{test_private_event.id}/featured",
            json={"is_featured": True},
        )

        assert r.status_code == 422
        assert r.json()["code"] == "event.feature_requires_public"

    async def test_event_owner_cannot_feature_their_own_event(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_event_admin: None,
    ):
        """Otherwise the home screen would be a free-for-all."""
        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}/featured",
            json={"is_featured": True},
        )

        assert r.status_code == 403

    async def test_going_private_drops_the_featured_slot(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        as_admin: None,
    ):
        """A featured event pulled out of public listings must not linger."""
        test_event.is_featured = True
        db_session.add(test_event)
        await db_session.flush()

        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}",
            json={"visibility": "private"},
        )

        assert r.status_code == 200
        assert r.json()["is_featured"] is False

    async def test_featured_scope_is_visible_to_an_outsider(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        as_outsider: None,
    ):
        """Featured events are the front door for someone with no events yet."""
        test_event.is_featured = True
        db_session.add(test_event)
        await db_session.flush()

        r = await async_client.get("/api/v1/events/?scope=featured")

        assert r.status_code == 200
        ids = [item["id"] for item in r.json()["items"]]
        assert str(test_event.id) in ids
        assert r.json()["items"][0]["my_role"] is None


@pytest.mark.asyncio
class TestMembershipGatesContent:
    """Membership is the outer boundary for everything inside an event."""

    async def test_outsider_sees_no_tasks(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_task: object,
        as_outsider: None,
    ):
        """A brand-new account sees an empty app, not the whole database."""
        r = await async_client.get("/api/v1/tasks/", params={"all_events": "true"})

        assert r.status_code == 200
        assert r.json()["items"] == []

    async def test_outsider_gets_404_on_a_task_in_someone_elses_event(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_task: object,
        as_outsider: None,
    ):
        task_id = getattr(test_task, "id", None)
        assert isinstance(task_id, uuid.UUID)

        r = await async_client.get(f"/api/v1/tasks/{task_id}")

        assert r.status_code == 404


@pytest.mark.asyncio
class TestUserDeletionCascades:
    """Deleting a user must not trip over the invitation/request tables."""

    async def test_deleting_an_inviter_who_owns_the_event(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_admin_user: User,
    ) -> None:
        """Regression: SET NULL on the inviter raced the event CASCADE.

        Postgres applied both actions in one statement, and the SET NULL
        update re-checked ``event_id`` against an event that the CASCADE had
        already removed — a foreign-key violation on an ordinary user delete.
        """
        await crud_invitation.create(
            db_session,
            event_id=test_event.id,
            email="invitee@example.com",
            role="member",
            invited_by_id=test_admin_user.id,
            expires_in_days=14,
        )

        await db_session.delete(test_admin_user)
        await db_session.flush()

        remaining = await db_session.execute(
            select(func.count()).select_from(EventInvitation)
        )
        assert remaining.scalar_one() == 0

    async def test_deleting_a_decider_of_a_join_request(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_admin_user: User,
        test_outsider_user: User,
    ) -> None:
        """Same shape for join requests, via ``decided_by_id``."""
        from app.crud.event_join_request import event_join_request as crud_join_request

        request = await crud_join_request.upsert_pending(
            db_session,
            user_id=test_outsider_user.id,
            event_id=test_event.id,
            message=None,
        )
        await crud_join_request.decide(
            db_session,
            request=request,
            approve=True,
            decided_by_id=test_admin_user.id,
        )

        await db_session.delete(test_admin_user)
        await db_session.flush()

        remaining = await db_session.execute(
            select(func.count()).select_from(EventJoinRequest)
        )
        assert remaining.scalar_one() == 0

    async def test_deleting_the_owner_of_an_event_with_a_location_graph(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_admin_user: User,
        test_user: User,
        test_location: Location,
        test_location_marker: VenueMarker,
    ) -> None:
        """Regression for the SET NULL on ``tasks.location_id``.

        The user delete cascades to the event in the database, and the event's
        SET NULL on ``tasks.event_id`` re-checks the task row — including its
        ``location_id``, whose location the same statement is removing.
        """
        task = Task(
            name="Garderobe",
            start_date=datetime.date(2026, 6, 11),
            end_date=datetime.date(2026, 6, 11),
            status="published",
            created_by_id=test_user.id,
            event_id=test_event.id,
            location=test_location.name,
            location_id=test_location.id,
        )
        db_session.add(task)
        await db_session.flush()
        batch = ShiftBatch(
            task_id=task.id,
            start_date=task.start_date,
            end_date=task.end_date,
            location=test_location.name,
            location_id=test_location.id,
        )
        db_session.add(batch)
        await db_session.flush()
        shift = Shift(
            task_id=task.id,
            batch_id=batch.id,
            title="Garderobe 18-20",
            date=task.start_date,
            start_time=datetime.time(18, 0),
            end_time=datetime.time(20, 0),
            location=test_location.name,
            location_id=test_location.id,
        )
        db_session.add(shift)
        await db_session.flush()
        plan_id = test_location_marker.plan_id

        await db_session.delete(test_admin_user)
        await db_session.flush()
        # The tasks.location_id check is deferred to commit, which the test
        # transaction never reaches; run the deferred checks now.
        await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

        assert (
            await db_session.get(Event, test_event.id, populate_existing=True) is None
        )
        survivor = await db_session.get(Task, task.id, populate_existing=True)
        assert survivor is not None
        assert (survivor.event_id, survivor.location_id) == (None, None)
        assert survivor.location == "Foyer"
        for row in (batch, shift):
            await db_session.refresh(row)
            assert (row.location_id, row.location) == (None, "Foyer")
        for model, row_id in (
            (Location, test_location.id),
            (VenuePlan, plan_id),
            (VenueMarker, test_location_marker.id),
        ):
            assert await db_session.get(model, row_id, populate_existing=True) is None
