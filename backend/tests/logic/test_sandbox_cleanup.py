"""Taking a demo away again — the half of the feature that keeps the promise.

This file exists because ``purge_sandbox`` can fail *silently*. Its deletion
order is load-bearing, and getting it wrong raises nothing: it leaves rows
behind that no longer belong to any event. Two foreign keys are responsible.
``tasks.event_id`` is ``ON DELETE SET NULL`` with no delete-orphan cascade, so
deleting the event first orphans its tasks rather than removing them; and
``events.created_by_id`` is ``ON DELETE CASCADE``, so deleting the guest first
deletes the event underneath, firing that SET NULL before any Python runs.

An orphaned task has ``event_id = NULL``. Every scope filter in this
application is built from ``event_id IN (...)``, and a NULL matches no ``IN``
list — so such a row escapes every one of them, forever, with no owner left who
could delete it. That is why the assertions here are not "the event is gone"
but a census: a count per table, plus a global sweep for rows whose parent
pointer went NULL while we were not looking.

The tests build their demos through the real seeder (see
``tests/fixtures/sandbox.py``), because the shapes that get orphaned are
exactly the ones a hand-rolled fixture would forget to create.
"""

import datetime as dt
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic.sandbox.cleanup import count_active, purge_sandbox, sweep_expired
from app.logic.sandbox.service import utc_now
from app.models.auth_session import AuthSession
from app.models.booking import Booking
from app.models.booking_reminder import BookingReminder
from app.models.event import Event
from app.models.event_invitation import EventInvitation
from app.models.event_join_request import EventJoinRequest
from app.models.event_membership import EventMembership
from app.models.location import Location
from app.models.notification import Notification
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User
from app.models.user_availability import UserAvailability, UserAvailabilityDate
from app.models.venue_plan import VenueMarker, VenuePlan, VenuePlanImage
from tests.fixtures.sandbox import SandboxFactory, SandboxSetup

# ── Counting helpers ──────────────────────────────────────────────


async def _count(db: AsyncSession, model: Any, *where: Any) -> int:
    """How many rows of ``model`` satisfy ``where``, straight from the database."""
    result = await db.execute(select(func.count()).select_from(model).where(*where))
    return int(result.scalar_one())


async def _ids(db: AsyncSession, column: Any, *where: Any) -> list[uuid.UUID]:
    return list((await db.execute(select(column).where(*where))).scalars())


@dataclass(frozen=True, slots=True)
class _Inventory:
    """Every id one sandbox owns, captured *before* anything is deleted.

    Taken up front because the only way to ask "did this row survive?" after
    the purge is to have written its id down first — once the event is gone
    there is nothing left to traverse from.
    """

    event_id: uuid.UUID
    task_ids: list[uuid.UUID]
    shift_ids: list[uuid.UUID]
    booking_ids: list[uuid.UUID]
    guest_ids: list[uuid.UUID]
    availability_ids: list[uuid.UUID]
    notification_ids: list[uuid.UUID]
    location_ids: list[uuid.UUID]
    plan_ids: list[uuid.UUID]


async def _inventory(db: AsyncSession, event_id: uuid.UUID) -> _Inventory:
    task_ids = await _ids(db, col(Task.id), col(Task.event_id) == event_id)
    shift_ids = await _ids(db, col(Shift.id), col(Shift.task_id).in_(task_ids))
    return _Inventory(
        location_ids=await _ids(
            db, col(Location.id), col(Location.event_id) == event_id
        ),
        plan_ids=await _ids(db, col(VenuePlan.id), col(VenuePlan.event_id) == event_id),
        event_id=event_id,
        task_ids=task_ids,
        shift_ids=shift_ids,
        booking_ids=await _ids(
            db, col(Booking.id), col(Booking.shift_id).in_(shift_ids)
        ),
        guest_ids=await _ids(
            db,
            col(EventMembership.user_id),
            col(EventMembership.event_id) == event_id,
        ),
        availability_ids=await _ids(
            db, col(UserAvailability.id), col(UserAvailability.event_id) == event_id
        ),
        notification_ids=await _ids(
            db,
            col(Notification.id),
            col(Notification.recipient_id).in_(
                await _ids(
                    db,
                    col(EventMembership.user_id),
                    col(EventMembership.event_id) == event_id,
                )
            ),
        ),
    )


