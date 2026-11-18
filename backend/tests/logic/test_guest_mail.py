"""Mail to guests: the templates, and member notices turned into guest mail.

The notices run as they do in production, through the trigger or the reminder
poller and ``NotificationService.notify``; only the SMTP transport is replaced
(``send_action_mail``'s ``_smtp_send``), so every assertion reads the message
that would have gone out. The modules that open sessions of their own get the
test's session (``SessionsStub``).
"""

import datetime as dt
import logging
import uuid
from collections.abc import Generator
from email.message import EmailMessage
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.crud.booking import booking as crud_booking
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.crud.shared_list_guest import GUEST_SUBJECT_PREFIX
from app.logic import clock
from app.logic.notifications import reminder_poller, triggers
from app.logic.notifications.channels.base import UNDELIVERABLE_SUBJECT_PREFIXES
from app.logic.notifications.service import NotificationService
from app.logic.shared_lists import guest_mail, guest_tokens
from app.logic.shared_lists.guest_mail import (
    _STRINGS,  # pyright: ignore[reportPrivateUsage]
    GUEST_REMINDER,
    GuestMail,
    GuestShift,
    render,
)
from app.models.booking import Booking
from app.models.event import Event
from app.models.notification import Notification
from app.models.shared_list import GuestActivityLog, SharedList
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.notification import NotificationData
from tests.fixtures.guest_signups import (
    add_shift,
    configure_smtp,
    confirm_address,
    disable_smtp,
    freeze_clocks,
)
from tests.fixtures.shared_lists import ListGuest, ListGuestFactory, SharedListFactory
from tests.fixtures.storage import SessionsStub

TRANSPORT = "app.logic.auth.emails._smtp_send"

SHIFT = GuestShift(
    task_name="Bar <b>&",
    date=dt.date(2026, 6, 11),
    start_time=dt.time(10, 0),
    end_time=dt.time(12, 0),
    location="Foyer",
)


def _mail(**fields: Any) -> GuestMail:
    values: dict[str, Any] = {
        "kind": "confirmation",
        "to": "guest@example.org",
        "language": "de",
        "name": "Anna",
        "event_name": "Sommerfest <script>",
        "zone": "Europe/Berlin",
        "shifts": (SHIFT,),
        "token": "abc.def",
        "not_me": "suppresses",
    }
    values.update(fields)
    return GuestMail(**values)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_clocks(monkeypatch)
    configure_smtp(monkeypatch)
    monkeypatch.setattr(settings, "FRONTEND_HOST", "https://app.example.test")


@pytest.fixture
def smtp() -> Generator[AsyncMock]:
    with patch(TRANSPORT, new_callable=AsyncMock) as transport:
        yield transport


@pytest.fixture
def sessions(db_session: AsyncSession) -> Generator[None]:
    """Every session the notice path opens is the test's."""
    stub = SessionsStub(db_session)
    with (
        patch.object(guest_mail, "async_session", stub),
        patch.object(triggers, "async_session", stub),
        patch.object(reminder_poller, "async_session", stub),
    ):
        yield


def _sent(smtp: AsyncMock) -> list[EmailMessage]:
    return [cast(EmailMessage, call.args[0]) for call in smtp.await_args_list]


def _text(message: EmailMessage) -> str:
    part = message.get_body(preferencelist=("plain",))
    assert part is not None
    return str(part.get_content())


def _html(message: EmailMessage) -> str:
    part = message.get_body(preferencelist=("html",))
    assert part is not None
    return str(part.get_content())


# ── Templates ─────────────────────────────────────────────────────


