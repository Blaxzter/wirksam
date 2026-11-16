"""Signing up for a shift through a shared list, without an account.

The route answers for the kill switch, the rate limits and Turnstile;
:func:`sign_up` does the rest, refusing in this order:

1. an unknown code (404 ``shared_list.not_found``);
2. a paused list (409 ``shared_list.paused``), or one that is closed,
   whether expired or ended (409 ``shared_list.closed``);
3. a missing address or phone number the list requires (422);
4. a shift the list does not offer (404 ``shared_list.shift_not_offered``) or
   one that has started (409 ``shared_list.shift_started``);
5. a ``guest_token`` that is not a live chain of this list (403
   ``shared_list.guest_token_invalid``). A token its chain's confirmation
   retired, or one of a guest account, starts a new chain instead;
6. the daily ceilings of the address and of the list (429, ``guest_quota``);
7. the list's per-person limit (409 ``shared_list.max_per_person``);
8. under the shift's capacity lock: the same address, or the same chain,
   already on the shift (409 ``shared_list.already_signed_up``), an overlap
   with the chain's other shifts (409 ``booking.time_conflict``), and a full
   shift (409 ``booking.slot_full``).

A sign-up chain is one guest user (``crud.shared_list_guest``): the first
sign-up of a visit creates it, "Noch eine Schicht eintragen" continues it with
the ``guest_token`` from the first answer, and it never leaves the list it
started on. It is never found by a typed address: anyone can type anyone's.
A sign-up never continues a guest account (``guest_account.py``).

Each booking keeps its own person: the first-name consent its form gave, and
the name and phone the chain stored (``bookings.show_first_name``,
``guest_name``, ``guest_phone``), since a confirmation may later pool it with
sign-ups of other people under one guest account.

Locks, always in this order, so no two requests wait for each other in a
circle: the event row ``FOR KEY SHARE`` (``crud.event.lock``: deleting the
event takes it before the list rows its CASCADE reaches, and the guest row
inserted here needs it for its foreign key), the list row ``FOR KEY SHARE``
(a pause or an end waits for the sign-ups in flight, and once it has
committed none that read "live" can complete), the chain's guest row ``FOR
UPDATE``, the address (``guest-address:{hash}``), the list's day count, and
last the shift (``booking_capacity.lock_shifts``). The address lock also
serialises the per-person count by address, so it needs none of its own.
"""

import datetime as dt
from dataclasses import dataclass
from typing import NoReturn

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.crud.event import event as crud_event
from app.crud.shared_list import shared_list as crud_shared_list
from app.crud.shared_list_guest import shared_list_guest as crud_guest
from app.crud.task import task as crud_task
from app.logic import clock
from app.logic.booking_capacity import lock_shifts
from app.logic.booking_conflicts import find_conflicting_booking
from app.logic.shared_lists import guest_quota, guest_tokens, offer
from app.logic.shared_lists.guest_mail import (
    GUEST_REMINDER,
    GuestMail,
    guest_shift,
    not_me_offer,
)
from app.logic.shared_lists.offer import OfferedShift
from app.logic.shared_lists.public_page import first_names, public_shift
from app.models.booking import Booking
from app.models.shared_list import SharedList, SharedListGuest
from app.models.user import User
from app.schemas.booking import ShiftConflict
from app.schemas.public_shared_list import PublicSignupRequest, PublicSignupResult


@dataclass(frozen=True, slots=True)
class SignupOutcome:
    result: PublicSignupResult
    #: The confirmation, already reserved; the route sends it after the commit.
    confirmation: GuestMail | None


async def _offered_shift(
    session: AsyncSession,
    shared_list: SharedList,
    form: PublicSignupRequest,
    now_wall: dt.datetime,
) -> OfferedShift:
    """The shift asked for, if the list offers it and it has not started."""
    included = await offer.list_shifts(
        session, shared_list, now_wall=now_wall, include_started=True
    )
    offered = next((o for o in included if o.shift.id == form.shift_id), None)
    if offered is None:
        raise_problem(
            404,
            code="shared_list.shift_not_offered",
            detail="This list does not offer that shift",
        )
    if offered.starts_at <= now_wall:
        raise_problem(
            409, code="shared_list.shift_started", detail="This shift has started"
        )
    return offered


async def _chain(
    session: AsyncSession, shared_list: SharedList, token: str
) -> SharedListGuest | None:
    """The live, unconfirmed chain of this list that ``token`` continues.

    None, which starts a new chain from the typed fields, when the chain was
    confirmed since (its response token is retired) or the token opens a
    guest account: "Noch eine Schicht eintragen" keeps working in a tab
    whose chain was confirmed meanwhile, and a sign-up never continues an
    account.
    """
    key = await guest_tokens.resolve(session, token)
    if key is None:
        if await guest_tokens.retired_response_token(session, token):
            return None
    elif key.guest.confirmed_at is not None:
        return None
    elif key.guest.shared_list_id == shared_list.id:
        return key.guest
    raise_problem(
        403,
        code="shared_list.guest_token_invalid",
        detail="This sign-up cannot be continued here",
    )