async def _remaining(db: AsyncSession, inv: _Inventory) -> dict[str, int]:
    """One count per table the demo wrote into. All of them must be zero."""
    return {
        "events": await _count(db, Event, col(Event.id) == inv.event_id),
        "tasks": await _count(db, Task, col(Task.id).in_(inv.task_ids)),
        "shifts": await _count(db, Shift, col(Shift.id).in_(inv.shift_ids)),
        "shift_batches": await _count(
            db, ShiftBatch, col(ShiftBatch.task_id).in_(inv.task_ids)
        ),
        "bookings": await _count(db, Booking, col(Booking.id).in_(inv.booking_ids)),
        "booking_reminders": await _count(
            db, BookingReminder, col(BookingReminder.booking_id).in_(inv.booking_ids)
        ),
        "user_availabilities": await _count(
            db, UserAvailability, col(UserAvailability.id).in_(inv.availability_ids)
        ),
        "user_availability_dates": await _count(
            db,
            UserAvailabilityDate,
            col(UserAvailabilityDate.availability_id).in_(inv.availability_ids),
        ),
        "event_memberships": await _count(
            db, EventMembership, col(EventMembership.event_id) == inv.event_id
        ),
        "event_invitations": await _count(
            db, EventInvitation, col(EventInvitation.event_id) == inv.event_id
        ),
        "event_join_requests": await _count(
            db, EventJoinRequest, col(EventJoinRequest.event_id) == inv.event_id
        ),
        # Not deleted explicitly anywhere — ``notifications.recipient_id`` is
        # ON DELETE CASCADE, so these go when the guest does. Counted because
        # that is a property of the schema rather than of this module, and a
        # migration that loosened it would otherwise leave every seeded inbox
        # behind, addressed to an account that no longer exists.
        "notifications": await _count(
            db, Notification, col(Notification.id).in_(inv.notification_ids)
        ),
        "auth_sessions": await _count(
            db, AuthSession, col(AuthSession.user_id).in_(inv.guest_ids)
        ),
        "users": await _count(db, User, col(User.id).in_(inv.guest_ids)),
        "locations": await _count(db, Location, col(Location.id).in_(inv.location_ids)),
        "venue_plans": await _count(db, VenuePlan, col(VenuePlan.id).in_(inv.plan_ids)),
        "venue_plan_images": await _count(
            db, VenuePlanImage, col(VenuePlanImage.plan_id).in_(inv.plan_ids)
        ),
        # By plan *and* by location: a marker must not outlive either parent.
        "venue_markers": await _count(
            db,
            VenueMarker,
            col(VenueMarker.plan_id).in_(inv.plan_ids)
            | col(VenueMarker.location_id).in_(inv.location_ids),
        ),
    }


async def _orphans(db: AsyncSession) -> dict[str, int]:
    """Rows anywhere in the database whose parent pointer has gone NULL.

    Deliberately unscoped. The whole danger is a row that is no longer
    reachable from the sandbox it came from, so a query filtered by that
    sandbox could not find it.
    """
    return {
        "tasks with no event": await _count(db, Task, col(Task.event_id).is_(None)),
        "bookings with no shift": await _count(
            db, Booking, col(Booking.shift_id).is_(None)
        ),
        "reminders with no shift": await _count(
            db, BookingReminder, col(BookingReminder.shift_id).is_(None)
        ),
        # A location marker whose location went away without it. The FK
        # cascades, so this guards against someone loosening it to SET NULL.
        "location markers with no location": await _count(
            db,
            VenueMarker,
            col(VenueMarker.kind) == "location",
            col(VenueMarker.location_id).is_(None),
        ),
    }


