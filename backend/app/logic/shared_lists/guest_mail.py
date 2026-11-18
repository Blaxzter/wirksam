"""Mail to people who signed up through a shared list.

A guest has no account, no settings and no inbox in the app, only the address
they typed. They get five mails, each with their manage link (the mail's
own, ``guest_tokens.mail_token``, the only one that may say "Das war ich
nicht"):

=================  ==================================================  =========
Mail               When                                                Log kind
=================  ==================================================  =========
confirmation       the first sign-up of a chain with an address        confirmation
reminder           a day before, if they asked for it                  reminder
moved              an organiser moved their shift                      moved
cancelled          an organiser removed their shift                    cancelled
removed            an organiser took them off (``removal.py``)         removed
=================  ==================================================  =========

The middle three are member notices too. ``NotificationService.notify`` hands
a guest's to :func:`deliver_notice` before it resolves a title or a body, and
writes nothing else for them: no in-app row, no push. The member texts carry
organiser free text (a cancellation's "Reason: …", which people in charge can
type too) and point to My Bookings, which a guest does not have.

So every mail here is written from database rows only: the event's and the
task's name, the date, the times and the place, and the vouchers a shift
earns. No list title or intro, no cancellation reason, nothing from
``logic/notifications/locales``. Everything interpolated is escaped. The texts
are their own, in English and German, in the guest's ``preferred_language``.
A mail about bookings greets the name of those sign-ups (``bookings.
guest_name``): a guest account pools sign-ups of several people.

Every mail says that whoever holds its link can change the sign-ups, and
redeem the vouchers when a shift in it earns some: the link is the only key
a guest has. Its line on "Das war ich nicht" says what the page will do
(:func:`not_me_offer`): a mail to a guest account has none, since its owner
confirmed those sign-ups, and one to an address that has an account only
promises to delete the sign-up. The confirmation also says how to redeem, how to confirm the
address, and how long the data is kept.

Before it goes out, every mail is reserved in ``guest_quota.reserve_mail``,
which refuses an address that opted out, one over a daily ceiling, every
mail about a demo event, and everything when SMTP is not configured: the
transactional mail path would log the link instead, and a manage link must
never reach a log.
"""

import datetime as dt
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.core.db import async_session
from app.core.logger import get_logger
from app.crud.shared_list_guest import shared_list_guest as crud_guest
from app.logic.auth.emails import send_action_mail
from app.logic.notifications.channels.email import (
    button_html,
    card_html,
    details_table_html,
    link_fallback_html,
    paragraphs_html,
    small_print_html,
)
from app.logic.notifications.messages import day_span, shift_times
from app.logic.shared_lists import guest_quota, guest_tokens
from app.models.booking import Booking
from app.models.event import Event
from app.models.shared_list import GuestMailKind, SharedListGuest
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.booking_reminder import ReminderOffsetEntry
from app.schemas.notification import NotificationData

logger = get_logger(__name__)

#: The member notices a guest gets, as mail written here. Every other notice
#: (co-booked, task published, …) is dropped for guests.
GUEST_MAIL_TYPES: Final = frozenset(
    {"booking.reminder", "booking.cancelled_by_admin", "shift.time_changed"}
)

#: The one reminder a guest can have: by mail, a day before the shift. The
#: reminder poller fires it as for anyone, and :func:`deliver_notice` writes it.
GUEST_REMINDER: Final = ReminderOffsetEntry(offset_minutes=1440, channels=["email"])

_LANGUAGES = ("en", "de")

#: What "Das war ich nicht" does for the guest a mail goes to
#: (:func:`not_me_offer`): erase the chain and never mail the address again,
#: or only erase the chain.
NotMeOffer = Literal["suppresses", "erases"]

