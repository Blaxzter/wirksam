"""What the seeded demo has to contain for the guided tour to be worth taking.

The failure mode this file exists to prevent is not an exception. It is an
empty screen. The tour stops on the task board, the staffing heatmap, "my
bookings", the regenerate dialog and — on the organiser track — the two pending
decisions, and every one of those screens has an empty state that reads as a
broken product rather than as a demo with nothing in it. A visitor who sees one
of those closes the tab, and nothing anywhere logs why.

The notification inbox is the same problem with an extra twist: it cannot fill
itself. ``NotificationService`` drops a sandbox recipient before it writes a
row, so nothing the visitor does during the tour lands in their bell — a demo
inbox is seeded or it is empty for the whole hour.

So these are not assertions about the seeder's implementation. They are the
minimum contract the tour depends on, written down where a change to
``_TASK_SPECS`` or to the day offsets will trip over them: dates spanning today
in both directions, published tasks that can actually be regenerated, shifts
behind and ahead, a booking already in the visitor's name, one upcoming shift
on the first job that the visitor can still take — the only thing the tour asks
them to do — teammates with availabilities, and, for the organiser, one
decision of each kind waiting.

The one thing here that is not about the tour is the last class. No account the
seeder creates may have an email address, and that is a safety property rather
than a presentation one: ``send_verify_email`` and ``request_password_reset``
both short-circuit on a missing address, so an address-less guest cannot be
mailed even by a future code path that forgets to check the ``sandbox|`` prefix.
"""

import datetime as dt
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic.notifications.registry import classification_for_code
from app.logic.sandbox.seed import guest_display_name
from app.models.booking import Booking
from app.models.event_invitation import EventInvitation
from app.models.event_join_request import EventJoinRequest
from app.models.event_membership import EventMembership
from app.models.notification import Notification
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User
from app.models.user_availability import UserAvailability
from app.schemas.sandbox import SandboxRole
from tests.fixtures.sandbox import SandboxFactory, SandboxSetup


async def _tasks(db: AsyncSession, sandbox: SandboxSetup) -> list[Task]:
    rows = await db.execute(
        select(Task)
        .where(col(Task.event_id) == sandbox.event.id)
        .order_by(col(Task.name))
    )
    return list(rows.scalars())


async def _shifts(db: AsyncSession, sandbox: SandboxSetup) -> list[Shift]:
    task_ids = [task.id for task in await _tasks(db, sandbox)]
    rows = await db.execute(select(Shift).where(col(Shift.task_id).in_(task_ids)))
    return list(rows.scalars())


async def _inbox(db: AsyncSession, sandbox: SandboxSetup) -> list[Notification]:
    """The visitor's own notifications, newest first — what the bell opens onto."""
    rows = await db.execute(
        select(Notification)
        .where(col(Notification.recipient_id) == sandbox.guest.id)
        .order_by(col(Notification.created_at).desc())
    )
    return list(rows.scalars())


async def _guests(db: AsyncSession, sandbox: SandboxSetup) -> list[User]:
    rows = await db.execute(
        select(User)
        .join(EventMembership, col(EventMembership.user_id) == col(User.id))
        .where(col(EventMembership.event_id) == sandbox.event.id)
    )
    return list(rows.scalars())