async def _expire(db: AsyncSession, sandbox: SandboxSetup, *, minutes: int = 5) -> None:
    """Wind a demo's TTL back so the sweep considers it collectable."""
    sandbox.event.sandbox_expires_at = utc_now() - dt.timedelta(minutes=minutes)
    db.add(sandbox.event)
    await db.flush()


async def _add_pending_decisions(db: AsyncSession, sandbox: SandboxSetup) -> User:
    """Give a demo the invitation and join request the manager variant carries.

    Written here rather than taken from ``seed_sandbox(role="manager")`` on
    purpose. The claim under test is that ``purge_sandbox`` removes these two
    tables, and a test that sourced them from the seeder would go quietly
    vacuous the day the seeder stopped producing them — which is exactly the
    kind of change that leaves rows behind.

    Returns the applicant, who is a guest of this demo too and must therefore
    be collected along with it.
    """
    applicant = User(
        subject="sandbox|applicant-for-purge-test",
        email=None,
        name="Ellis Vaughan",
        is_sandbox=True,
        is_active=True,
        email_verified=False,
        roles=[],
    )
    db.add(applicant)
    await db.flush()

    db.add(
        EventInvitation(
            event_id=sandbox.event.id,
            email="sam.rivera@example.invalid",
            role="member",
            token=secrets.token_urlsafe(32),
            invited_by_id=sandbox.guest.id,
            expires_at=utc_now() + dt.timedelta(days=14),
        )
    )
    db.add(
        EventJoinRequest(
            user_id=applicant.id, event_id=sandbox.event.id, status="pending"
        )
    )
    db.add(
        EventMembership(user_id=applicant.id, event_id=sandbox.event.id, role="member")
    )
    await db.flush()
    return applicant


async def _add_booking_reminder(db: AsyncSession, *, booking_id: uuid.UUID) -> None:
    """Schedule a reminder against one of the demo's bookings.

    The seeder writes none — reminders are created when a volunteer books,
    which in a demo happens during the tour rather than during the seed. So
    without this the ``booking_reminders`` line of the census would be
    vacuously zero both before and after the purge.
    """
    booking = (
        await db.execute(select(Booking).where(col(Booking.id) == booking_id))
    ).scalar_one()
    db.add(
        BookingReminder(
            booking_id=booking.id,
            user_id=booking.user_id,
            shift_id=booking.shift_id,
            remind_at=utc_now() + dt.timedelta(hours=1),
            offset_minutes=60,
        )
    )
    await db.flush()


