"""A demo belongs to exactly one account, and the superadmin is not it.

That sentence is the whole invariant, and it is unusual enough to be worth
spelling out: everywhere else in this application the platform superadmin is
the account that can see anything. Here they deliberately cannot. A sandbox is
a stranger's throwaway data, seeded by an anonymous visitor with no agreement
of any kind; putting it in the admin event list would show one visitor's made-up
rota to an operator whose only available action on it is to break it.

The invariant is not enforced in one place. It is enforced in about a dozen —
every listing query that a superadmin can run without an event filter, plus the
one gate every read of a single event goes through. Each of those is a separate
opportunity to forget, so this file is one test per guard, named after it, and
each one is paired with the positive case: the demo's own guest still sees
their demo. A guard that hid the sandbox from everybody would pass the negative
half and leave the visitor staring at an empty app.

Two things to know about how these are driven:

* **The guest's perspective goes through ``unauthenticated_client``** with the
  real access token their sandbox was handed. There is no identity override for
  a guest, and inventing one would test the override.
* **The organiser screens are reached by promoting the guest's membership**
  rather than by seeding ``role="manager"``, which currently raises — see
  ``_promote_to_owner`` and the xfails in ``test_sandbox_seed.py``.
"""

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.logic.notifications.channels.base import (
    UNDELIVERABLE_SUBJECT_PREFIXES,
    is_undeliverable,
)
from app.logic.notifications.service import NotificationService
from app.models.event_join_request import EventJoinRequest
from app.models.event_membership import EventMembership
from app.models.notification import Notification, NotificationType
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from tests.fixtures.client import act_as
from tests.fixtures.sandbox import SandboxSetup

API = settings.API_V1_STR


def _as_guest(sandbox: SandboxSetup) -> dict[str, str]:
    """The Authorization header the demo's own browser would send."""
    return {"Authorization": f"Bearer {sandbox.session.access_token}"}


async def _promote_to_owner(db: AsyncSession, sandbox: SandboxSetup) -> None:
    """Give the guest the role the organiser tour is seeded with.

    ``role="manager"`` would do this at seed time. Doing it here instead keeps
    the guard tests below independent of the seeder — what they are about is
    that a sandbox owner is refused *despite* passing
    ``require_event_role(minimum="admin")``, and the membership row is the only
    part of the seed that has any bearing on that.
    """
    membership = (
        await db.execute(
            select(EventMembership).where(
                col(EventMembership.user_id) == sandbox.guest.id,
                col(EventMembership.event_id) == sandbox.event.id,
            )
        )
    ).scalar_one()
    membership.role = "owner"
    db.add(membership)
    await db.flush()


async def _teammate_id(db: AsyncSession, sandbox: SandboxSetup) -> uuid.UUID:
    """One of the seeded colleagues — anybody in the demo who is not the guest."""
    return (
        (
            await db.execute(
                select(col(EventMembership.user_id)).where(
                    col(EventMembership.event_id) == sandbox.event.id,
                    col(EventMembership.user_id) != sandbox.guest.id,
                )
            )
        )
        .scalars()
        .first()
    )  # pyright: ignore[reportReturnType]


async def _sandbox_task_ids(db: AsyncSession, sandbox: SandboxSetup) -> set[str]:
    rows = await db.execute(
        select(col(Task.id)).where(col(Task.event_id) == sandbox.event.id)
    )
    return {str(task_id) for task_id in rows.scalars()}


async def _sandbox_shift_ids(db: AsyncSession, sandbox: SandboxSetup) -> set[str]:
    task_ids = await _sandbox_task_ids(db, sandbox)
    rows = await db.execute(
        select(col(Shift.id)).where(
            col(Shift.task_id).in_([uuid.UUID(t) for t in task_ids])
        )
    )
    return {str(shift_id) for shift_id in rows.scalars()}


