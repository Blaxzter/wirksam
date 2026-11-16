"""What strangers see of a shared list, and what a guest sends and gets back.

Nothing here names anyone beyond the first names of guests who agreed to it:
no full names, addresses, phone numbers or user ids, no task descriptions,
and nothing an organiser wrote for the organisers (``share_note``). The list's
``title`` and ``intro`` are organiser text on a page strangers trust, so the
frontend shows them as plain text, never as HTML.
"""

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Field,
    StringConstraints,
)

from app.logic.shared_lists.normalize import (
    normalize_email,
    normalize_name,
    normalize_phone,
)
from app.models.shared_list import AskMode, ShowNames
from app.schemas.voucher import VoucherAccount


def _blank_is_none(value: object) -> object:
    """An optional field left empty in a form is not given at all."""
    return None if isinstance(value, str) and not value.strip() else value


# The length bounds the raw input; the normaliser then applies the real rule.
GuestName = Annotated[
    str, StringConstraints(max_length=100), AfterValidator(normalize_name)
]
GuestEmail = Annotated[
    str, StringConstraints(max_length=254), AfterValidator(normalize_email)
]
GuestPhone = Annotated[
    str, StringConstraints(max_length=30), AfterValidator(normalize_phone)
]


class PublicShift(BaseModel):
    """One shift on the public page."""

    id: uuid.UUID
    task_id: uuid.UUID
    task_name: str
    location: str | None = None
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    capacity: int
    free: int
    full: bool
    #: First names of guests who agreed to be named when they signed up, from
    #: any list; only while this list shows first names.
    names: list[str] = Field(default_factory=list)
    #: Everyone else on the shift, counted, never named.
    others_count: int = 0
    #: The vouchers ("Marken") the shift earns once it is over; 0 for none.
    vouchers: int = 0


class PublicDay(BaseModel):
    date: dt.date
    shifts: list[PublicShift]


class PublicEventRef(BaseModel):
    name: str
    start_date: dt.date
    end_date: dt.date
    timezone: str


class PublicSharedList(BaseModel):
    """``GET /public/shared-lists/{code}``, and the organisers' preview."""

    code: str
    title: str
    #: Plain text: shown with line breaks, never rendered as HTML or linkified.
    intro: str | None = None
    #: ``expired`` and ``ended`` both show as ``closed``.
    status: Literal["live", "paused", "closed"]
    event: PublicEventRef
    ask_email: AskMode
    ask_phone: AskMode
    show_names: ShowNames
    max_per_person: int | None = None
    #: Empty unless ``live``.
    days: list[PublicDay]
    #: ``GUEST_DATA_RETENTION_DAYS``: what a guest typed is deleted this many
    #: days after their last shift. The page says so with this number.
    retention_days: int


class PublicSignupRequest(BaseModel):
    """Signing up for one shift without an account.

    ``name``, ``email`` and ``phone`` are normalised here
    (``logic/shared_lists/normalize.py``); a value that cannot be is a 422.
    Whether the list asks for an address or a number at all is the sign-up's
    check. With ``guest_token`` (from the first sign-up's answer) the sign-up
    continues that chain, and what the chain stored wins over these fields.
    """

    shift_id: uuid.UUID
    name: GuestName
    email: Annotated[GuestEmail | None, BeforeValidator(_blank_is_none)] = None
    phone: Annotated[GuestPhone | None, BeforeValidator(_blank_is_none)] = None
    #: A reminder by mail the day before; only with an address.
    remind: bool = False
    language: Literal["en", "de"] = "de"
    #: The list's ``show_names`` as the form showed it. This sign-up's first
    #: name appears publicly only if the form said so and the list still does;
    #: stored on this booking (``bookings.show_first_name``).
    show_names: ShowNames
    guest_token: str | None = Field(default=None, max_length=128)
    # Optional here, required by the route when the deployment has Turnstile
    # (the RegisterRequest pattern).
    turnstile_token: str | None = Field(default=None, max_length=2048)