# ── The event itself ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestSeededEvent:
    """The frame every other screen is drawn inside."""

    async def test_spans_today_in_both_directions(
        self, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the week view has columns either side of today.

        A demo event that started tomorrow leaves the past half of every
        calendar blank, and one that ended yesterday reads as expired before
        the visitor has clicked anything.
        """
        today = dt.date.today()

        assert test_sandbox.event.start_date < today
        assert test_sandbox.event.end_date > today
        assert test_sandbox.event.is_expired is False

    async def test_is_published_private_and_unfeatured(
        self, test_sandbox: SandboxSetup
    ) -> None:
        """Test the three flags that decide who else can find it.

        Published so the volunteer screens show anything at all; private so
        that visibility is the second lock behind the explicit ``is_sandbox``
        filters; never featured, because the home screen must not carry a card
        for an event that deletes itself within the hour.
        """
        assert test_sandbox.event.status == "published"
        assert test_sandbox.event.visibility == "private"
        assert test_sandbox.event.is_featured is False

    async def test_carries_a_deadline_and_belongs_to_its_guest(
        self, test_sandbox: SandboxSetup
    ) -> None:
        """Test the two columns the whole lifecycle hangs off.

        ``sandbox_expires_at`` is what the sweep selects on and what the demo
        banner counts down to; ``created_by_id`` is how ``event_id_for_guest``
        resolves which demo a session belongs to — from ownership rather than
        from the selection, which the guest can change.
        """
        assert test_sandbox.event.is_sandbox is True
        assert test_sandbox.event.sandbox_expires_at is not None
        assert test_sandbox.event.sandbox_expires_at > dt.datetime.now(
            dt.timezone.utc
        ).replace(tzinfo=None)
        assert test_sandbox.event.created_by_id == test_sandbox.guest.id

    async def test_the_guest_is_a_member_of_it(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the visitor is in their own event, and not alone in it."""
        guests = await _guests(db_session, test_sandbox)

        assert test_sandbox.guest.id in {guest.id for guest in guests}
        assert len(guests) >= 4, (
            "a staffing board with one person on it teaches nothing"
        )


# ── Tasks and shifts ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestSeededTasks:
    """The board the tour opens on, and the dialog it opens next."""

    async def test_has_several_published_tasks(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the task list is populated and visible to a member.

        Published, not draft: drafts are hidden from anyone below ``admin`` in
        the event, so a helper-track visitor would open the app on an empty
        board.
        """
        tasks = await _tasks(db_session, test_sandbox)

        assert len(tasks) >= 2
        assert {task.status for task in tasks} == {"published"}
        assert all(task.is_sandbox for task in tasks), (
            "the denormalised flag is what keeps a task hidden after its event "
            "is gone — tasks.event_id is ON DELETE SET NULL"
        )

    async def test_every_task_can_be_regenerated(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that each task carries a batch *and* the config that produced it.

        The organiser tour's "add more shifts" step reads the stored
        generation config back into the regenerate form. A task seeded without
        it opens that form empty, which is the one screen in the tour where an
        empty state looks like the visitor broke something.
        """
        tasks = await _tasks(db_session, test_sandbox)

        for task in tasks:
            assert task.shift_duration_minutes, task.name
            assert task.default_start_time is not None, task.name
            assert task.default_end_time is not None, task.name
            assert task.people_per_shift, task.name

            batch = (
                await db_session.execute(
                    select(ShiftBatch).where(col(ShiftBatch.task_id) == task.id)
                )
            ).scalar_one()
            assert batch.shift_duration_minutes == task.shift_duration_minutes
            assert batch.people_per_shift == task.people_per_shift
            assert batch.default_start_time == task.default_start_time
            assert batch.default_end_time == task.default_end_time

    async def test_every_shift_belongs_to_a_batch(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that shifts were generated rather than hand-rolled row by row.

        A shift with no batch cannot be edited or removed as a group, which is
        the workflow the manager screens are built around.
        """
        shifts = await _shifts(db_session, test_sandbox)

        assert shifts
        assert all(shift.batch_id is not None for shift in shifts)

    async def test_shifts_land_behind_today_on_it_and_ahead_of_it(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test all three of past, today and future are populated.

        Each carries a different screen: past shifts give the reporting charts
        a trend rather than a flat line, today's drive the "happening now"
        markers, and future ones are the only shifts a visitor can actually
        book during the tour.
        """
        today = dt.date.today()
        dates = {shift.date for shift in await _shifts(db_session, test_sandbox)}

        assert any(date < today for date in dates), "nothing behind today"
        assert today in dates, "nothing happening today"
        assert any(date > today for date in dates), "nothing to book"

    async def test_the_rota_is_filled_unevenly(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that some shifts are full and some are not.

        A board where every shift is green teaches the reader nothing about
        what the application is for — the gaps are the product.
        """
        shifts = await _shifts(db_session, test_sandbox)
        booked: dict[uuid.UUID | None, int] = {}
        rows = await db_session.execute(
            select(col(Booking.shift_id)).where(
                col(Booking.shift_id).in_([shift.id for shift in shifts])
            )
        )
        for shift_id in rows.scalars():
            booked[shift_id] = booked.get(shift_id, 0) + 1

        fill_rates = {booked.get(shift.id, 0) / shift.max_bookings for shift in shifts}
        assert any(rate >= 1 for rate in fill_rates), "no shift is full"
        assert any(rate < 1 for rate in fill_rates), "no shift has room"


# ── The visitor's own presence in the data ────────────────────────


@pytest.mark.asyncio
class TestSeededBookings:
    """ "My bookings" must not be the first empty screen the visitor sees."""

    async def test_the_visitor_already_holds_bookings(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the guest arrives with a history and something ahead of them.

        Both halves matter: without a past booking the history tab is blank,
        and without a future one the dashboard counter reads zero on arrival —
        which is the number the visitor is being shown the app to avoid.
        """
        shift_by_id = {
            shift.id: shift for shift in await _shifts(db_session, test_sandbox)
        }
        rows = await db_session.execute(
            select(Booking).where(col(Booking.user_id) == test_sandbox.guest.id)
        )
        bookings = list(rows.scalars())
        today = dt.date.today()

        assert bookings
        assert {booking.status for booking in bookings} == {"confirmed"}
        dates = [shift_by_id[booking.shift_id].date for booking in bookings]  # type: ignore[index]
        assert any(date >= today for date in dates), "nothing upcoming"
        assert any(date < today for date in dates), "no history"

    async def test_the_tour_always_has_a_shift_it_can_book(
        self, db_session: AsyncSession, make_sandbox: SandboxFactory
    ) -> None:
        """Test that the first job holds its first shift after today open.

        The one thing the guided tour asks the visitor to *do* is take a shift:
        it opens a chip on the first row of the board and points at *Book
        shift*. That button renders only for a shift that is still to come, has
        a place free and is not one the visitor already holds — so a chip that
        is full, or already theirs, turns the demo's single interactive moment
        into a popover aimed at a button that was never drawn. Which is what
        happened on all but a few per cent of demos: the guest's own bookings
        began at the first upcoming shift of the first job, and the teammates
        filled whatever was left of it.

        Pinned on one specific shift rather than on "some shift somewhere",
        because a board this size nearly always has *a* gap in it by luck — the
        seeder has to reserve one on purpose, and this is the one it reserves:
        the earliest shift of the first job that falls after today. After
        today, not today, because a chip whose start time has already gone by
        reads as a demo that was built last week.

        The second assertion is the step *before* the button, which tells the
        visitor they would be joining people rather than volunteering alone. So
        the shift being open is not enough — somebody has to be on it already.

        Repeated across several demos and both roles because the rota is filled
        from a generator seeded with the guest's own account id, and one demo
        passing would only prove that one draw happened to be kind.
        """
        today = dt.date.today()
        roles: tuple[SandboxRole, ...] = ("helper", "manager")

        for index in range(8):
            sandbox = await make_sandbox(role=roles[index % len(roles)])
            first_job = (
                await db_session.execute(
                    select(Task)
                    .where(col(Task.event_id) == sandbox.event.id)
                    # The order the board itself puts them in: ``crud.task``
                    # sorts on ``start_date`` ascending unless asked otherwise,
                    # so this is the row the tour looks for its chip in.
                    .order_by(col(Task.start_date), col(Task.name))
                    .limit(1)
                )
            ).scalar_one()

            reserved = (
                await db_session.execute(
                    select(Shift)
                    .where(
                        col(Shift.task_id) == first_job.id,
                        col(Shift.date) > today,
                    )
                    .order_by(col(Shift.date), col(Shift.start_time))
                    .limit(1)
                )
            ).scalar_one_or_none()

            assert reserved is not None, (
                f"{first_job.name}: the first job on the board has no shift "
                "after today, so the tour has no chip to open at all"
            )

            takers = [
                booking.user_id
                for booking in (
                    await db_session.execute(
                        select(Booking).where(
                            col(Booking.shift_id) == reserved.id,
                            col(Booking.status) == "confirmed",
                        )
                    )
                ).scalars()
            ]

            assert sandbox.guest.id not in takers, (
                f"{reserved.title}: the visitor already holds the shift the "
                "tour asks them to take"
            )
            assert len(takers) < reserved.max_bookings, (
                f"{reserved.title}: full, so *Book shift* never renders"
            )
            assert takers, (
                f"{reserved.title}: nobody on it, so the roster step has no "
                "name to point at"
            )

    async def test_the_teammates_have_availabilities(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the staffing heatmap has more than one colour on it.

        It is one of the more convincing screens in the application and it
        needs a spread — a single availability type across every teammate
        renders as one flat block.
        """
        rows = await db_session.execute(
            select(UserAvailability).where(
                col(UserAvailability.event_id) == test_sandbox.event.id
            )
        )
        availabilities = list(rows.scalars())

        assert len(availabilities) >= 3
        assert len({a.availability_type for a in availabilities}) >= 2


# ── The inbox the demo cannot fill for itself ─────────────────────


@pytest.mark.asyncio
class TestSeededNotifications:
    """The bell, its badge, and the four tabs behind it.

    Every claim here is one the demo makes on screen and cannot make on its
    own: the notification service refuses sandbox recipients outright, so an
    unseeded demo shows a bell with no badge over an inbox with four empty
    filter tabs. These rows are that inbox.
    """

    async def test_the_visitor_arrives_with_notifications(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the bell opens onto something."""
        inbox = await _inbox(db_session, test_sandbox)

        assert len(inbox) >= 4
        assert all(n.recipient_id == test_sandbox.guest.id for n in inbox)

    async def test_only_the_visitor_gets_one(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the fake teammates have no inbox of their own.

        Nobody can sign into those accounts, so a notification addressed to one
        is a row that exists only to be deleted again. It would also be the
        first sign that the seeder had started fanning out the way a real
        trigger does.
        """
        others = [
            guest.id
            for guest in await _guests(db_session, test_sandbox)
            if guest.id != test_sandbox.guest.id
        ]
        rows = await db_session.execute(
            select(Notification).where(col(Notification.recipient_id).in_(others))
        )

        assert list(rows.scalars()) == []

    async def test_some_are_unread_and_some_are_not(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the badge has a number on it without the list being a wall of bold.

        Both halves are the point. Nothing unread means no badge, and the bell
        is then indistinguishable from a bell with nothing behind it; nothing
        read means every row is highlighted, which is the same as none being.
        """
        inbox = await _inbox(db_session, test_sandbox)

        assert any(not n.is_read for n in inbox), "the bell would carry no badge"
        assert any(n.is_read for n in inbox), "every row would render as unread"
        assert all(n.read_at is not None for n in inbox if n.is_read)
        assert all(n.read_at is None for n in inbox if not n.is_read)

    async def test_every_filter_tab_has_something_behind_it(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that all four classifications are represented.

        The notifications screen offers a pill per classification and each one
        renders its own empty state. A demo that seeded only, say, changes puts
        three empty screens one click away from the full one.
        """
        inbox = await _inbox(db_session, test_sandbox)
        classifications = {
            classification_for_code(n.notification_type_code) for n in inbox
        }

        assert classifications == {"reminder", "change", "match", "announcement"}

    async def test_they_are_stamped_across_the_range_the_list_can_render(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the relative timestamps read as an inbox rather than a batch.

        Everything created in the same second renders as one block of "just
        now", which is what a seeded list looks like when it looks seeded.
        Nothing may be stamped in the future either: the frontend subtracts and
        floors, so a future row also reads as "just now" — and past seven days
        the wording gives way to a plain date, which is where a demo starts
        looking abandoned.
        """
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        inbox = await _inbox(db_session, test_sandbox)
        ages = [(now - n.created_at) for n in inbox]

        assert all(age > dt.timedelta(0) for age in ages), "stamped in the future"
        assert all(age < dt.timedelta(days=7) for age in ages), "renders as a date"
        assert any(age < dt.timedelta(hours=12) for age in ages), "nothing recent"
        assert any(age > dt.timedelta(days=1) for age in ages), "nothing older"

    async def test_nothing_claims_to_have_been_delivered(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that no seeded row records a channel it went out on.

        Nothing was sent — the demo has no address to send to and must never
        acquire one. ``channels_sent`` is the field that would say otherwise,
        and it is the field any future "resend" affordance would read.
        """
        inbox = await _inbox(db_session, test_sandbox)

        assert all(n.channels_sent == [] for n in inbox)
        assert all(n.channels_failed == [] for n in inbox)

    async def test_every_entry_opens_something_that_exists(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the deep-link payloads point into this demo.

        Clicking a notification navigates on whichever of ``task_id``,
        ``event_id`` or ``booking_id`` it carries. A payload naming a row that
        was never seeded — or one belonging to a different sandbox — sends the
        visitor to a 404 from the one screen that exists to be clicked through.
        """
        inbox = await _inbox(db_session, test_sandbox)
        known: dict[str, set[str]] = {
            "task_id": {
                str(task.id) for task in await _tasks(db_session, test_sandbox)
            },
            "slot_id": {
                str(shift.id) for shift in await _shifts(db_session, test_sandbox)
            },
            "user_id": {
                str(guest.id) for guest in await _guests(db_session, test_sandbox)
            },
            "event_id": {str(test_sandbox.event.id)},
            "booking_id": {
                str(booking_id)
                for booking_id in (
                    await db_session.execute(
                        select(col(Booking.id)).where(
                            col(Booking.user_id) == test_sandbox.guest.id
                        )
                    )
                ).scalars()
            },
        }

        assert inbox
        for notification in inbox:
            data = notification.data or {}
            assert data, notification.notification_type_code
            for key, value in data.items():
                assert key in known, key
                assert value in known[key], (
                    f"{notification.notification_type_code}.{key}"
                )

    async def test_the_co_booking_names_someone_actually_on_that_shift(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that "X also booked this shift" is true of the seeded rota.

        The body names a person and the payload names a shift, and the staffing
        board is one click away — so a name taken from the teammate list rather
        than from the roster is a contradiction the visitor can see.
        """
        inbox = await _inbox(db_session, test_sandbox)
        cobooked = next(
            n for n in inbox if n.notification_type_code == "booking.shift_cobooked"
        )
        slot_id = uuid.UUID(str((cobooked.data or {})["slot_id"]))

        rostered = list(
            (
                await db_session.execute(
                    select(User)
                    .join(Booking, col(Booking.user_id) == col(User.id))
                    .where(col(Booking.shift_id) == slot_id)
                )
            ).scalars()
        )

        assert test_sandbox.guest.id in {user.id for user in rostered}
        assert any(
            user.name and user.name in cobooked.body
            for user in rostered
            if user.id != test_sandbox.guest.id
        ), cobooked.body

    async def test_the_reminder_is_stamped_when_it_would_have_been_sent(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the reminder's body and its timestamp agree.

        It says "in 1 day", which is only true of a row written a day before
        the shift starts. Stamping it anywhere else is invisible in the code
        and obvious on screen, because the list prints the age of the row right
        next to the sentence claiming the gap.
        """
        inbox = await _inbox(db_session, test_sandbox)
        reminder = next(
            n for n in inbox if n.notification_type_code == "booking.reminder"
        )
        slot_id = uuid.UUID(str((reminder.data or {})["slot_id"]))
        shift = next(
            shift
            for shift in await _shifts(db_session, test_sandbox)
            if shift.id == slot_id
        )
        starts_at = dt.datetime.combine(shift.date, shift.start_time or dt.time())

        assert "1 day" in reminder.body
        assert starts_at - reminder.created_at == dt.timedelta(days=1)

    async def test_it_speaks_the_language_the_visitor_clicked(
        self, db_session: AsyncSession, make_sandbox: SandboxFactory
    ) -> None:
        """Test that the inbox is written in the demo's language.

        Real notifications are rendered per recipient at dispatch time, so a
        German visitor's inbox is German. A seeded one that is not would be the
        only English screen in an otherwise German demo.
        """
        german = await make_sandbox(language="de")
        english = await make_sandbox(language="en")

        assert any(
            n.title == "Schichtzeit geändert" for n in await _inbox(db_session, german)
        )
        assert any(
            n.title == "Shift Time Changed" for n in await _inbox(db_session, english)
        )


# ── The two tracks ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRoleShapesTheDemo:
    """The role picked on the landing page is the whole configuration of the tour."""

    async def test_a_helper_is_a_plain_member(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the volunteer track cannot reach the organiser screens.

        ``member`` is what leaves the management routes behind the frontend's
        ``requiresEventManager`` guard, which is the half of the application
        the helper tour is deliberately not about.
        """
        membership = (
            await db_session.execute(
                select(EventMembership).where(
                    col(EventMembership.user_id) == test_sandbox.guest.id,
                    col(EventMembership.event_id) == test_sandbox.event.id,
                )
            )
        ).scalar_one()

        assert membership.role == "member"

    async def test_a_helper_gets_no_pending_decisions(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the volunteer track is not given an organiser's inbox.

        A helper cannot open either screen, so an invitation and a join request
        seeded for them would be rows nobody could ever see or act on — and
        rows the purge would still have to remember to remove.
        """
        invitations = await db_session.execute(
            select(EventInvitation).where(
                col(EventInvitation.event_id) == test_sandbox.event.id
            )
        )
        requests = await db_session.execute(
            select(EventJoinRequest).where(
                col(EventJoinRequest.event_id) == test_sandbox.event.id
            )
        )

        assert invitations.scalars().all() == []
        assert requests.scalars().all() == []

    async def test_a_manager_owns_the_event(
        self, db_session: AsyncSession, make_sandbox: SandboxFactory
    ) -> None:
        """Test that the organiser track can reach the screens it is about."""
        sandbox = await make_sandbox(role="manager")

        membership = (
            await db_session.execute(
                select(EventMembership).where(
                    col(EventMembership.user_id) == sandbox.guest.id,
                    col(EventMembership.event_id) == sandbox.event.id,
                )
            )
        ).scalar_one()

        assert membership.role == "owner"

    async def test_a_manager_gets_one_decision_of_each_kind(
        self, db_session: AsyncSession, make_sandbox: SandboxFactory
    ) -> None:
        """Test that both organiser inboxes have exactly one thing waiting.

        Approving a request and inviting someone are the two decisions running
        an event actually consists of, and both screens read as broken when
        empty. The invitation address is on ``example.invalid`` — reserved by
        RFC 2606 and guaranteed never to resolve — because nothing in a demo
        may reach a real inbox even if a send path is added later.
        """
        sandbox = await make_sandbox(role="manager")

        invitations = list(
            (
                await db_session.execute(
                    select(EventInvitation).where(
                        col(EventInvitation.event_id) == sandbox.event.id
                    )
                )
            ).scalars()
        )
        requests = list(
            (
                await db_session.execute(
                    select(EventJoinRequest).where(
                        col(EventJoinRequest.event_id) == sandbox.event.id
                    )
                )
            ).scalars()
        )

        assert len(invitations) == 1
        assert invitations[0].email is not None
        assert invitations[0].email.endswith("@example.invalid")
        assert len(requests) == 1
        assert requests[0].status == "pending"

    async def test_the_organiser_is_told_about_the_join_request(
        self, db_session: AsyncSession, make_sandbox: SandboxFactory
    ) -> None:
        """Test that the pending decision also arrives in the manager's inbox.

        The join-request screen is two clicks deep. The bell is what sends an
        organiser there in the real product, so a demo whose only trace of the
        request is the screen itself teaches the wrong workflow — and the
        notification has to name the applicant the request is actually from,
        because approving it is the next thing the tour asks them to do.
        """
        sandbox = await make_sandbox(role="manager")
        request = (
            await db_session.execute(
                select(EventJoinRequest).where(
                    col(EventJoinRequest.event_id) == sandbox.event.id
                )
            )
        ).scalar_one()
        applicant = (
            await db_session.execute(
                select(User).where(col(User.id) == request.user_id)
            )
        ).scalar_one()

        told = [
            n
            for n in await _inbox(db_session, sandbox)
            if n.notification_type_code == "event.join_requested"
        ]

        assert len(told) == 1
        assert not told[0].is_read
        assert applicant.name and applicant.name in told[0].body
        assert (told[0].data or {})["user_id"] == str(applicant.id)

    async def test_a_helper_is_not_told_about_decisions_they_cannot_make(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that the volunteer inbox carries nothing organiser-shaped.

        A helper cannot open the join-request screen, so an entry pointing at
        it is a dead end — and event-scoped payloads route to event settings,
        which the router's ``requiresEventManager`` guard bounces them off.
        """
        codes = {
            n.notification_type_code for n in await _inbox(db_session, test_sandbox)
        }

        assert "event.join_requested" not in codes

    async def test_the_applicant_is_a_member_so_the_purge_finds_them(
        self, db_session: AsyncSession, make_sandbox: SandboxFactory
    ) -> None:
        """Test that the seeded applicant is enumerable as a guest of the demo.

        ``purge_sandbox`` finds the accounts to delete by joining through
        ``event_memberships``. An applicant seeded without one would survive
        every purge and every sweep, as an account nothing points at.
        """
        sandbox = await make_sandbox(role="manager")
        request = (
            await db_session.execute(
                select(EventJoinRequest).where(
                    col(EventJoinRequest.event_id) == sandbox.event.id
                )
            )
        ).scalar_one()

        membership = (
            await db_session.execute(
                select(EventMembership).where(
                    col(EventMembership.user_id) == request.user_id,
                    col(EventMembership.event_id) == sandbox.event.id,
                )
            )
        ).scalar_one_or_none()

        assert membership is not None


# ── Nothing in here may be contactable ────────────────────────────


@pytest.mark.asyncio
class TestSeededAccounts:
    """No account the seeder creates may be reachable by mail, or signed into."""

    async def test_no_seeded_account_has_an_email_address(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that every guest is unmailable by construction.

        Not laziness and not an oversight: ``send_verify_email`` and
        ``request_password_reset`` both short-circuit on a missing address, so
        a NULL here means even a future code path that forgets the ``sandbox|``
        prefix check cannot put anything in anyone's inbox.
        """
        guests = await _guests(db_session, test_sandbox)

        assert guests
        assert all(guest.email is None for guest in guests)
        assert all(guest.is_sandbox for guest in guests)
        assert all(guest.subject.startswith("sandbox|") for guest in guests)

    async def test_no_seeded_account_can_be_signed_into(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that ``password_hash`` is NULL on every guest.

        ``verify_password`` folds a NULL hash to a failed comparison, so these
        accounts can only ever be handed out by ``POST /auth/sandbox`` — never
        logged into, and never recovered into by anyone who learns an id.
        """
        guests = await _guests(db_session, test_sandbox)

        assert all(guest.password_hash is None for guest in guests)

    async def test_no_seeded_account_holds_a_platform_role(
        self, db_session: AsyncSession, test_sandbox: SandboxSetup
    ) -> None:
        """Test that a demo cannot mint an administrator.

        ``roles`` is the one remaining platform-wide grant. An anonymous
        visitor being able to cause an ``admin`` row to exist would make this
        endpoint a privilege-escalation path rather than a demo.
        """
        guests = await _guests(db_session, test_sandbox)

        assert all(guest.roles == [] for guest in guests)
        assert all(not guest.is_admin for guest in guests)

    async def test_the_guest_is_named_in_the_language_they_clicked(
        self, make_sandbox: SandboxFactory
    ) -> None:
        """Test that the visitor appears on the staffing board under a real name.

        ``guest_display_name`` exists because the account is minted before the
        event does, and a guest showing up as ``None`` on every shift they hold
        undoes the illusion the demo is built on.
        """
        assert guest_display_name("en") == "Demo visitor"
        assert guest_display_name("de") == "Demo-Gast"
        assert guest_display_name("fr") == "Demo visitor", "unknown falls back to en"

        german = await make_sandbox(language="de")
        assert german.guest.name == "Demo-Gast"
        assert german.guest.preferred_language == "de"

    async def test_two_demos_are_shaped_differently(
        self, db_session: AsyncSession, make_sandbox: SandboxFactory
    ) -> None:
        """Test that the rota is seeded from the guest's id, not from a constant.

        Two visitors clicking the button in the same second should not get
        byte-identical rotas — and the same visitor reloading should not see
        theirs reshuffle, which is why the seed is the account id rather than
        the clock.

        Compared as the whole fill pattern rather than as a total: two totals
        can coincide by chance often enough to make this test flap, while two
        fifty-odd-shift patterns coinciding would mean the generator had
        stopped depending on its seed.
        """
        first = await make_sandbox()
        second = await make_sandbox()

        async def _fill_pattern(sandbox: SandboxSetup) -> tuple[int, ...]:
            shifts = sorted(
                await _shifts(db_session, sandbox),
                key=lambda s: (s.title or "", s.date, s.start_time),
            )
            rows = await db_session.execute(
                select(col(Booking.shift_id)).where(
                    col(Booking.shift_id).in_([shift.id for shift in shifts])
                )
            )
            taken: dict[uuid.UUID | None, int] = {}
            for shift_id in rows.scalars():
                taken[shift_id] = taken.get(shift_id, 0) + 1
            return tuple(taken.get(shift.id, 0) for shift in shifts)

        first_pattern = await _fill_pattern(first)
        second_pattern = await _fill_pattern(second)

        assert len(first_pattern) == len(second_pattern) > 0
        assert first_pattern != second_pattern
