"""Organisers taking guests off shifts they signed up for through a list.

One call serves the row action "Austragen", a selection, and the clean-up
after a wave of fake sign-ups ("Diese und alle neueren austragen"). It is the
only way an organiser cancels someone else's booking; members' bookings stay
out of it.

Erasing goes by guest user, as everywhere (``erase.erase_guests``): the
chain's other sign-ups go along, and so does everything a guest account
pooled under its address. The organisers' table says how many sign-ups an
account holds (``SharedListSignup.pooled_signups``) and the result how many
went beyond the selection (``also_removed``).

Each sign-up is judged on its own, and one that may not be removed is
reported in ``skipped`` with the reason as an error code, never failing the
rest: not through this list, no longer confirmed, or handed to a guest
account while this call waited for its lock (``shared_list.signup_not_found``;
a retry locks the right row), on a task the caller is not in charge of
(``shared_list.forbidden``), booked by someone who is not a guest
(``shared_list.signup_not_guest``: only a guest's sign-up is an organiser's
to cancel or erase), or on a shift that is over (``booking.shift_over``: what
was worked stays worked).

Locks: every guest row touched ``FOR UPDATE``, in one statement in id order,
before anything else; then, for the mails, each address, in the order of its
hash, so two removals sharing addresses cannot wait for each other in a
circle. No shift lock: removing only frees places.
"""

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.errors import raise_problem
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.logic.permissions import SharedListAccess, TaskAccess, task_access
from app.logic.shared_lists import guest_quota, guest_tokens
from app.logic.shared_lists.erase import erase_guests
from app.logic.shared_lists.guest_mail import (
    GuestMail,
    GuestShift,
    greeting_name,
    guest_shift,
    not_me_offer,
)
from app.logic.work_hours import shift_ends_at
from app.models.booking import Booking
from app.models.event import Event
from app.models.shared_list import SharedList, SharedListGuest
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.shared_list_guest import (
    SharedListSignupRemoveRequest,
    SharedListSignupRemoveResult,
    SharedListSignupSkip,
)

#: How many sign-ups one ``created_since`` call removes at most.
CREATED_SINCE_MAX = 500


@dataclass(frozen=True, slots=True)
class RemovalOutcome:
    result: SharedListSignupRemoveResult
    #: Reserved mails to the guests taken off, for the route to send.
    mails: list[GuestMail]


async def _selected(
    session: AsyncSession,
    shared_list: SharedList,
    request: SharedListSignupRemoveRequest,
) -> list[uuid.UUID]:
    if (request.booking_ids is None) == (request.created_since is None):
        raise_problem(
            422,
            code="shared_list.remove_selector",
            detail="Name either the sign-ups or a moment to remove from",
        )
    if request.booking_ids is not None:
        return list(dict.fromkeys(request.booking_ids))
    result = await session.execute(
        select(col(Booking.id))
        .join(Shift, col(Shift.id) == col(Booking.shift_id))
        .join(Task, col(Task.id) == col(Shift.task_id))
        .where(
            col(Booking.shared_list_id) == shared_list.id,
            col(Booking.status) == "confirmed",
            col(Booking.created_at) >= request.created_since,
            # As the table of sign-ups: a task moved away took its own along.
            col(Task.event_id) == shared_list.event_id,
        )
        .order_by(col(Booking.created_at), col(Booking.id))
        .limit(CREATED_SINCE_MAX)
    )
    return list(result.scalars().all())