_STRINGS: Final[dict[str, dict[str, str]]] = {
    "en": {
        "greeting": "Hello {name},",
        "greeting_no_name": "Hello,",
        "title_confirmation": "You're signed up: {task}",
        "intro_confirmation": "You signed up for this shift at “{event}”.",
        "title_reminder": "Reminder: {task}",
        "intro_reminder": "Your shift at “{event}” is coming up.",
        "title_moved": "New time: {task}",
        "intro_moved": (
            "The organisers of “{event}” moved your shift. This is the new time."
        ),
        "title_cancelled_one": "Cancelled: {task}",
        "title_cancelled_other": "{count} shifts cancelled",
        "intro_cancelled_one": (
            "The organisers of “{event}” removed this shift, so you are no "
            "longer signed up for it."
        ),
        "intro_cancelled_other": (
            "The organisers of “{event}” removed these shifts, so you are no "
            "longer signed up for them."
        ),
        "title_removed_one": "Taken off: {task}",
        "title_removed_other": "Taken off {count} shifts",
        "intro_removed_one": "The organisers of “{event}” took you off this shift.",
        "intro_removed_other": (
            "The organisers of “{event}” took you off these shifts."
        ),
        "detail_task": "Task",
        "detail_when": "When",
        "detail_location": "Where",
        "manage": (
            "The button opens your sign-ups. There you can take your name off a "
            "shift, switch reminders on or off, or delete your data."
        ),
        "cta": "Manage my sign-ups",
        "not_me_suppresses": (
            "Not you? Choose “That wasn't me” on the same page: we delete the "
            "sign-up and never write to this address again."
        ),
        "not_me_erases": (
            "Not you? Choose “That wasn't me” on the same page: we delete the sign-up."
        ),
        "vouchers_one": "This shift earns {count} voucher once it is over.",
        "vouchers_other": "This shift earns {count} vouchers once it is over.",
        "redeem": (
            "To redeem vouchers at a stand, open your sign-ups with the button "
            "below and tap “Show code”."
        ),
        "confirm_hint": (
            "On that page you can also confirm that this is your address. Every "
            "sign-up you confirm with it for “{event}” is then shown on one page."
        ),
        "confirm_hint_vouchers": (
            "On that page you can also confirm that this is your address. Every "
            "sign-up you confirm with it for “{event}” is then shown on one page, "
            "and your vouchers are added up."
        ),
        "retention": (
            "We delete your name and email address {days} days after your last shift."
        ),
        "retention_phone": (
            "We delete your name, email address and phone number {days} days "
            "after your last shift."
        ),
        "retention_vouchers": "Vouchers you have not redeemed by then expire.",
        "link_private": (
            "Anyone with this link can change your sign-ups, so please do not "
            "forward this mail."
        ),
        "link_private_vouchers": (
            "Anyone with this link can change your sign-ups and redeem your "
            "vouchers, so please do not forward this mail."
        ),
        "link_fallback": "If the button does not work, copy this link into your browser:",
        "footer": (
            "You get this mail because this address was entered on a sign-up "
            "list at {project}."
        ),
    },
    "de": {
        "greeting": "Hallo {name},",
        "greeting_no_name": "Hallo,",
        "title_confirmation": "Du bist eingetragen: {task}",
        "intro_confirmation": "Du hast dich bei „{event}“ für diese Schicht eingetragen.",
        "title_reminder": "Erinnerung: {task}",
        "intro_reminder": "Bald ist deine Schicht bei „{event}“.",
        "title_moved": "Neue Zeit: {task}",
        "intro_moved": (
            "Die Organisator:innen von „{event}“ haben deine Schicht verschoben. "
            "Das ist die neue Zeit."
        ),
        "title_cancelled_one": "Abgesagt: {task}",
        "title_cancelled_other": "{count} Schichten abgesagt",
        "intro_cancelled_one": (
            "Die Organisator:innen von „{event}“ haben diese Schicht gestrichen. "
            "Du bist dafür nicht mehr eingetragen."
        ),
        "intro_cancelled_other": (
            "Die Organisator:innen von „{event}“ haben diese Schichten "
            "gestrichen. Du bist dafür nicht mehr eingetragen."
        ),
        "title_removed_one": "Ausgetragen: {task}",
        "title_removed_other": "Aus {count} Schichten ausgetragen",
        "intro_removed_one": (
            "Die Organisator:innen von „{event}“ haben dich aus dieser Schicht "
            "ausgetragen."
        ),
        "intro_removed_other": (
            "Die Organisator:innen von „{event}“ haben dich aus diesen Schichten "
            "ausgetragen."
        ),
        "detail_task": "Aufgabe",
        "detail_when": "Wann",
        "detail_location": "Ort",
        "manage": (
            "Über den Button siehst du deine Eintragungen. Dort kannst du dich "
            "austragen, Erinnerungen an- oder ausschalten oder deine Daten löschen."
        ),
        "cta": "Meine Eintragungen",
        "not_me_suppresses": (
            "Warst du das nicht? Wähle auf derselben Seite „Das war ich nicht“: "
            "Dann löschen wir die Eintragung und schreiben dieser Adresse nie wieder."
        ),
        "not_me_erases": (
            "Warst du das nicht? Wähle auf derselben Seite „Das war ich nicht“: "
            "Dann löschen wir die Eintragung."
        ),
        "vouchers_one": (
            "Für diese Schicht bekommst du {count} Marke, sobald sie vorbei ist."
        ),
        "vouchers_other": (
            "Für diese Schicht bekommst du {count} Marken, sobald sie vorbei ist."
        ),
        "redeem": (
            "Einlösen kannst du Marken an den Ständen: Öffne über den Button deine "
            "Eintragungen und tipp auf „Code zeigen“."
        ),
        "confirm_hint": (
            "Dort kannst du auch bestätigen, dass das deine Adresse ist. Dann "
            "stehen alle Eintragungen, die du mit dieser Adresse bei „{event}“ "
            "bestätigst, auf einer Seite."
        ),
        "confirm_hint_vouchers": (
            "Dort kannst du auch bestätigen, dass das deine Adresse ist. Dann "
            "stehen alle Eintragungen, die du mit dieser Adresse bei „{event}“ "
            "bestätigst, auf einer Seite, und deine Marken werden zusammengezählt."
        ),
        "retention": (
            "Wir löschen deinen Namen und deine E-Mail-Adresse {days} Tage nach "
            "deiner letzten Schicht."
        ),
        "retention_phone": (
            "Wir löschen deinen Namen, deine E-Mail-Adresse und deine "
            "Telefonnummer {days} Tage nach deiner letzten Schicht."
        ),
        "retention_vouchers": (
            "Marken, die du bis dahin nicht eingelöst hast, verfallen dann."
        ),
        "link_private": (
            "Wer diesen Link hat, kann deine Eintragungen ändern. Leite die Mail "
            "deshalb nicht weiter."
        ),
        "link_private_vouchers": (
            "Wer diesen Link hat, kann deine Eintragungen ändern und deine Marken "
            "einlösen. Leite die Mail deshalb nicht weiter."
        ),
        "link_fallback": (
            "Falls der Button nicht funktioniert, kopiere diesen Link in deinen Browser:"
        ),
        "footer": (
            "Du bekommst diese Mail, weil diese Adresse in eine Eintragungsliste "
            "bei {project} eingegeben wurde."
        ),
    },
}