class TestTemplates:
    def test_both_languages_say_the_same_things(self) -> None:
        assert set(_STRINGS["en"]) == set(_STRINGS["de"])

    @pytest.mark.parametrize("language", ["en", "de"])
    @pytest.mark.parametrize(
        "kind", ["confirmation", "reminder", "moved", "cancelled", "removed"]
    )
    def test_every_mail_renders_with_its_link(self, language: str, kind: Any) -> None:
        rendered = render(_mail(kind=kind, language=language))
        link = "https://app.example.test/guest-signup#abc.def"
        assert rendered.action_url == link
        assert link in rendered.text
        assert "Sommerfest <script>" in rendered.text
        assert "Bar <b>&" in rendered.text
        assert "Foyer" in rendered.text
        assert "10:00–12:00" in rendered.text
        not_me = "Das war ich nicht" if language == "de" else "That wasn't me"
        assert not_me in rendered.text
        # Escaped in HTML, never markup.
        assert "<script>" not in rendered.html
        assert "<b>&" not in rendered.html
        assert "Sommerfest &lt;script&gt;" in rendered.html
        assert f'lang="{language}"' in rendered.html

    def test_a_mail_about_several_shifts_lists_them(self) -> None:
        later = GuestShift(
            task_name="Grill",
            date=dt.date(2026, 6, 12),
            start_time=None,
            end_time=None,
            location=None,
        )
        rendered = render(_mail(kind="cancelled", language="en", shifts=(SHIFT, later)))
        assert rendered.title == "2 shifts cancelled"
        assert "Thu 11 June · 10:00–12:00: Bar <b>&" in rendered.text
        assert "Fri 12 June: Grill" in rendered.text

    def test_the_german_confirmation(self) -> None:
        rendered = render(_mail())
        assert rendered.title == "Du bist eingetragen: Bar <b>&"
        assert rendered.text.startswith("Hallo Anna,")
        assert "Do, 11. Juni · 10:00–12:00" in rendered.text

    def test_another_zone_is_named(self) -> None:
        rendered = render(_mail(zone="America/New_York"))
        assert "10:00–12:00 (America/New_York)" in rendered.text

    async def test_sending_goes_through_the_transactional_path(
        self, smtp: AsyncMock
    ) -> None:
        assert await guest_mail.send_guest_mail(_mail(language="en")) is True
        [message] = _sent(smtp)
        assert message["To"] == "guest@example.org"
        assert message["Subject"] == "You're signed up: Bar <b>&"

    def test_no_channel_contacts_a_guest(self) -> None:
        assert GUEST_SUBJECT_PREFIX in UNDELIVERABLE_SUBJECT_PREFIXES


# ── Notices ───────────────────────────────────────────────────────


async def _guest(
    make_list_guest: ListGuestFactory,
    shared_list: SharedList,
    shifts: list[Shift],
    *,
    email: str | None = "guest@example.org",
) -> ListGuest:
    return await make_list_guest(
        shared_list, name="Gast Eins", email=email, language="en", shifts=shifts
    )


async def _read_afresh(db: AsyncSession, signed: ListGuest) -> None:
    """Read the bookings as the trigger's own session will, after the commit.

    ``Shift.bookings`` deletes passively, so the database has set their
    ``shift_id`` to NULL while the objects in this session still hold it.
    """
    for booking in signed.bookings:
        await db.refresh(booking)


async def _notifications(db: AsyncSession, user: User) -> int:
    return (
        await db.scalar(
            select(func.count()).where(col(Notification.recipient_id) == user.id)
        )
    ) or 0


async def _log_rows(db: AsyncSession, kind: str) -> int:
    return (
        await db.scalar(select(func.count()).where(col(GuestActivityLog.kind) == kind))
    ) or 0


async def _remove_shifts(
    db: AsyncSession,
    signed: ListGuest,
    shifts: list[Shift],
    task: Task,
    event: Event,
    actor: User,
) -> None:
    """Delete ``shifts`` of ``task`` as the shift and task routes do, and run
    the notice they queue."""
    cancelled = await crud_booking.cancel_bookings_for_shifts(
        db, slot_ids=[s.id for s in shifts], task_name=task.name
    )
    for shift in shifts:
        await db.delete(shift)
    await db.flush()
    await _read_afresh(db, signed)
    await triggers.dispatch_booking_cancelled_by_admin(
        cancelled=cancelled,
        actor_id=actor.id,
        task_id=task.id,
        task_name=task.name,
        task_is_open=False,
        now=clock.wall_clock_now(event.timezone),
        event_id=event.id,
    )


