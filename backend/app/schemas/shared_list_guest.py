"""Who signed up through a shared list: the organisers' table and removal,
and the operator's lookup of guest data.

A guest's address and phone number go only to the event admins and the
people in charge of the task the sign-up is on, as for members.
"""

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

from app.schemas.public_shared_list import (
    GuestEmail,
    GuestSignupBooking,
    GuestVoucherAccount,
)

#: How the organisers' table of one list's sign-ups can be sorted.
SignupSort = Literal["created_at", "name", "shift_start"]


def _naive_utc(value: dt.datetime | None) -> dt.datetime | None:
    """Stored timestamps are naive UTC; an aware one is converted, not refused."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(dt.UTC).replace(tzinfo=None)


class SharedListSignup(BaseModel):
    """One confirmed sign-up through a list."""

    booking_id: uuid.UUID
    #: None once the guest's data was erased ("Gast (gelöscht)").
    name: str | None = None
    erased: bool
    email: str | None = None
    phone: str | None = None
    task_id: uuid.UUID
    task_name: str
    shift_id: uuid.UUID
    shift_date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    #: When the guest signed up, naive UTC.
    created_at: dt.datetime
    #: Another guest of the same name is on the same shift; without an
    #: address two sign-ups cannot be told apart otherwise.
    possible_duplicate: bool
    #: The shift is not over, so the sign-up can still be removed.
    can_remove: bool
    #: The guest confirmed their address, which pools every sign-up confirmed
    #: with it at the event under one guest account, perhaps other people's:
    #: how many confirmed sign-ups that account holds besides this one. They
    #: go too when the guest's data is erased. 0 for any other sign-up.
    pooled_signups: int


class SharedListSignupListResponse(BaseModel):
    items: list[SharedListSignup]
    total: int
    skip: int
    limit: int
    #: Confirmed sign-ups through the list on tasks the caller is not in
    #: charge of, left out of ``items``.
    hidden_count: int
    #: The caller is an event admin, who may erase guests' data on removal.
    can_erase: bool


class SharedListSignupRemoveRequest(BaseModel):
    """Which sign-ups to remove: exactly one of ``booking_ids`` and
    ``created_since`` (422 ``shared_list.remove_selector`` otherwise)."""

    booking_ids: list[uuid.UUID] | None = Field(
        default=None, min_length=1, max_length=100
    )
    #: Every confirmed sign-up through the list from this moment on, at most
    #: 500 per call: the clean-up after a wave of fake sign-ups.
    created_since: Annotated[dt.datetime | None, AfterValidator(_naive_utc)] = None
    #: Mail the guests who were taken off. Off for spam, so the addresses
    #: someone typed are not written to again.
    notify: bool = True
    #: Also erase the data of every guest touched (event admins only), as for
    #: a guest who asked an organiser to delete it.
    erase: bool = False


class SharedListSignupSkip(BaseModel):
    """A sign-up the removal left alone, and why, as an error code."""

    id: uuid.UUID
    code: str


class SharedListSignupRemoveResult(BaseModel):
    removed: list[uuid.UUID]
    erased_guests: int
    #: Confirmed sign-ups beyond ``removed`` that ``erase`` took off with
    #: their guests: the shifts not over yet of a chain or a guest account
    #: touched, which may hold other people's sign-ups under the same address.
    also_removed: int
    skipped: list[SharedListSignupSkip]


class ListGuestAdminRow(BaseModel):
    """A guest, as the operator finds them for a data-subject request."""

    guest_user_id: uuid.UUID
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    #: The event of the list the guest signed up on; None once it was deleted.
    event_id: uuid.UUID | None = None
    event_name: str | None = None
    booking_count: int
    last_signup_at: dt.datetime | None = None
    erased: bool


class ListGuestAdminListResponse(BaseModel):
    items: list[ListGuestAdminRow]
    total: int
    skip: int
    limit: int


class ListGuestExportBooking(GuestSignupBooking):
    """One booking in the export: as the guest's page shows it, plus the
    phone number this sign-up was made with (``bookings.guest_phone``)."""

    phone: str | None = None


class ListGuestExport(ListGuestAdminRow):
    """Everything stored about one guest, for a request under Art. 15 GDPR.

    The manage link's nonce and the aliases of merged chains are left out:
    they are credentials, not data about the person. ``name`` and ``phone``
    are the guest user's; each booking carries the name, phone and first-name
    consent of its own sign-up.
    """

    preferred_language: str
    #: The list the guest's sign-ups started on.
    shared_list_id: uuid.UUID | None = None
    created_at: dt.datetime
    erased_at: dt.datetime | None = None
    #: When the address was confirmed, which made this a guest account.
    confirmed_at: dt.datetime | None = None
    bookings: list[ListGuestExportBooking]
    #: What the guest earned and redeemed, and the corrections, per event,
    #: without who redeemed or corrected and without the corrections' notes.
    vouchers: list[GuestVoucherAccount]


class MailSuppressionLift(BaseModel):
    """An address "Das war ich nicht" stopped all mail to, to mail again."""

    email: GuestEmail