@dataclass(frozen=True, slots=True)
class GuestShift:
    """One shift as a guest mail names it."""

    task_name: str
    date: dt.date
    start_time: dt.time | None
    end_time: dt.time | None
    location: str | None
    #: What the shift earns once it is over; 0 for one read from a
    #: cancellation's snapshot.
    vouchers: int = 0


@dataclass(frozen=True, slots=True)
class GuestMail:
    """Everything a guest mail says, read from the database before it goes out,
    so sending it needs no session (it runs after the request has ended)."""

    kind: GuestMailKind
    to: str
    language: str
    #: The name of the sign-ups the mail is about; None greets no one by name.
    name: str | None
    event_name: str
    #: The event's zone, which the times are on.
    zone: str | None
    shifts: tuple[GuestShift, ...]
    token: str
    #: The line on "Das war ich nicht"; None for a guest account, whose page
    #: does not offer it.
    not_me: NotMeOffer | None
    #: The confirmation only: ``GUEST_DATA_RETENTION_DAYS``, and whether the
    #: chain stored a phone number, for the line on how long data is kept.
    retention_days: int | None = None
    has_phone: bool = False


@dataclass(frozen=True, slots=True)
class RenderedGuestMail:
    title: str
    text: str
    html: str
    action_url: str
    action_label: str
    footer: str