@pytest.mark.usefixtures("sessions")
class TestServiceBranch:
    async def test_a_guest_gets_the_notice_as_data_never_as_text(
        self,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_user: User,
    ) -> None:
        shift = await add_shift(db_session, test_task)
        signed = await _guest(make_list_guest, test_shared_list, [shift])
        calls: list[dict[str, Any]] = []

        async def _record(_db: AsyncSession, **kwargs: Any) -> None:
            calls.append(kwargs)

        data: dict[str, str | int | None] = {"booking_id": str(signed.bookings[0].id)}
        scope_chain = [("task", shift.task_id)]
        with patch.object(guest_mail, "deliver_notice", _record):
            await NotificationService(db_session).notify(
                recipient_ids=[signed.user.id],
                type_code="booking.cancelled_by_admin",
                title="Gestrichen. Grund: <script>X",
                body="Siehe Meine Buchungen",
                data=data,
                scope_chain=scope_chain,
            )

        assert calls == [
            {
                "recipient": signed.user,
                "type_code": "booking.cancelled_by_admin",
                "data": data,
                "scope_chain": scope_chain,
            }
        ]
        assert await _notifications(db_session, signed.user) == 0

    async def test_other_notices_reach_a_guest_not_at_all(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
    ) -> None:
        shift = await add_shift(db_session, test_task)
        signed = await _guest(make_list_guest, test_shared_list, [shift])
        await NotificationService(db_session).notify(
            recipient_ids=[signed.user.id],
            type_code="booking.shift_cobooked",
            title="Someone booked too",
            data={"slot_id": str(shift.id)},
        )
        assert smtp.await_count == 0
        assert await _notifications(db_session, signed.user) == 0
        assert (
            await db_session.scalar(select(func.count(col(GuestActivityLog.id))))
        ) == 0