async def _lock_guests(
    session: AsyncSession, booking_ids: list[uuid.UUID]
) -> dict[uuid.UUID, SharedListGuest]:
    """The guest rows of the bookings' users, locked ``FOR UPDATE`` in id order."""
    result = await session.execute(
        select(SharedListGuest)
        .where(
            col(SharedListGuest.user_id).in_(
                select(col(Booking.user_id)).where(col(Booking.id).in_(booking_ids))
            )
        )
        .order_by(col(SharedListGuest.user_id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return {guest.user_id: guest for guest in result.scalars().all()}


async def remove_signups(
    session: AsyncSession,
    *,
    user: User,
    shared_list: SharedList,
    event: Event,
    access: SharedListAccess,
    request: SharedListSignupRemoveRequest,
    now: dt.datetime,
    now_wall: dt.datetime,
) -> RemovalOutcome:
    """Remove the selected sign-ups; ``access`` is the caller's on the list.

    422 ``shared_list.remove_selector`` unless exactly one selector is given;
    403 ``shared_list.forbidden`` for ``erase`` from anyone but an event admin.
    ``now`` is naive UTC, ``now_wall`` the event's clock.
    """
    booking_ids = await _selected(session, shared_list, request)
    if request.erase and access != "admin":
        raise_problem(
            403,
            code="shared_list.forbidden",
            detail="Only the event admins can erase a guest's data",
        )
    guests = await _lock_guests(session, booking_ids)
    rows = {
        booking.id: (booking, shift, task, booker)
        for booking, shift, task, booker in (
            await session.execute(
                select(Booking, Shift, Task, User)
                .join(Shift, col(Shift.id) == col(Booking.shift_id))
                .join(Task, col(Task.id) == col(Shift.task_id))
                .join(User, col(User.id) == col(Booking.user_id))
                .where(col(Booking.id).in_(booking_ids))
                .execution_options(populate_existing=True)
            )
        ).all()
    }

    access_by_task: dict[uuid.UUID, TaskAccess | None] = {}
    removed: list[uuid.UUID] = []
    skipped: list[SharedListSignupSkip] = []
    touched: dict[uuid.UUID, User] = {}
    shifts_of: dict[uuid.UUID, list[tuple[uuid.UUID, GuestShift, str | None]]] = {}
    not_found = "shared_list.signup_not_found"
    for booking_id in booking_ids:
        row = rows.get(booking_id)
        if row is None:
            skipped.append(SharedListSignupSkip(id=booking_id, code=not_found))
            continue
        booking, shift, task, booker = row
        # A task moved to another event took its sign-ups out of the list.
        if (
            booking.shared_list_id != shared_list.id
            or booking.status != "confirmed"
            or task.event_id != shared_list.event_id
        ):
            skipped.append(SharedListSignupSkip(id=booking_id, code=not_found))
            continue
        if task.id not in access_by_task:
            access_by_task[task.id] = await task_access(user, session, task)
        if access_by_task[task.id] is None:
            skipped.append(
                SharedListSignupSkip(id=booking_id, code="shared_list.forbidden")
            )
            continue
        if not booker.is_list_guest:
            skipped.append(
                SharedListSignupSkip(id=booking_id, code="shared_list.signup_not_guest")
            )
            continue
        if booker.id not in guests:
            # A confirmation merged the chain whose row was locked into a guest
            # account between the lock and this read. Going on would cancel,
            # or erase the whole account, without the account's row lock.
            skipped.append(SharedListSignupSkip(id=booking_id, code=not_found))
            continue
        touched[booker.id] = booker
        if shift_ends_at(shift.date, shift.start_time, shift.end_time) <= now_wall:
            skipped.append(
                SharedListSignupSkip(id=booking_id, code="booking.shift_over")
            )
            continue
        booking.status = "cancelled"
        session.add(booking)
        removed.append(booking.id)
        shifts_of.setdefault(booker.id, []).append(
            (booking.id, guest_shift(shift, task), booking.guest_name)
        )
    await session.flush()
    if removed:
        await crud_reminder.cancel_by_bookings(session, booking_ids=removed)

    mails: list[GuestMail] = []
    also_removed = 0
    if request.erase:
        if touched:
            # A guest account pools every sign-up confirmed with its address,
            # perhaps other people's: they go with it, and are counted.
            also_removed = await erase_guests(session, user_ids=touched.keys(), now=now)
    elif request.notify:
        # Each reservation holds its address's lock until commit, so they are
        # taken in the order of the hashes.
        addressed = sorted(
            (
                (guest_tokens.address_hash(guest.email), guest.email, guest)
                for guest in guests.values()
                if guest.user_id in shifts_of
                and guest.email is not None
                and guest.manage_nonce is not None
            ),
            key=lambda entry: entry[0],
        )
        for _, email, guest in addressed:
            shifts = shifts_of[guest.user_id]
            if await guest_quota.reserve_mail(
                session,
                address=email,
                kind="removed",
                event_id=event.id,
                booking_id=shifts[0][0],
                shared_list_id=shared_list.id,
            ):
                booker = touched[guest.user_id]
                mails.append(
                    GuestMail(
                        kind="removed",
                        to=email,
                        language=booker.preferred_language,
                        name=greeting_name(name for _, _, name in shifts),
                        event_name=event.name,
                        zone=event.timezone,
                        shifts=tuple(shift for _, shift, _ in shifts),
                        token=guest_tokens.mail_token(guest),
                        not_me=await not_me_offer(session, guest),
                    )
                )
    return RemovalOutcome(
        result=SharedListSignupRemoveResult(
            removed=removed,
            erased_guests=len(touched) if request.erase else 0,
            also_removed=also_removed,
            skipped=skipped,
        ),
        mails=mails,
    )