async def _held_through_list(
    session: AsyncSession,
    shared_list: SharedList,
    *,
    email: str | None,
    guest: SharedListGuest | None,
) -> int:
    """Confirmed shifts this person holds through the list: counted by address
    when there is one, else by chain; a new chain without an address holds
    none yet."""
    query = select(func.count()).select_from(Booking)
    if email is not None:
        query = query.join(
            SharedListGuest, col(SharedListGuest.user_id) == col(Booking.user_id)
        ).where(func.lower(col(SharedListGuest.email)) == email)
    elif guest is not None:
        query = query.where(col(Booking.user_id) == guest.user_id)
    else:
        return 0
    held = await session.scalar(
        query.where(
            col(Booking.shared_list_id) == shared_list.id,
            col(Booking.status) == "confirmed",
        )
    )
    return held or 0


async def _refuse_if_taken(
    session: AsyncSession,
    offered: OfferedShift,
    *,
    email: str | None,
    chain_booking: Booking | None,
    guest: SharedListGuest | None,
    zone: str,
) -> int:
    """The checks that need the shift's capacity lock; returns the confirmed
    bookings the shift has before this one."""
    shift = offered.shift
    if email is not None:
        # Any guest with this address, through any list: a second chain
        # typed with the same address is the same person.
        same_address = await session.scalar(
            select(col(Booking.id))
            .join(SharedListGuest, col(SharedListGuest.user_id) == col(Booking.user_id))
            .where(
                col(Booking.shift_id) == shift.id,
                col(Booking.status) == "confirmed",
                func.lower(col(SharedListGuest.email)) == email,
            )
            .limit(1)
        )
        if same_address is not None:
            _refuse_already_signed_up()
    if chain_booking is not None and chain_booking.status == "confirmed":
        _refuse_already_signed_up()
    if guest is not None:
        conflict = await find_conflicting_booking(
            session, user_id=guest.user_id, shift=shift, zone=zone
        )
        if conflict is not None:
            conflict_task = await crud_task.get(session, str(conflict.shift.task_id))
            clash = ShiftConflict.model_validate(conflict.shift)
            clash.task_name = conflict_task.name if conflict_task else None
            raise_problem(
                409,
                code="booking.time_conflict",
                detail=f"This shift overlaps your booked shift '{clash.title}'",
                extensions={"conflicting_shift": clash.model_dump(mode="json")},
            )
    confirmed = await crud_booking.get_confirmed_count(session, shift_id=shift.id)
    if confirmed >= shift.max_bookings:
        raise_problem(
            409, code="booking.slot_full", detail="This duty shift is fully booked"
        )
    return confirmed


def _refuse_already_signed_up() -> NoReturn:
    raise_problem(
        409,
        code="shared_list.already_signed_up",
        detail="This person is already signed up for this shift",
    )


def _refuse_not_found() -> NoReturn:
    raise_problem(404, code="shared_list.not_found", detail="Shared list not found")