@pytest.mark.usefixtures("sessions")
class TestCancelledByAdmin:
    async def test_a_removed_shift_names_no_reason(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_event: Event,
        test_event_admin_user: User,
    ) -> None:
        shift = await add_shift(db_session, test_task)
        signed = await _guest(make_list_guest, test_shared_list, [shift])
        cancelled = await crud_booking.cancel_bookings_for_shifts(
            db_session,
            slot_ids=[shift.id],
            task_name=test_task.name,
            cancellation_reason="<script>X",
        )
        await db_session.delete(shift)
        await db_session.flush()
        await _read_afresh(db_session, signed)

        await triggers.dispatch_booking_cancelled_by_admin(
            cancelled=cancelled,
            actor_id=test_event_admin_user.id,
            task_id=test_task.id,
            task_name=test_task.name,
            task_is_open=True,
            now=clock.wall_clock_now(test_event.timezone),
            event_id=test_event.id,
            reason="<script>X",
        )

        [message] = _sent(smtp)
        assert message["To"] == "guest@example.org"
        assert message["Subject"] == f"Cancelled: {test_task.name}"
        # Neither the reason nor any escaped form of it.
        for part in (_text(message), _html(message)):
            assert "script" not in part
            assert "My Bookings" not in part
            assert "Meine Buchungen" not in part
        assert test_event.name in _text(message)
        assert guest_tokens.manage_url(guest_tokens.mail_token(signed.guest)) in _text(
            message
        )
        assert guest_tokens.manage_token(signed.guest) not in _text(message)

    async def test_one_mail_names_every_shift_the_action_took(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_event: Event,
        test_event_admin_user: User,
    ) -> None:
        shifts = [
            await add_shift(db_session, test_task, day=dt.date(2026, 6, day))
            for day in (11, 12, 13)
        ]
        signed = await _guest(make_list_guest, test_shared_list, shifts)

        await _remove_shifts(
            db_session, signed, shifts, test_task, test_event, test_event_admin_user
        )

        [message] = _sent(smtp)
        assert message["Subject"] == "3 shifts cancelled"
        text = _text(message)
        for day in ("11 June", "12 June", "13 June"):
            assert day in text
        # One mail is one row, so the ceilings count it once.
        assert await _log_rows(db_session, "cancelled") == 1

    async def test_a_shift_already_over_is_not_named(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_event: Event,
        test_event_admin_user: User,
    ) -> None:
        """Removed together with one still ahead: the one that ended earlier
        today was worked, not cancelled. It is 08:00 in Berlin."""
        worked = await add_shift(
            db_session,
            test_task,
            day=dt.date(2026, 6, 1),
            start=dt.time(6, 0),
            end=dt.time(7, 0),
        )
        ahead = await add_shift(db_session, test_task)
        signed = await _guest(make_list_guest, test_shared_list, [worked, ahead])

        await _remove_shifts(
            db_session,
            signed,
            [worked, ahead],
            test_task,
            test_event,
            test_event_admin_user,
        )

        [message] = _sent(smtp)
        assert message["Subject"] == f"Cancelled: {test_task.name}"
        assert "Thu 11 June" in _text(message)
        assert "Mon 1 June" not in _text(message)

    async def test_a_pruned_log_names_no_shift_again(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_event: Event,
        test_event_admin_user: User,
    ) -> None:
        """Each mail names the bookings of its own action, never what an
        earlier one named, even once the log of it has been pruned."""
        first = await add_shift(db_session, test_task, day=dt.date(2026, 6, 11))
        later = await add_shift(db_session, test_task, day=dt.date(2026, 6, 13))
        signed = await _guest(make_list_guest, test_shared_list, [first, later])

        await _remove_shifts(
            db_session, signed, [first], test_task, test_event, test_event_admin_user
        )
        await db_session.execute(delete(GuestActivityLog))
        await _remove_shifts(
            db_session, signed, [later], test_task, test_event, test_event_admin_user
        )

        [one, two] = _sent(smtp)
        assert one["Subject"] == two["Subject"] == f"Cancelled: {test_task.name}"
        assert "11 June" in _text(one)
        assert "13 June" not in _text(one)
        assert "13 June" in _text(two)
        assert "11 June" not in _text(two)

    async def test_a_task_moved_away_names_the_event_it_moved_to(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_event: Event,
        test_private_event: Event,
        test_event_admin_user: User,
    ) -> None:
        """Its bookings went with it, and so does every mail about them: the
        name and the ceilings are the new event's."""
        shift = await add_shift(db_session, test_task)
        signed = await _guest(make_list_guest, test_shared_list, [shift])
        test_task.event_id = test_private_event.id
        db_session.add(test_task)
        await db_session.flush()

        await _remove_shifts(
            db_session,
            signed,
            [shift],
            test_task,
            test_private_event,
            test_event_admin_user,
        )

        [message] = _sent(smtp)
        assert test_private_event.name in _text(message)
        assert test_event.name not in _text(message)
        [event_id] = (
            await db_session.execute(
                select(col(GuestActivityLog.event_id)).where(
                    col(GuestActivityLog.kind) == "cancelled"
                )
            )
        ).scalars()
        assert event_id == test_private_event.id

    async def test_a_task_without_an_event_names_the_guests_own(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_event: Event,
        test_admin_user: User,
    ) -> None:
        """A task whose event was deleted after it moved there has no event
        to name; the one of the guest's list is the one they know."""
        shift = await add_shift(db_session, test_task)
        signed = await _guest(make_list_guest, test_shared_list, [shift])
        cancelled = await crud_booking.cancel_bookings_for_shifts(
            db_session, slot_ids=[shift.id], task_name=test_task.name
        )
        await db_session.delete(shift)
        await db_session.flush()
        await _read_afresh(db_session, signed)

        await triggers.dispatch_booking_cancelled_by_admin(
            cancelled=cancelled,
            actor_id=test_admin_user.id,
            task_id=test_task.id,
            task_name=test_task.name,
            task_is_open=False,
            now=clock.wall_clock_now(),
            event_id=None,
        )

        [message] = _sent(smtp)
        assert test_event.name in _text(message)