# ── purge_sandbox ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPurgeSandbox:
    """``purge_sandbox`` — hard-delete one demo and everything it touched."""

    async def test_leaves_no_row_behind_in_any_table(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that every table a demo writes into comes back to zero.

        The invitation, the join request and the booking reminder are added on
        top of the seed so that the census covers all eighteen tables rather
        than the fifteen a freshly seeded helper demo happens to populate. Every
        line of it starts non-zero and must end at zero — a count that was
        never anything but zero proves nothing.
        """
        await _add_pending_decisions(db_session, test_sandbox)
        inv = await _inventory(db_session, test_sandbox.event.id)
        await _add_booking_reminder(db_session, booking_id=inv.booking_ids[0])
        # Guard the guards: an assertion that "nothing remains" is worthless if
        # nothing was there.
        assert inv.task_ids, "the seeder must have produced tasks"
        assert inv.shift_ids, "the seeder must have produced shifts"
        assert inv.booking_ids, "the seeder must have produced bookings"
        assert len(inv.guest_ids) > 1, "the seeder must have produced teammates"
        assert inv.availability_ids, "the seeder must have produced availabilities"
        assert inv.notification_ids, "the seeder must have produced an inbox"
        assert inv.location_ids, "the seeder must have produced locations"
        assert inv.plan_ids, "the seeder must have produced a venue plan"

        before = await _remaining(db_session, inv)
        assert all(count > 0 for count in before.values()), before

        await purge_sandbox(db_session, event_id=inv.event_id)
        # ``tasks.location_id`` is a deferred FK, checked at commit, which the
        # test transaction never reaches. Check it here instead.
        await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

        after = await _remaining(db_session, inv)
        assert after == dict.fromkeys(after, 0)

    async def test_removes_reminders_hanging_off_a_demo_booking(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that a reminder scheduled against a demo shift goes with it.

        The seeder writes none, so without this the ``booking_reminders``
        column of the census above is vacuously zero — and the poller does
        write them, for any booking a guest makes during the tour.
        """
        inv = await _inventory(db_session, test_sandbox.event.id)
        await _add_booking_reminder(db_session, booking_id=inv.booking_ids[0])
        assert await _count(db_session, BookingReminder) == 1

        await purge_sandbox(db_session, event_id=inv.event_id)

        assert await _count(db_session, BookingReminder) == 0

    async def test_orphans_nothing_anywhere_in_the_database(
        self,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
        test_booking: Booking,
    ) -> None:
        """Test that no task loses its event and no booking loses its shift.

        This is the regression test for the deletion order. Delete the event
        before its tasks and ``tasks.event_id`` is SET NULL rather than the row
        being removed; delete a shift before the bookings on it and
        ``bookings.shift_id`` goes the same way. Neither raises. Both leave a
        row that every scope filter in the application will wave through
        forever, because a NULL matches no ``IN (...)``.

        ``test_booking`` is here so the database is not empty of real rows —
        an assertion that counts orphans globally has to be one that a real
        installation would also pass.
        """
        before = await _orphans(db_session)
        assert before == dict.fromkeys(before, 0), (
            "the fixtures themselves must not leave orphans, or this test "
            "cannot tell the purge's from theirs"
        )

        await _add_pending_decisions(db_session, test_sandbox)

        await purge_sandbox(db_session, event_id=test_sandbox.event.id)

        assert await _orphans(db_session) == before

    async def test_does_nothing_to_an_event_that_is_not_a_sandbox(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_booking: Booking,
        test_task: Task,
        test_shift: Shift,
    ) -> None:
        """Test that a real event id is refused rather than obeyed.

        The id this function acts on arrives from a session, and the function
        is reachable from an HTTP route. The ``is_sandbox`` filter on the
        lookup is the only thing between a confused caller and a real event
        being hard-deleted along with its members' accounts.
        """
        inv = await _inventory(db_session, test_event.id)
        before = await _remaining(db_session, inv)

        await purge_sandbox(db_session, event_id=test_event.id)

        assert await _remaining(db_session, inv) == before
        assert await _count(db_session, Event, col(Event.id) == test_event.id) == 1

    async def test_keeps_a_real_account_that_joined_the_demo(
        self,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
        test_user: User,
    ) -> None:
        """Test that only ``is_sandbox`` accounts are collected with the demo.

        Nothing in the product puts a real member inside a sandbox today, but
        the guest list is assembled from ``event_memberships`` — a table the
        join-request approval screen writes to, from inside the manager tour.
        Deleting a real person's account because they appeared in that table
        is not a bug anyone could undo.
        """
        db_session.add(
            EventMembership(
                user_id=test_user.id, event_id=test_sandbox.event.id, role="member"
            )
        )
        await db_session.flush()

        await purge_sandbox(db_session, event_id=test_sandbox.event.id)

        assert await _count(db_session, User, col(User.id) == test_user.id) == 1
        assert (
            await _count(db_session, User, col(User.id) == test_sandbox.guest.id) == 0
        ), "the guest, however, must go"

    async def test_is_idempotent(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that purging twice is not an error.

        ``end_sandbox`` and the TTL sweep can both reach the same demo — a
        visitor clicking "leave" on a session the sweep has already collected
        must still get a clean answer.
        """
        await purge_sandbox(db_session, event_id=test_sandbox.event.id)
        await purge_sandbox(db_session, event_id=test_sandbox.event.id)

    async def test_ignores_an_id_that_matches_nothing(
        self, db_session: AsyncSession
    ) -> None:
        """Test that an unknown event id is a no-op rather than a 500."""
        await purge_sandbox(db_session, event_id=uuid.uuid4())

    async def test_leaves_a_second_demo_untouched(
        self, db_session: AsyncSession, make_sandbox: SandboxFactory
    ) -> None:
        """Test that purging one guest's demo does not touch the next one's.

        Both are seeded from the same specs and both are ``is_sandbox``, so a
        filter written against the flag instead of against the id would take
        the whole shelf.
        """
        first = await make_sandbox()
        second = await make_sandbox()
        await _add_pending_decisions(db_session, second)
        keep = await _inventory(db_session, second.event.id)
        await _add_booking_reminder(db_session, booking_id=keep.booking_ids[0])

        await purge_sandbox(db_session, event_id=first.event.id)

        after = await _remaining(db_session, keep)
        assert all(count > 0 for count in after.values()), after


# ── sweep_expired ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSweepExpired:
    """``sweep_expired`` — what makes the feature self-cleaning with no scheduler."""

    async def test_collects_only_the_demos_whose_ttl_has_run_out(
        self, db_session: AsyncSession, make_sandbox: SandboxFactory
    ) -> None:
        """Test that a live demo survives a sweep that takes an expired one."""
        stale = await make_sandbox()
        live = await make_sandbox()
        await _expire(db_session, stale)

        swept = await sweep_expired(db_session, now=utc_now())

        assert swept == 1
        assert await _count(db_session, Event, col(Event.id) == stale.event.id) == 0
        assert await _count(db_session, Event, col(Event.id) == live.event.id) == 1

    async def test_takes_the_whole_demo_not_just_its_event_row(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the sweep goes through ``purge_sandbox`` rather than round it.

        A sweep implemented as ``DELETE FROM events WHERE …`` would pass a test
        that only counted events, and would orphan every task it touched.
        """
        await _add_pending_decisions(db_session, test_sandbox)
        inv = await _inventory(db_session, test_sandbox.event.id)
        orphans_before = await _orphans(db_session)
        await _expire(db_session, test_sandbox)

        assert await sweep_expired(db_session, now=utc_now()) == 1

        after = await _remaining(db_session, inv)
        assert after == dict.fromkeys(after, 0)
        assert await _orphans(db_session) == orphans_before

    async def test_respects_the_limit(
        self, db_session: AsyncSession, make_sandbox: SandboxFactory
    ) -> None:
        """Test that a backlog is taken in batches rather than in one click.

        The bound is what stops a long-idle deployment turning one visitor's
        button press into a hundred cascading deletes. The remainder is not
        lost — the next call takes it.
        """
        sandboxes = [await make_sandbox() for _ in range(3)]
        for sandbox in sandboxes:
            await _expire(db_session, sandbox)

        assert await sweep_expired(db_session, now=utc_now(), limit=2) == 2
        assert await _count(db_session, Event, col(Event.is_sandbox).is_(True)) == 1

        assert await sweep_expired(db_session, now=utc_now(), limit=2) == 1
        assert await _count(db_session, Event, col(Event.is_sandbox).is_(True)) == 0

    async def test_takes_the_oldest_first(
        self, db_session: AsyncSession, make_sandbox: SandboxFactory
    ) -> None:
        """Test that a limited sweep starts at the demo that expired longest ago.

        Without the ordering, a deployment with more expired demos than
        ``limit`` could keep collecting the same recent ones and never reach
        the oldest — which are precisely the rows the sweep exists to remove.
        """
        recent = await make_sandbox()
        ancient = await make_sandbox()
        await _expire(db_session, recent, minutes=1)
        await _expire(db_session, ancient, minutes=600)

        assert await sweep_expired(db_session, now=utc_now(), limit=1) == 1

        assert await _count(db_session, Event, col(Event.id) == ancient.event.id) == 0
        assert await _count(db_session, Event, col(Event.id) == recent.event.id) == 1

    async def test_is_idempotent(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that a second sweep with nothing left to do reports zero."""
        await _expire(db_session, test_sandbox)

        assert await sweep_expired(db_session, now=utc_now()) == 1
        assert await sweep_expired(db_session, now=utc_now()) == 0

    async def test_spares_a_demo_whose_deadline_has_not_arrived(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the comparison is ``<= now`` against a future deadline."""
        assert await sweep_expired(db_session, now=utc_now()) == 0
        assert (
            await _count(db_session, Event, col(Event.id) == test_sandbox.event.id) == 1
        )

    async def test_ignores_a_real_event_that_carries_an_expiry(
        self, db_session: AsyncSession, test_event: Event
    ) -> None:
        """Test that ``is_sandbox`` — not the deadline — is what selects a row.

        ``sandbox_expires_at`` is meaningless on a real event and NULL there in
        practice. A sweep keyed on the timestamp alone would delete an ordinary
        event the moment anything ever set that column.
        """
        test_event.sandbox_expires_at = utc_now() - dt.timedelta(hours=1)
        db_session.add(test_event)
        await db_session.flush()

        assert await sweep_expired(db_session, now=utc_now()) == 0
        assert await _count(db_session, Event, col(Event.id) == test_event.id) == 1

    async def test_ignores_a_sandbox_with_no_deadline_at_all(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that a NULL deadline means "not yet", never "long overdue".

        SQL's three-valued logic would answer neither true nor false to
        ``NULL <= now``, so the ``IS NOT NULL`` clause is what keeps this
        predictable rather than dialect-dependent.
        """
        test_sandbox.event.sandbox_expires_at = None
        db_session.add(test_sandbox.event)
        await db_session.flush()

        assert await sweep_expired(db_session, now=utc_now()) == 0
        assert (
            await _count(db_session, Event, col(Event.id) == test_sandbox.event.id) == 1
        )


# ── count_active ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCountActive:
    """``count_active`` — the real concurrency ceiling, counted in SQL.

    It has to be the real one: the rate limiter's counters live in a single
    worker process and ``RateLimiter.check`` returns immediately under
    ``TESTING``, so it cannot be relied on as a ceiling here or in production.
    """

    async def test_counts_nothing_when_no_demo_is_running(
        self, db_session: AsyncSession, test_event: Event
    ) -> None:
        """Test that ordinary events do not count toward the ceiling."""
        assert await count_active(db_session, now=utc_now()) == 0

    async def test_counts_each_live_demo_once(
        self, db_session: AsyncSession, make_sandbox: SandboxFactory
    ) -> None:
        """Test that two running demos count as two."""
        await make_sandbox()
        await make_sandbox()

        assert await count_active(db_session, now=utc_now()) == 2

    async def test_stops_counting_a_demo_once_its_ttl_passes(
        self, db_session: AsyncSession, make_sandbox: SandboxFactory
    ) -> None:
        """Test that an expired demo frees its slot before it is swept.

        The order in ``create_sandbox`` is sweep, then count — but the count
        must be correct on its own, because a sweep bounded by ``limit`` can
        leave expired rows in the table.
        """
        stale = await make_sandbox()
        await make_sandbox()
        await _expire(db_session, stale)

        assert await count_active(db_session, now=utc_now()) == 1

    async def test_ignores_a_real_event_that_carries_an_expiry(
        self, db_session: AsyncSession, test_event: Event
    ) -> None:
        """Test that the ceiling is counted against demos and nothing else."""
        test_event.sandbox_expires_at = utc_now() + dt.timedelta(hours=1)
        db_session.add(test_event)
        await db_session.flush()

        assert await count_active(db_session, now=utc_now()) == 0