class PublicSignupResult(BaseModel):
    booking_id: uuid.UUID
    #: Continues the chain ("Noch eine Schicht eintragen"), undoes the sign-up,
    #: and opens the manage page (``/guest-signup#<token>``), all but its "Das
    #: war ich nicht": that needs the link from the mail.
    guest_token: str
    shift: PublicShift
    date: dt.date
    email: str | None = None
    #: A confirmation mail is on its way. False for every sign-up after the
    #: first of a chain, and alike for no SMTP, an address that opted out and
    #: one over its daily ceiling, so the answer reveals none of them.
    mail_queued: bool
    #: The first sign-up of a chain that got no mail: the page shows the manage
    #: link, the guest's only way back.
    show_manage_link: bool
    #: Shifts this person may still take through the list; None for no limit.
    remaining: int | None = None


class GuestTokenRequest(BaseModel):
    """A manage link's token, sent in the body so it never reaches a log."""

    token: str = Field(max_length=128)


class GuestCancelRequest(GuestTokenRequest):
    booking_id: uuid.UUID


class GuestRemindersRequest(GuestTokenRequest):
    enabled: bool


class GuestSignupBooking(BaseModel):
    booking_id: uuid.UUID
    status: Literal["confirmed", "cancelled"]
    #: Per booking: a moved task takes its bookings to another event.
    event_name: str | None = None
    task_name: str
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    location: str | None = None
    can_cancel: bool
    reminder_on: bool
    #: What the shift earns once it is over; 0 for a shift that was removed.
    vouchers: int = 0
    #: This sign-up's consent: its first name appears on shared lists that
    #: show first names.
    show_first_name: bool = False
    #: The name this sign-up was made under (``bookings.guest_name``). The page
    #: shows it when it differs from the page's name, after a family's
    #: sign-ups were pooled; None once erased.
    name: str | None = None


class GuestVoucherAccount(BaseModel):
    """A guest's vouchers in one event."""

    event_id: uuid.UUID
    event_name: str
    #: As members see theirs, without the names of whoever redeemed or
    #: corrected (``actor_name``) and without an organiser's ``note``; and the
    #: summary carries no ``email``.
    account: VoucherAccount


class GuestSignupManage(BaseModel):
    """The guest's manage page: a sign-up chain, or a guest account."""

    #: The wallet holder's name: for an account, its first confirmed chain's.
    #: Each booking carries its own (``GuestSignupBooking.name``).
    name: str | None = None
    email: str | None = None
    #: The event of the list the guest signed up on.
    event: PublicEventRef
    bookings: list[GuestSignupBooking]
    #: Reminders go by mail, so only with an address.
    can_set_reminders: bool
    #: This is a guest account: the address was confirmed through a mail link.
    confirmed: bool
    #: Offer "Ja, das bin ich": opened from a mail, not confirmed yet, and an
    #: address to confirm.
    can_confirm: bool
    #: Offer "Das war ich nicht": opened from a mail, and not confirmed (whoever
    #: confirmed these sign-ups cannot disown them).
    can_reject: bool
    #: "Das war ich nicht" also stops all mail to the address: false while the
    #: address has a confirmed account at any event, whose mail would stop too.
    reject_suppresses: bool
    #: A phone number is stored for this guest or one of its sign-ups. With
    #: ``email``, it picks the retention text.
    has_phone: bool
    #: ``GUEST_DATA_RETENTION_DAYS``.
    retention_days: int
    #: The first day the guest's data may be deleted: ``retention_days`` after
    #: their last shift. Unredeemed vouchers expire with it.
    erase_on: dt.date
    #: Per event in which the guest has or will have vouchers, their own event
    #: first; empty when nothing earns any.
    vouchers: list[GuestVoucherAccount]


class GuestConfirmResult(BaseModel):
    """``POST /public/guest-signups/confirm``."""

    #: The account's mail token: the page uses it from now on.
    token: str
    manage: GuestSignupManage


class GuestPassRequest(GuestTokenRequest):
    """A voucher code for one event, asked for with a manage token."""

    event_id: uuid.UUID


class GuestPassStatusRequest(GuestPassRequest):
    pass_id: uuid.UUID