@pytest.mark.usefixtures("sessions")
class TestMovedAndReminder:
    async def test_a_moved_shift_shows_the_new_time(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_event: Event,
    ) -> None:
        shift = await add_shift(db_session, test_task)
        signed = await _guest(make_list_guest, test_shared_list, [shift])
        shift.start_time = dt.time(15, 30)
        shift.end_time = dt.time(17, 0)
        db_session.add(shift)
        await db_session.flush()

        await triggers.dispatch_shift_time_changed(
            slot_id=shift.id,
            slot_title=shift.title,
            task_id=test_task.id,
            event_id=test_event.id,
            booked_user_ids=[signed.user.id],
        )

        [message] = _sent(smtp)
        assert message["Subject"] == f"New time: {test_task.name}"
        assert "15:30–17:00" in _text(message)
        assert "10:00" not in _text(message)

    async def test_the_reminder_poller_reminds_by_mail(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_event: Event,
    ) -> None:
        shift = await add_shift(db_session, test_task)
        signed = await _guest(make_list_guest, test_shared_list, [shift])
        [reminder] = await crud_reminder.replace_for_booking(
            db_session,
            booking_id=signed.bookings[0].id,
            user_id=signed.user.id,
            shift_id=shift.id,
            entries=[GUEST_REMINDER],
            slot_start=dt.datetime(2026, 6, 11, 10, 0),
            zone=test_event.timezone,
        )

        await reminder_poller._process_reminder(reminder)  # pyright: ignore[reportPrivateUsage]

        [message] = _sent(smtp)
        assert message["Subject"] == f"Reminder: {test_task.name}"
        assert "Thu 11 June · 10:00–12:00" in _text(message)
        await db_session.refresh(reminder)
        assert reminder.status == "sent"
        assert await _notifications(db_session, signed.user) == 0
        kinds = (
            (await db_session.execute(select(col(GuestActivityLog.kind))))
            .scalars()
            .all()
        )
        assert kinds == ["reminder"]

    async def test_no_address_no_mail(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
    ) -> None:
        shift = await add_shift(db_session, test_task)
        signed = await _guest(make_list_guest, test_shared_list, [shift], email=None)
        await guest_mail.deliver_notice(
            db_session,
            recipient=signed.user,
            type_code="booking.reminder",
            data={"booking_id": str(signed.bookings[0].id)},
            scope_chain=None,
        )
        assert smtp.await_count == 0