# ── Event listings ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestEventListings:
    """``crud.event._apply_scope`` — the four slices ``GET /events/`` can return."""

    @pytest.mark.parametrize("scope", ["mine", "discover", "featured", "all"])
    async def test_an_ordinary_user_sees_no_demo_in_any_scope(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
        scope: str,
    ) -> None:
        """Test that no scope a signed-in stranger can ask for contains a demo.

        ``all`` is included even though it degrades to ``mine`` for a
        non-superadmin: that degradation is itself part of the guard, and a
        change that stopped degrading would show up here first.
        """
        response = await async_client.get(f"{API}/events/", params={"scope": scope})

        assert response.status_code == 200, response.text
        ids = {item["id"] for item in response.json()["items"]}
        assert str(test_sandbox.event.id) not in ids

    async def test_the_superadmin_sees_no_demo_under_scope_all(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test that "everything" stops short of the demos.

        ``all`` is the one scope with no membership filter behind it, so it is
        the only listing where the exclusion has to be written out rather than
        falling out of the event scope.
        """
        response = await async_client.get(f"{API}/events/", params={"scope": "all"})

        assert response.status_code == 200, response.text
        ids = {item["id"] for item in response.json()["items"]}
        assert str(test_sandbox.event.id) not in ids
        assert response.json()["total"] == 0

    async def test_the_guest_sees_their_own_demo_under_mine(
        self, unauthenticated_client: AsyncClient, test_sandbox: SandboxSetup
    ) -> None:
        """Test the other half: the visitor's event list is not empty.

        ``mine`` is membership-scoped, so it is already correct for a guest
        looking at their own demo — which is why the exclusion belongs on the
        other three scopes and not on this one.
        """
        response = await unauthenticated_client.get(
            f"{API}/events/", params={"scope": "mine"}, headers=_as_guest(test_sandbox)
        )

        assert response.status_code == 200, response.text
        ids = {item["id"] for item in response.json()["items"]}
        assert ids == {str(test_sandbox.event.id)}


@pytest.mark.asyncio
class TestEventById:
    """``logic.permissions.require_event_visible`` — the gate every single read passes."""

    async def test_the_superadmin_gets_404_for_a_demo(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test that the sandbox check runs *before* the role check.

        ``get_event_role`` reports the superadmin as owner of every event, so a
        sandbox test placed after it would leave them able to read any
        visitor's demo by id — and the listing exclusions above would look like
        they were working.
        """
        response = await async_client.get(f"{API}/events/{test_sandbox.event.id}")

        assert response.status_code == 404, response.text
        assert response.json()["code"] == "event.not_found"

    async def test_an_ordinary_user_gets_404_for_a_demo(
        self, async_client: AsyncClient, test_sandbox: SandboxSetup
    ) -> None:
        """Test that 404 rather than 403 is the answer, so ids cannot be probed."""
        response = await async_client.get(f"{API}/events/{test_sandbox.event.id}")

        assert response.status_code == 404, response.text

    async def test_the_guest_can_read_their_own(
        self, unauthenticated_client: AsyncClient, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the owner of the demo is exempt from the exemption."""
        response = await unauthenticated_client.get(
            f"{API}/events/{test_sandbox.event.id}", headers=_as_guest(test_sandbox)
        )

        assert response.status_code == 200, response.text
        assert response.json()["is_sandbox"] is True


@pytest.mark.asyncio
class TestSelectedEvent:
    """``PUT /users/me/selected-event`` — the dashboard scope."""

    async def test_the_superadmin_cannot_adopt_a_demo_as_their_scope(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test that the membership check's ``is_admin`` bypass is fenced off.

        The membership test on this endpoint lets ``is_admin`` straight
        through, which would otherwise let the superadmin point their whole
        dashboard at a stranger's demo — and every screen behind it reads
        through that selection.
        """
        response = await async_client.put(
            f"{API}/users/me/selected-event",
            json={"selected_event_id": str(test_sandbox.event.id)},
        )

        assert response.status_code == 404, response.text
        assert response.json()["code"] == "event.not_found"

    async def test_the_guest_may_select_their_own(
        self, unauthenticated_client: AsyncClient, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the guest's own selection still goes through the endpoint.

        ``create_sandbox`` presets it, but the demo's event switcher writes it
        again — a guard keyed on ``is_sandbox`` alone would break that.
        """
        response = await unauthenticated_client.put(
            f"{API}/users/me/selected-event",
            json={"selected_event_id": str(test_sandbox.event.id)},
            headers=_as_guest(test_sandbox),
        )

        assert response.status_code == 200, response.text
        assert response.json()["selected_event_id"] == str(test_sandbox.event.id)


@pytest.mark.asyncio
class TestFeaturing:
    """``PATCH /events/{id}/featured`` — the superadmin's remaining editorial role."""

    async def test_a_demo_cannot_be_put_on_the_home_screen(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test that featuring a demo is refused with its own code.

        The home screen is the most public surface the application has, and a
        featured event that deletes itself within the hour would leave a dead
        card on it. 422 rather than 404 because this is the one endpoint whose
        whole job is to act on events by id — the superadmin is allowed to know
        this row exists, just not to promote it.
        """
        response = await async_client.patch(
            f"{API}/events/{test_sandbox.event.id}/featured",
            json={"is_featured": True},
        )

        assert response.status_code == 422, response.text
        assert response.json()["code"] == "event.sandbox_not_featurable"


# ── Tasks and shifts ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestTaskListings:
    """``crud.task._apply_filters`` — where the demo exclusion is read off the task.

    Off the *task*, not off its event, and that is the interesting part.
    ``tasks.event_id`` is ON DELETE SET NULL, so a task can outlive its event
    with a NULL event_id — and a NULL matches no ``IN (...)``, which would make
    such a row visible to everyone. ``Task.is_sandbox`` is denormalised for
    exactly that case.
    """

    async def test_the_superadmin_task_list_excludes_demo_tasks(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test that an unrestricted task query still filters the demos out."""
        seeded = await _sandbox_task_ids(db_session, test_sandbox)
        assert seeded, "the seeder must have produced tasks to hide"

        response = await async_client.get(f"{API}/tasks/", params={"all_events": True})

        assert response.status_code == 200, response.text
        assert {item["id"] for item in response.json()["items"]} & seeded == set()
        assert response.json()["total"] == 0

    async def test_the_superadmin_task_feed_excludes_demo_tasks(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test the feed separately from the list.

        They are two endpoints over one filter builder today, which is exactly
        why both are asserted: the day someone gives the feed its own query,
        this is what notices.
        """
        seeded = await _sandbox_task_ids(db_session, test_sandbox)

        response = await async_client.get(
            f"{API}/tasks/feed", params={"all_events": True}
        )

        assert response.status_code == 200, response.text
        assert {item["id"] for item in response.json()["items"]} & seeded == set()

    async def test_the_guest_sees_the_tasks_in_their_demo(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test that the tour's first screen is not empty."""
        seeded = await _sandbox_task_ids(db_session, test_sandbox)

        response = await unauthenticated_client.get(
            f"{API}/tasks/", headers=_as_guest(test_sandbox)
        )

        assert response.status_code == 200, response.text
        assert {item["id"] for item in response.json()["items"]} == seeded


@pytest.mark.asyncio
class TestShiftListings:
    """``crud.shift._apply_event_scope`` — scope through the task, since shifts have none."""

    async def test_the_unfiltered_shift_list_does_not_leak_demo_shifts(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test ``GET /shifts/`` with no ``task_id`` — the widest query available.

        With a ``task_id`` the caller has already named something they can be
        checked against. Without one, this endpoint is a straight read of the
        shifts table, and the join to ``tasks`` is the only thing standing
        between the superadmin and every demo shift in the installation.
        """
        seeded = await _sandbox_shift_ids(db_session, test_sandbox)
        assert seeded, "the seeder must have produced shifts to hide"

        response = await async_client.get(f"{API}/shifts/", params={"limit": 200})

        assert response.status_code == 200, response.text
        assert {item["id"] for item in response.json()["items"]} & seeded == set()
        assert response.json()["total"] == 0

    async def test_a_demo_shift_is_not_readable_by_id(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test that the by-id route resolves the event and runs the visibility gate.

        This route had no permission check at all before: any signed-in account
        could read any shift in the installation by id. Routing it through
        ``require_event_visible`` is what also keeps demo shifts private, since
        that gate is where the sandbox test lives.
        """
        shift_id = next(iter(await _sandbox_shift_ids(db_session, test_sandbox)))

        response = await async_client.get(f"{API}/shifts/{shift_id}")

        assert response.status_code == 404, response.text

    async def test_the_guest_sees_the_shifts_in_their_demo(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test that the staffing board has something on it for the visitor."""
        seeded = await _sandbox_shift_ids(db_session, test_sandbox)

        response = await unauthenticated_client.get(
            f"{API}/shifts/", params={"limit": 200}, headers=_as_guest(test_sandbox)
        )

        assert response.status_code == 200, response.text
        returned = {item["id"] for item in response.json()["items"]}
        assert returned and returned <= seeded


_SCHEDULE = {
    "default_start_time": "09:00:00",
    "default_end_time": "11:00:00",
    "shift_duration_minutes": 60,
    "people_per_shift": 1,
}


@pytest.mark.asyncio
class TestTasksTheGuestCreates:
    """A task the guest adds to their demo is as private as a seeded one.

    The seeder and the clone set ``Task.is_sandbox`` themselves, but the create
    routes take no such field, so ``crud.task.create`` copies it from the
    event. The single-task gate (``require_task_visible``) decides on the event
    as well, so a row whose own flag is wrong still answers 404.

    Driven through ``act_as`` rather than the guest's token, because the test
    switches between the guest and the superadmin.
    """

    async def _create(
        self,
        app: FastAPI,
        client: AsyncClient,
        db: AsyncSession,
        sandbox: SandboxSetup,
        route: str,
        *,
        status: str = "published",
    ) -> tuple[Task, str]:
        """The task the guest created through ``route``, and one of its shifts."""
        await _promote_to_owner(db, sandbox)
        day = sandbox.event.start_date.isoformat()
        body = {
            "name": "Bar",
            "start_date": day,
            "end_date": day,
            "status": status,
            "event_id": str(sandbox.event.id),
        }
        with act_as(app, sandbox.guest):
            if route == "with-shifts":
                r = await client.post(
                    f"{API}/tasks/with-shifts", json={**body, "schedule": _SCHEDULE}
                )
                assert r.status_code == 201, r.text
                task_id = r.json()["task"]["id"]
            else:
                r = await client.post(f"{API}/tasks/", json=body)
                assert r.status_code == 201, r.text
                task_id = r.json()["id"]
                shift = await client.post(
                    f"{API}/shifts/",
                    json={
                        "task_id": task_id,
                        "title": "Bar",
                        "date": day,
                        "start_time": "18:00:00",
                        "end_time": "22:00:00",
                    },
                )
                assert shift.status_code == 201, shift.text
        task = await db.get(Task, uuid.UUID(task_id), populate_existing=True)
        assert task is not None
        shift_id = (
            (
                await db.execute(
                    select(col(Shift.id)).where(col(Shift.task_id) == task.id)
                )
            )
            .scalars()
            .first()
        )
        assert shift_id is not None
        return task, str(shift_id)

    @pytest.mark.parametrize("route", ["plain", "with-shifts"])
    async def test_the_superadmin_cannot_read_it(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
        test_admin_user: User,
        route: str,
    ) -> None:
        task, shift_id = await self._create(
            app, async_client, db_session, test_sandbox, route
        )
        assert task.is_sandbox is True

        with act_as(app, test_admin_user):
            reads = {
                "task": await async_client.get(f"{API}/tasks/{task.id}"),
                "shift": await async_client.get(f"{API}/shifts/{shift_id}"),
                "roster": await async_client.get(f"{API}/shifts/{shift_id}/bookings"),
            }
            shifts = await async_client.get(f"{API}/shifts/", params={"limit": 200})
            tasks = await async_client.get(f"{API}/tasks/", params={"all_events": True})
        for name, r in reads.items():
            assert r.status_code == 404, (name, r.text)
        assert shift_id not in {s["id"] for s in shifts.json()["items"]}
        assert str(task.id) not in {t["id"] for t in tasks.json()["items"]}

        # Its guest still opens it.
        with act_as(app, test_sandbox.guest):
            own = await async_client.get(f"{API}/shifts/{shift_id}")
        assert own.status_code == 200, own.text

    async def test_publishing_it_notifies_nobody(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The publish fan-out reaches every account; its hard stop reads the flag."""
        calls: list[dict[str, Any]] = []

        async def _record(**kwargs: Any) -> None:
            calls.append(kwargs)

        monkeypatch.setattr(
            "app.logic.notifications.triggers.dispatch_task_published", _record
        )
        task, _ = await self._create(
            app, async_client, db_session, test_sandbox, "plain", status="draft"
        )
        with act_as(app, test_sandbox.guest):
            r = await async_client.patch(
                f"{API}/tasks/{task.id}", json={"status": "published"}
            )
        assert r.status_code == 200, r.text
        assert [c["is_sandbox"] for c in calls] == [True]


# ── Aggregates ────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDashboardAndReporting:
    """The two screens that count rather than list, and so cannot be scoped by id."""

    async def test_the_superadmin_sidebar_does_not_show_a_demo(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test the sidebar's own exclusion, which cannot lean on an event scope.

        ``visible_event_ids`` is None for the superadmin, so it is not what
        keeps demos out of their sidebar — the ``is_sandbox`` clause has to
        stand on its own there.
        """
        response = await async_client.get(f"{API}/dashboard/sidebar")

        assert response.status_code == 200, response.text
        ids = {event["id"] for event in response.json()["events"]}
        assert str(test_sandbox.event.id) not in ids

    async def test_the_guest_sidebar_shows_their_own_demo(
        self, unauthenticated_client: AsyncClient, test_sandbox: SandboxSetup
    ) -> None:
        """Test the second clause of that same filter — the one that lets the owner through."""
        response = await unauthenticated_client.get(
            f"{API}/dashboard/sidebar", headers=_as_guest(test_sandbox)
        )

        assert response.status_code == 200, response.text
        ids = {event["id"] for event in response.json()["events"]}
        assert ids == {str(test_sandbox.event.id)}

    async def test_reporting_totals_exclude_the_demo(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test that a demo does not move the numbers on the platform-wide report.

        Reporting is the one place where a caller may legitimately have no
        event filter at all, so the exclusion is its own clause applied exactly
        where the scope filter would otherwise have gone. Totals rather than
        ids, because that is all this screen exposes — and a demo that leaked
        here would be invisible until the figures stopped making sense.
        """
        response = await async_client.get(f"{API}/reporting/overview")

        assert response.status_code == 200, response.text
        overview = response.json()["overview"]
        assert overview["total_tasks"] == 0
        assert overview["total_shifts"] == 0
        assert overview["total_bookings"] == 0
        assert response.json()["top_volunteers"] == []

    async def test_the_guest_sees_their_own_numbers(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test that the organiser tour's reporting screen is not blank.

        Reporting is admin-and-above, so this is the promoted guest — the
        state ``role="manager"`` seeds.
        """
        await _promote_to_owner(db_session, test_sandbox)
        seeded = await _sandbox_task_ids(db_session, test_sandbox)

        response = await unauthenticated_client.get(
            f"{API}/reporting/overview", headers=_as_guest(test_sandbox)
        )

        assert response.status_code == 200, response.text
        assert response.json()["overview"]["total_tasks"] == len(seeded)
        assert response.json()["overview"]["total_bookings"] > 0


@pytest.mark.asyncio
class TestUserDirectory:
    """``crud.user.search`` — the superadmin's people list."""

    async def test_guest_accounts_are_not_people(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test that demo accounts stay out of the user directory."""
        response = await async_client.get(f"{API}/users/", params={"limit": 100})

        assert response.status_code == 200, response.text
        subjects = {item["id"] for item in response.json()["items"]}
        assert str(test_sandbox.guest.id) not in subjects


# ── Invitations, and what still works without them ────────────────


@pytest.mark.asyncio
class TestInvitationsFromADemo:
    """``routes.events._refuse_if_sandbox`` — the guard in front of outbound mail.

    Necessary because a guest is seeded as *owner* of their sandbox so that the
    organiser tour can show them the screens an organiser uses. That role
    passes ``require_event_role(minimum="admin")``, which means the invitation
    endpoints would otherwise happily post an email to any address an anonymous
    visitor typed in. The ``sandbox|`` recipient guard does not help: it tests
    who is being *notified*, and the recipient of an invitation is whoever was
    named in it.
    """

    async def test_a_targeted_invitation_is_refused(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test that inviting an address from a demo answers 403 with its own code."""
        await _promote_to_owner(db_session, test_sandbox)

        response = await unauthenticated_client.post(
            f"{API}/events/{test_sandbox.event.id}/invitations",
            json={"email": "someone@example.com", "role": "member"},
            headers=_as_guest(test_sandbox),
        )

        assert response.status_code == 403, response.text
        assert response.json()["code"] == "sandbox.invitations_disabled"

    async def test_a_share_link_is_refused_too(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test that the guard sits above the email branch, not inside it.

        A link invitation sends no mail, so a guard written into the mailing
        path would let this one through — and hand an anonymous visitor a URL
        that joins strangers into a demo that deletes itself within the hour.
        """
        await _promote_to_owner(db_session, test_sandbox)

        response = await unauthenticated_client.post(
            f"{API}/events/{test_sandbox.event.id}/invitations",
            json={"role": "member"},
            headers=_as_guest(test_sandbox),
        )

        assert response.status_code == 403, response.text
        assert response.json()["code"] == "sandbox.invitations_disabled"

    async def test_the_bulk_endpoint_is_refused(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test the second door into the same behaviour.

        Bulk is a separate handler with its own copy of the guard call. One
        endpoint fenced and the other open is the ordinary shape of this bug.
        """
        await _promote_to_owner(db_session, test_sandbox)

        response = await unauthenticated_client.post(
            f"{API}/events/{test_sandbox.event.id}/invitations/bulk",
            json={"emails": ["a@example.com", "b@example.com"], "role": "member"},
            headers=_as_guest(test_sandbox),
        )

        assert response.status_code == 403, response.text
        assert response.json()["code"] == "sandbox.invitations_disabled"

    async def test_member_roles_can_still_be_changed(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test that the organiser tour's other screens still work.

        Promoting a teammate is one of the two decisions running an event
        actually consists of. A guard written as "demo events are read-only"
        instead of "demo events cannot send mail" would take this with it and
        leave half the tour showing a permission error.
        """
        await _promote_to_owner(db_session, test_sandbox)
        teammate_id = await _teammate_id(db_session, test_sandbox)

        response = await unauthenticated_client.patch(
            f"{API}/events/{test_sandbox.event.id}/members/{teammate_id}",
            json={"role": "admin"},
            headers=_as_guest(test_sandbox),
        )

        assert response.status_code == 200, response.text
        assert response.json()["role"] == "admin"

    async def test_join_requests_can_still_be_decided(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
    ) -> None:
        """Test the other of those two decisions, end to end.

        The seeder puts a pending request in front of every organiser tour
        precisely so this screen is not empty; approving it must reach the
        membership upsert rather than a 403.
        """
        await _promote_to_owner(db_session, test_sandbox)
        applicant = User(
            subject="sandbox|join-request-applicant",
            email=None,
            name="Ellis Vaughan",
            is_sandbox=True,
            is_active=True,
            email_verified=False,
            roles=[],
        )
        db_session.add(applicant)
        await db_session.flush()
        request = EventJoinRequest(
            user_id=applicant.id, event_id=test_sandbox.event.id, status="pending"
        )
        db_session.add(request)
        await db_session.flush()

        response = await unauthenticated_client.post(
            f"{API}/events/{test_sandbox.event.id}/join-requests/{request.id}/decide",
            json={"approve": True, "role": "member"},
            headers=_as_guest(test_sandbox),
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "approved"


# ── Notifications ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestNotifications:
    """Guests are skipped before the row is written, not merely before delivery."""

    async def test_a_guest_gets_no_notification_row_at_all(
        self,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
        test_user: User,
    ) -> None:
        """Test that nothing *dispatched* lands in ``notifications`` for a guest.

        The per-channel guards further down stop the *send* but still leave an
        in-app notification and an SSE unread bump behind — noise inside a demo
        and rows to clean up afterwards. The real account in the same call is
        what proves this is a filter on the recipient rather than the whole
        dispatch quietly turning into a no-op.

        Scoped to the type code this call dispatched, not to the guest's whole
        inbox: the seeder writes one deliberately (``logic/sandbox/seed.py``),
        precisely *because* this guard means the demo can never fill its own
        bell. The two are not in tension — one is a row written for a
        recipient, the other is a send the recipient could never receive.
        """
        db_session.add(
            NotificationType(
                code="test.sandbox_skip",
                name="Sandbox skip",
                description="",
                category="test",
                default_channels=[],
                is_active=True,
            )
        )
        await db_session.flush()

        created = await NotificationService(db_session).notify(
            recipient_ids=[test_sandbox.guest.id, test_user.id],
            type_code="test.sandbox_skip",
            title="Something happened",
            body="Somewhere",
            force_channels=[],
        )

        assert [n.recipient_id for n in created] == [test_user.id]
        rows = await db_session.execute(
            select(Notification).where(
                col(Notification.recipient_id) == test_sandbox.guest.id,
                col(Notification.notification_type_code) == "test.sandbox_skip",
            )
        )
        assert rows.scalars().all() == []


class TestUndeliverableAccounts:
    """``channels.base.is_undeliverable`` — the one list every channel asks.

    Not under the ``asyncio`` mark above: this is a pure predicate over a
    ``User``, and nothing about it needs a database or an event loop.
    """

    def test_every_stand_in_prefix_is_undeliverable(self) -> None:
        """Test that ``is_undeliverable`` covers all three prefixes, and only those.

        The check used to be copied into the email, push and Telegram channels
        separately, and a fourth channel would have shipped without it. It
        lives in one place now — so one place is where the list has to be
        right.
        """
        assert UNDELIVERABLE_SUBJECT_PREFIXES == ("demo|", "test|", "sandbox|")

        for prefix in UNDELIVERABLE_SUBJECT_PREFIXES:
            account = User(subject=f"{prefix}whoever", name="Stand-in", roles=[])
            assert is_undeliverable(account), prefix

        real = User(subject="local|abc123", name="A Person", roles=[])
        assert not is_undeliverable(real)