def _when(shift: GuestShift, language: str, zone: str | None) -> str:
    day = day_span(shift.date, shift.date, language, zone=zone)
    times = shift_times(shift.start_time, shift.end_time, zone)
    if shift.start_time and shift.end_time:
        return f"{day} · {times['start_time']}–{times['end_time']}"
    if shift.start_time:
        return f"{day} · {times['start_time']}"
    return day


def greeting_name(names: Iterable[str | None]) -> str | None:
    """The name a mail about these sign-ups greets: the one they share, or
    None when they were made under different names (a pooled account)."""
    distinct = set(names)
    return distinct.pop() if len(distinct) == 1 else None


def _voucher_lines(mail: GuestMail, s: dict[str, str]) -> list[str]:
    """What the shift earns and how to redeem it, in a confirmation or a
    reminder about one shift that earns vouchers."""
    if mail.kind not in ("confirmation", "reminder") or len(mail.shifts) != 1:
        return []
    count = mail.shifts[0].vouchers
    if count <= 0:
        return []
    number = "one" if count == 1 else "other"
    return [s[f"vouchers_{number}"].format(count=count), s["redeem"]]


def _confirmation_lines(mail: GuestMail, s: dict[str, str]) -> list[str]:
    """How to confirm the address, and how long the data is kept. The hint
    speaks of vouchers being added up only in a mail that says what the shift
    earns: a guest of an event without vouchers never reads of them."""
    if mail.kind != "confirmation" or mail.retention_days is None:
        return []
    retention = s["retention_phone" if mail.has_phone else "retention"].format(
        days=mail.retention_days
    )
    if any(shift.vouchers > 0 for shift in mail.shifts):
        retention = f"{retention} {s['retention_vouchers']}"
    hint = "confirm_hint_vouchers" if _voucher_lines(mail, s) else "confirm_hint"
    return [s[hint].format(event=mail.event_name), retention]


def render(mail: GuestMail) -> RenderedGuestMail:
    """The mail as subject, plain text and HTML, in the guest's language."""
    language = mail.language if mail.language in _LANGUAGES else "en"
    s = _STRINGS[language]
    first = mail.shifts[0]
    if mail.kind in ("cancelled", "removed"):
        number = "one" if len(mail.shifts) == 1 else "other"
        title_key, intro_key = (
            f"title_{mail.kind}_{number}",
            f"intro_{mail.kind}_{number}",
        )
    else:
        title_key, intro_key = f"title_{mail.kind}", f"intro_{mail.kind}"
    title = s[title_key].format(task=first.task_name, count=len(mail.shifts))
    intro = s[intro_key].format(event=mail.event_name)
    greeting = (
        s["greeting"].format(name=mail.name) if mail.name else s["greeting_no_name"]
    )

    if len(mail.shifts) == 1:
        details = [
            (s["detail_task"], first.task_name),
            (s["detail_when"], _when(first, language, mail.zone)),
        ]
        if first.location:
            details.append((s["detail_location"], first.location))
    else:
        details = [
            (_when(shift, language, mail.zone), shift.task_name)
            for shift in mail.shifts
        ]

    action_url = guest_tokens.manage_url(mail.token)
    action_label = s["cta"]
    footer = s["footer"].format(project=settings.PROJECT_NAME)
    # The vouchers come before "manage", which introduces the page that
    # "confirm_hint" then calls "that page".
    body = [
        *_voucher_lines(mail, s),
        s["manage"],
        *_confirmation_lines(mail, s),
    ]
    earns = any(shift.vouchers > 0 for shift in mail.shifts)
    small_print = [
        *([s[f"not_me_{mail.not_me}"]] if mail.not_me is not None else []),
        s["link_private_vouchers" if earns else "link_private"],
    ]
    text = "\n\n".join(
        [
            greeting,
            intro,
            "\n".join(f"{label}: {value}" for label, value in details),
            *body,
            f"{action_label}:\n{action_url}",
            *small_print,
            f"--\n{footer}",
        ]
    )
    content = (
        paragraphs_html([greeting, intro])
        + details_table_html(details, label_width=110)
        + paragraphs_html(body, first_margin=20)
        + button_html(action_url, action_label)
        + small_print_html(small_print[0])
        + "".join(small_print_html(line, margin_top=8) for line in small_print[1:])
        # Clients that strip the button must still leave a way to the page.
        + link_fallback_html(action_url, s["link_fallback"])
    )
    return RenderedGuestMail(
        title=title,
        text=text,
        html=card_html(
            title=title, content=content, language=language, footer_text=footer
        ),
        action_url=action_url,
        action_label=action_label,
        footer=footer,
    )