@pytest.mark.usefixtures("sessions")
class TestFences:
    async def test_over_the_address_ceiling_nothing_more_goes_out(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
    ) -> None:
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(settings, "GUEST_MAILS_PER_ADDRESS_PER_DAY", 2)
        shift = await add_shift(db_session, test_task)
        signed = await _guest(make_list_guest, test_shared_list, [shift])
        reminder: NotificationData = {"booking_id": str(signed.bookings[0].id)}
        moved: NotificationData = {"slot_id": str(shift.id)}
        with caplog.at_level(logging.INFO):
            for type_code, data in (
                ("booking.reminder", reminder),
                ("shift.time_changed", moved),
                ("booking.reminder", reminder),
                ("shift.time_changed", moved),
            ):
                await guest_mail.deliver_notice(
                    db_session,
                    recipient=signed.user,
                    type_code=type_code,
                    data=data,
                    scope_chain=None,
                )
        assert smtp.await_count == 2
        refusals = [
            record.getMessage()
            for record in caplog.records
            if "over the daily" in record.getMessage()
        ]
        assert len(refusals) == 2
        for line in refusals:
            assert "address ceiling" in line
            assert "guest@example.org" not in line

    async def test_without_smtp_the_link_reaches_no_log(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
    ) -> None:
        disable_smtp(monkeypatch)
        shift = await add_shift(db_session, test_task)
        signed = await _guest(make_list_guest, test_shared_list, [shift])
        token = guest_tokens.mail_token(signed.guest)
        with caplog.at_level(logging.DEBUG):
            await guest_mail.deliver_notice(
                db_session,
                recipient=signed.user,
                type_code="booking.reminder",
                data={"booking_id": str(signed.bookings[0].id)},
                scope_chain=None,
            )
            await guest_mail.send_guest_mail(_mail(token=token))
        assert smtp.await_count == 0
        assert token not in caplog.text
        assert token.partition(".")[2] not in caplog.text

    async def test_a_mail_about_many_shifts_counts_once(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_event: Event,
        test_event_admin_user: User,
    ) -> None:
        """The address ceiling counts mails: one cancellation naming three
        shifts leaves room for the reminder of the fourth."""
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(settings, "GUEST_MAILS_PER_ADDRESS_PER_DAY", 2)
        removed = [
            await add_shift(db_session, test_task, day=dt.date(2026, 6, day))
            for day in (11, 12, 13)
        ]
        kept = await add_shift(db_session, test_task, day=dt.date(2026, 6, 14))
        signed = await _guest(make_list_guest, test_shared_list, [*removed, kept])
        reminder: NotificationData = {"booking_id": str(signed.bookings[-1].id)}

        await _remove_shifts(
            db_session, signed, removed, test_task, test_event, test_event_admin_user
        )
        for _ in range(2):
            await guest_mail.deliver_notice(
                db_session,
                recipient=signed.user,
                type_code="booking.reminder",
                data=reminder,
                scope_chain=None,
            )

        assert [m["Subject"] for m in _sent(smtp)] == [
            "3 shifts cancelled",
            f"Reminder: {test_task.name}",
        ]

    async def test_a_notice_that_does_not_fit_the_guest_is_dropped(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_booking: Booking,
    ) -> None:
        shift = await add_shift(db_session, test_task)
        signed = await _guest(make_list_guest, test_shared_list, [shift])
        notices: list[tuple[str, NotificationData]] = [
            # Someone else's booking, a booking still on, no id, no booking.
            ("booking.reminder", {"booking_id": str(test_booking.id)}),
            ("booking.cancelled_by_admin", {"booking_ids": str(test_booking.id)}),
            (
                "booking.cancelled_by_admin",
                {"booking_ids": str(signed.bookings[0].id)},
            ),
            ("booking.cancelled_by_admin", {"booking_ids": "not-an-id"}),
            ("booking.cancelled_by_admin", {"booking_id": str(signed.bookings[0].id)}),
            ("booking.reminder", {"booking_id": "not-an-id"}),
            ("shift.time_changed", {"slot_id": str(uuid.uuid4())}),
        ]
        for type_code, data in notices:
            await guest_mail.deliver_notice(
                db_session,
                recipient=signed.user,
                type_code=type_code,
                data=data,
                scope_chain=None,
            )
        assert smtp.await_count == 0


async def test_an_erased_guest_gets_nothing(
    db_session: AsyncSession,
    smtp: AsyncMock,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_task: Task,
) -> None:
    shift = await add_shift(db_session, test_task)
    signed = await _guest(make_list_guest, test_shared_list, [shift])
    signed.guest.email = None
    signed.guest.manage_nonce = None
    db_session.add(signed.guest)
    await db_session.flush()
    await guest_mail.deliver_notice(
        db_session,
        recipient=signed.user,
        type_code="booking.reminder",
        data={"booking_id": str(signed.bookings[0].id)},
        scope_chain=None,
    )
    assert smtp.await_count == 0