async def sign_up(
    session: AsyncSession, *, code: str, form: PublicSignupRequest, now: dt.datetime
) -> SignupOutcome:
    """Sign a guest up for one shift of the list behind ``code``.

    ``now`` is naive UTC, for the chain's ``last_signup_at``. Nothing is
    written before the last refusal, and no member notice is sent: the guest
    gets one confirmation per chain, by mail, and nobody else is told.
    """
    found = await crud_shared_list.get_by_code(session, code=code)
    if found is None:
        _refuse_not_found()
    event = await crud_event.lock(session, found.event_id, mode="key_share")
    # Read again under the lock: the list may have been rotated, or deleted
    # with its event, in between.
    shared_list = await crud_shared_list.get_by_code(
        session, code=code, lock="key_share"
    )
    if event is None or shared_list is None:
        _refuse_not_found()
    now_wall = clock.wall_clock_now(event.timezone)
    effective = offer.effective_status(
        shared_list,
        event=event,
        last_start=await offer.last_start(session, shared_list),
        now_wall=now_wall,
    )
    if effective == "paused":
        raise_problem(409, code="shared_list.paused", detail="This list is paused")
    if effective != "live":
        raise_problem(409, code="shared_list.closed", detail="This list is closed")

    email = form.email if shared_list.ask_email != "off" else None
    phone = form.phone if shared_list.ask_phone != "off" else None
    if shared_list.ask_email == "required" and email is None:
        raise_problem(
            422,
            code="shared_list.email_required",
            detail="An email address is required",
        )
    if shared_list.ask_phone == "required" and phone is None:
        raise_problem(
            422, code="shared_list.phone_required", detail="A phone number is required"
        )

    offered = await _offered_shift(session, shared_list, form, now_wall)

    guest: SharedListGuest | None = None
    if form.guest_token is not None:
        guest = await _chain(session, shared_list, form.guest_token)
    if guest is not None:
        # The chain is one person: what it stored wins over what was typed.
        email = guest.email

    hashed = guest_tokens.address_hash(email) if email is not None else None
    if hashed is not None:
        await guest_quota.admit_signup(session, hashed=hashed, event_id=event.id)
    await guest_quota.admit_list_signup(session, shared_list_id=shared_list.id)

    limit = shared_list.max_per_person
    held = 0
    if limit is not None:
        held = await _held_through_list(session, shared_list, email=email, guest=guest)
        if held >= limit:
            raise_problem(
                409,
                code="shared_list.max_per_person",
                detail=f"One person can take at most {limit} shifts through this list",
                extensions={"max": limit},
            )

    await lock_shifts(session, [offered.shift.id])
    chain_booking = (
        await crud_booking.get_by_shift_and_user(
            session, shift_id=offered.shift.id, user_id=guest.user_id
        )
        if guest is not None
        else None
    )
    confirmed = await _refuse_if_taken(
        session,
        offered,
        email=email,
        chain_booking=chain_booking,
        guest=guest,
        zone=event.timezone,
    )

    first = guest is None
    if guest is None:
        guest = await crud_guest.create(
            session,
            shared_list=shared_list,
            name=form.name,
            email=email,
            phone=phone,
            language=form.language,
            now=now,
        )
    else:
        guest.last_signup_at = now
        session.add(guest)
    person = await session.get(User, guest.user_id)
    assert person is not None  # the guest row's foreign key

    if chain_booking is not None:
        # The chain undid this sign-up before; the row comes back, as a
        # member's cancelled booking does when they book again.
        booking = chain_booking
        booking.status = "confirmed"
        booking.shared_list_id = shared_list.id
        booking.cancellation_reason = None
    else:
        booking = Booking(
            shift_id=offered.shift.id,
            user_id=guest.user_id,
            status="confirmed",
            shared_list_id=shared_list.id,
        )
    # Named only when the form said so and the list still does: an organiser
    # may have switched names on after the page was opened.
    booking.show_first_name = (
        form.show_names == "first" and shared_list.show_names == "first"
    )
    booking.guest_name = person.name
    booking.guest_phone = person.phone_number
    session.add(booking)
    await session.flush()

    # Written through replace_for_booking even for a new row: a reactivated
    # one may still carry the reminder it had.
    await crud_reminder.replace_for_booking(
        session,
        booking_id=booking.id,
        user_id=guest.user_id,
        shift_id=offered.shift.id,
        entries=[GUEST_REMINDER] if form.remind and email is not None else [],
        slot_start=offered.starts_at,
        zone=event.timezone,
    )

    guest_quota.record_signup(
        session,
        hashed=hashed,
        event_id=event.id,
        shared_list_id=shared_list.id,
        booking_id=booking.id,
    )
    confirmation: GuestMail | None = None
    # One confirmation per chain: its link lists every later sign-up too.
    if first and email is not None:
        if await guest_quota.reserve_mail(
            session,
            address=email,
            kind="confirmation",
            event_id=event.id,
            booking_id=booking.id,
            shared_list_id=shared_list.id,
        ):
            confirmation = GuestMail(
                kind="confirmation",
                to=email,
                language=form.language,
                name=booking.guest_name,
                event_name=event.name,
                zone=event.timezone,
                shifts=(guest_shift(offered.shift, offered.task),),
                token=guest_tokens.mail_token(guest),
                not_me=await not_me_offer(session, guest),
                retention_days=settings.GUEST_DATA_RETENTION_DAYS,
                has_phone=booking.guest_phone is not None,
            )

    now_offered = OfferedShift(
        shift=offered.shift, task=offered.task, confirmed=confirmed + 1
    )
    names = (
        (await first_names(session, [offered.shift.id])).get(offered.shift.id, [])
        if shared_list.show_names == "first"
        else None
    )
    return SignupOutcome(
        result=PublicSignupResult(
            booking_id=booking.id,
            guest_token=guest_tokens.manage_token(guest),
            shift=public_shift(now_offered, names=names),
            date=offered.shift.date,
            email=email,
            mail_queued=confirmation is not None,
            show_manage_link=first and confirmation is None,
            remaining=None if limit is None else max(0, limit - held - 1),
        ),
        confirmation=confirmation,
    )