async def send_guest_mail(mail: GuestMail) -> bool:
    """Send a mail already reserved (``guest_quota.reserve_mail``); never raise.

    Queued as a background task by the routes, which import it by name.
    Without SMTP it refuses on its own too: the transactional path would log
    the link instead, and a manage link must never reach a log.
    """
    if not settings.emails_configured:
        logger.info(f"guest mail not sent: SMTP not configured ({mail.kind})")
        return False
    try:
        rendered = render(mail)
    except Exception:
        logger.exception(f"Failed to render the guest {mail.kind} mail")
        return False
    return await send_action_mail(
        to=mail.to,
        language=mail.language,
        title=rendered.title,
        text_body=rendered.text,
        action_url=rendered.action_url,
        action_label=rendered.action_label,
        footer=rendered.footer,
        kind=f"guest.{mail.kind}",
        html_body=rendered.html,
    )


async def not_me_offer(
    session: AsyncSession, guest: SharedListGuest
) -> NotMeOffer | None:
    """What "Das war ich nicht" does for this guest, as its manage page will
    offer it (``GuestSignupManage.can_reject`` and ``reject_suppresses``)."""
    if guest.confirmed_at is not None:
        return None
    if guest.email is not None and await guest_quota.rejection_suppresses(
        session, address=guest.email
    ):
        return "suppresses"
    return "erases"


def guest_shift(shift: Shift, task: Task) -> GuestShift:
    return GuestShift(
        task_name=task.name,
        date=shift.date,
        start_time=shift.start_time,
        end_time=shift.end_time,
        location=shift.location,
        vouchers=task.vouchers_per_shift,
    )


# ── Member notices, as guest mail ─────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Notice:
    kind: GuestMailKind
    event: Event
    #: The booking the mail is about, the first of several.
    booking_id: uuid.UUID
    shifts: tuple[GuestShift, ...]
    #: Whom it greets (:func:`greeting_name`).
    name: str | None


def _uuid(data: NotificationData, key: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(data[key]))
    except (KeyError, ValueError):
        return None


def _uuids(data: NotificationData, key: str) -> list[uuid.UUID]:
    """A comma-separated list of ids, as ``booking_ids``; empty if malformed."""
    try:
        return [uuid.UUID(part) for part in str(data[key]).split(",")]
    except (KeyError, ValueError):
        return []


async def _booked_shift(
    session: AsyncSession, recipient: User, booking: Booking | None, kind: GuestMailKind
) -> _Notice | None:
    """A notice about one confirmed booking of the guest, at its current time."""
    if (
        booking is None
        or booking.user_id != recipient.id
        or booking.status != "confirmed"
        or booking.shift_id is None
    ):
        return None
    row = (
        await session.execute(
            select(Shift, Task, Event)
            .join(Task, col(Task.id) == col(Shift.task_id))
            .join(Event, col(Event.id) == col(Task.event_id))
            .where(col(Shift.id) == booking.shift_id)
        )
    ).first()
    if row is None:
        return None
    shift, task, event = row
    return _Notice(
        kind=kind,
        event=event,
        booking_id=booking.id,
        shifts=(guest_shift(shift, task),),
        name=booking.guest_name,
    )