# ── Vouchers, confirming and the retention period ────────────────


EARNING = GuestShift(
    task_name="Theke",
    date=dt.date(2026, 6, 11),
    start_time=dt.time(10, 0),
    end_time=dt.time(12, 0),
    location=None,
    vouchers=2,
)

#: Per language: the voucher line, how to redeem, how to confirm, the two
#: retention lines, and what expires.
SAYS = {
    "en": (
        "This shift earns 2 vouchers once it is over.",
        "tap “Show code”",
        "confirm that this is your address",
        "We delete your name and email address 30 days after your last shift.",
        "We delete your name, email address and phone number 30 days",
        "Vouchers you have not redeemed by then expire.",
    ),
    "de": (
        "Für diese Schicht bekommst du 2 Marken, sobald sie vorbei ist.",
        "tipp auf „Code zeigen“",
        "bestätigen, dass das deine Adresse ist",
        "Wir löschen deinen Namen und deine E-Mail-Adresse 30 Tage nach deiner "
        "letzten Schicht.",
        "Wir löschen deinen Namen, deine E-Mail-Adresse und deine Telefonnummer "
        "30 Tage",
        "Marken, die du bis dahin nicht eingelöst hast, verfallen dann.",
    ),
}


#: Per language: what confirming does to the vouchers, said only in a mail
#: about a shift that earns some.
POOLED = {
    "en": "and your vouchers are added up",
    "de": "und deine Marken werden zusammengezählt",
}


@pytest.mark.parametrize("language", ["en", "de"])
class TestVouchersAndRetention:
    def test_the_confirmation_of_a_voucher_shift(self, language: str) -> None:
        vouchers, redeem, confirm, retention, _, expire = SAYS[language]
        rendered = render(
            _mail(
                language=language,
                shifts=(EARNING,),
                retention_days=30,
                event_name="Sommerfest",
            )
        )
        pooled = POOLED[language]
        for said in (vouchers, redeem, confirm, pooled, retention, expire):
            assert said in rendered.text
        assert "Sommerfest" in rendered.text
        assert vouchers in rendered.html
        # The steps come in the order a guest takes them: what it earns and
        # how to redeem, then confirming, then how long the data is kept.
        text = rendered.text
        assert text.index(vouchers) < text.index(confirm) < text.index(retention)

    def test_the_confirmation_of_a_shift_without_vouchers(self, language: str) -> None:
        vouchers, redeem, confirm, retention, _, expire = SAYS[language]
        rendered = render(_mail(language=language, retention_days=30))
        assert confirm in rendered.text
        assert retention in rendered.text
        for unsaid in (vouchers, redeem, expire, POOLED[language]):
            assert unsaid not in rendered.text
            assert unsaid not in rendered.html

    def test_the_retention_line_names_a_stored_phone(self, language: str) -> None:
        _, _, _, without, with_phone, _ = SAYS[language]
        rendered = render(_mail(language=language, retention_days=30, has_phone=True))
        assert with_phone in rendered.text
        assert without not in rendered.text

    def test_the_period_is_the_one_passed_in(self, language: str) -> None:
        rendered = render(_mail(language=language, retention_days=14))
        assert (" 14 days " if language == "en" else " 14 Tage ") in rendered.text
        assert " 30 " not in rendered.text

    def test_the_reminder_says_what_the_shift_earns(self, language: str) -> None:
        vouchers, redeem, confirm, *_ = SAYS[language]
        rendered = render(_mail(kind="reminder", language=language, shifts=(EARNING,)))
        assert vouchers in rendered.text
        assert redeem in rendered.text
        assert confirm not in rendered.text

    @pytest.mark.parametrize(
        "kind", ["confirmation", "reminder", "moved", "cancelled", "removed"]
    )
    def test_every_mail_says_the_link_is_private(
        self, language: str, kind: Any
    ) -> None:
        plain = _STRINGS[language]["link_private"]
        with_vouchers = _STRINGS[language]["link_private_vouchers"]
        without = render(_mail(kind=kind, language=language))
        earning = render(_mail(kind=kind, language=language, shifts=(EARNING,)))
        assert plain in without.text and with_vouchers not in without.text
        assert with_vouchers in earning.text
        assert with_vouchers in earning.html

    def test_the_not_me_line_says_what_the_page_will_do(self, language: str) -> None:
        """Never "we never write to this address again" where the page will
        not stop the mail, and no line at all where it offers no choice."""
        strings = _STRINGS[language]
        name = "Das war ich nicht" if language == "de" else "That wasn't me"
        suppresses = render(_mail(language=language, not_me="suppresses"))
        erases = render(_mail(language=language, not_me="erases"))
        account = render(_mail(kind="reminder", language=language, not_me=None))

        assert strings["not_me_suppresses"] in suppresses.text
        assert strings["not_me_erases"] in erases.text
        assert strings["not_me_suppresses"] not in erases.text
        for part in (account.text, account.html):
            assert name not in part
            assert strings["link_private"] in part


class TestNotMeOffer:
    async def test_by_what_the_address_has(
        self,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        make_shared_list: SharedListFactory,
        test_draft_event: Event,
    ) -> None:
        """The rule of the manage page's ``reject_suppresses``: an account
        anywhere keeps the address mailable, and an account itself offers
        nothing."""
        alone = await make_list_guest(test_shared_list, email="alone@example.org")
        account = await make_list_guest(
            await make_shared_list(event=test_draft_event, tasks=[]),
            email="fam@example.org",
        )
        await confirm_address(db_session, account.guest)
        beside = await make_list_guest(test_shared_list, email="fam@example.org")

        offers = [
            await guest_mail.not_me_offer(db_session, signed.guest)
            for signed in (alone, beside, account)
        ]

        assert offers == ["suppresses", "erases", None]


def test_a_mail_about_several_sign_ups_greets_their_one_name() -> None:
    assert guest_mail.greeting_name(["Tom", "Tom"]) == "Tom"
    assert guest_mail.greeting_name(["Tom", "Maria"]) is None
    assert guest_mail.greeting_name([None]) is None


@pytest.mark.usefixtures("sessions")
class TestPooledBookings:
    async def test_a_reminder_greets_the_sign_ups_own_name(
        self,
        db_session: AsyncSession,
        smtp: AsyncMock,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_event: Event,
    ) -> None:
        """Tom's shift, pooled into Maria's account, greets Tom."""
        test_task.vouchers_per_shift = 2
        db_session.add(test_task)
        maria = await make_list_guest(
            test_shared_list, name="Maria", email="fam@example.org", language="en"
        )
        tom = await make_list_guest(
            test_shared_list,
            name="Tom",
            email="fam@example.org",
            shifts=[await add_shift(db_session, test_task)],
        )
        await confirm_address(db_session, maria.guest)
        await confirm_address(db_session, tom.guest)
        [reminder] = await crud_reminder.replace_for_booking(
            db_session,
            booking_id=tom.bookings[0].id,
            user_id=maria.user.id,
            shift_id=tom.bookings[0].shift_id,  # type: ignore[arg-type]
            entries=[GUEST_REMINDER],
            slot_start=dt.datetime(2026, 6, 11, 10, 0),
            zone=test_event.timezone,
        )

        await reminder_poller._process_reminder(reminder)  # pyright: ignore[reportPrivateUsage]

        [message] = _sent(smtp)
        text = _text(message)
        assert text.startswith("Hello Tom,")
        # An account's page offers no "That wasn't me", so its mail does not.
        assert "That wasn't me" not in text
        assert "This shift earns 2 vouchers once it is over." in text
        assert guest_tokens.manage_url(guest_tokens.mail_token(maria.guest)) in text