async def _cancelled(
    session: AsyncSession,
    recipient: User,
    guest: SharedListGuest,
    data: NotificationData,
    scope_chain: list[tuple[str, uuid.UUID]] | None,
) -> _Notice | None:
    """The guest's bookings that ended with their shifts in the action the
    notice is about, read from the snapshot the cancellation wrote.

    ``data["booking_ids"]`` names exactly those of this person, and only on
    shifts not over yet (``dispatch_booking_cancelled_by_admin``), so a mail
    never names a shift worked or one an earlier mail named. The shifts are
    gone, so their event comes from the notice's scope: a task moved to
    another event took its bookings there, away from the guest's list.
    """
    bookings = (
        await session.execute(
            select(Booking)
            .where(
                col(Booking.id).in_(_uuids(data, "booking_ids")),
                col(Booking.user_id) == recipient.id,
                col(Booking.status) == "cancelled",
                col(Booking.shift_id).is_(None),
            )
            .order_by(
                col(Booking.cancelled_shift_date),
                col(Booking.cancelled_shift_start_time).asc().nulls_first(),
                col(Booking.id),
            )
        )
    ).scalars()
    found = [
        (
            booking.id,
            GuestShift(
                task_name=booking.cancelled_task_name
                or booking.cancelled_shift_title
                or "",
                date=booking.cancelled_shift_date,
                start_time=booking.cancelled_shift_start_time,
                end_time=booking.cancelled_shift_end_time,
                location=None,
            ),
            booking.guest_name,
        )
        for booking in bookings
        if booking.cancelled_shift_date is not None
    ]
    if not found:
        return None
    event_id = next(
        (scope_id for scope, scope_id in scope_chain or () if scope == "event"),
        None,
    )
    event = await session.get(Event, event_id) if event_id else None
    if event is None:
        # A task without an event: the guest's own list's event is the one
        # they know. shared_list_guests.event_id is a foreign key.
        event = await session.get(Event, guest.event_id)
        assert event is not None
    return _Notice(
        kind="cancelled",
        event=event,
        booking_id=found[0][0],
        shifts=tuple(shift for _, shift, _ in found),
        name=greeting_name(name for _, _, name in found),
    )


async def _load_notice(
    session: AsyncSession,
    *,
    recipient: User,
    guest: SharedListGuest,
    type_code: str,
    data: NotificationData,
    scope_chain: list[tuple[str, uuid.UUID]] | None,
) -> _Notice | None:
    if type_code == "booking.reminder":
        booking_id = _uuid(data, "booking_id")
        booking = await session.get(Booking, booking_id) if booking_id else None
        return await _booked_shift(session, recipient, booking, "reminder")
    if type_code == "shift.time_changed":
        shift_id = _uuid(data, "slot_id")
        booking = (
            await session.scalar(
                select(Booking).where(
                    col(Booking.shift_id) == shift_id,
                    col(Booking.user_id) == recipient.id,
                )
            )
            if shift_id
            else None
        )
        return await _booked_shift(session, recipient, booking, "moved")
    # booking.cancelled_by_admin
    return await _cancelled(session, recipient, guest, data, scope_chain)


async def deliver_notice(
    session: AsyncSession,
    *,
    recipient: User,
    type_code: str,
    data: NotificationData | None,
    scope_chain: list[tuple[str, uuid.UUID]] | None,
) -> None:
    """Mail a guest the notice ``type_code`` would have been, written here.

    ``data`` is only a key into the database: the reminder's ``booking_id``,
    the cancellation's ``booking_ids``, the moved shift's ``slot_id``.
    ``scope_chain`` is the notice's, of which only a cancellation needs the
    event. Called by ``NotificationService.notify`` with its session for the
    reads; the mail is reserved in a short transaction of its own, so the
    address lock is not held while the caller goes on to other recipients.
    Never raises: a guest's mail must not cost the members in the same notice
    theirs.
    """
    if type_code not in GUEST_MAIL_TYPES or not data:
        return
    try:
        guest = await crud_guest.get_by_user_id(session, user_id=recipient.id)
        if guest is None or guest.email is None or guest.manage_nonce is None:
            return
        notice = await _load_notice(
            session,
            recipient=recipient,
            guest=guest,
            type_code=type_code,
            data=data,
            scope_chain=scope_chain,
        )
        if notice is None:
            return
        async with async_session.begin() as own:
            reserved = await guest_quota.reserve_mail(
                own,
                address=guest.email,
                kind=notice.kind,
                event_id=notice.event.id,
                booking_id=notice.booking_id,
            )
        if not reserved:
            return
        await send_guest_mail(
            GuestMail(
                kind=notice.kind,
                to=guest.email,
                language=recipient.preferred_language,
                name=notice.name,
                event_name=notice.event.name,
                zone=notice.event.timezone,
                shifts=notice.shifts,
                token=guest_tokens.mail_token(guest),
                not_me=await not_me_offer(session, guest),
            )
        )
    except Exception:
        logger.exception(f"Failed to deliver the guest mail for {type_code}")
