"""The daily ceilings on guest sign-ups and guest mail.

Anyone can create an event, so the names in a guest mail are chosen by
whoever shares a list, and the address it goes to is whatever an anonymous
visitor typed. The invitation limits (``logic/invitations.py``) work because
the inviter is signed in; here nobody is. So every guest sign-up and every
guest mail appends a row to ``guest_activity_log``, and the ceilings in
``core/config.py`` count those rows over the last 24 hours:

* per address: sign-ups, other events signed up for, and mails of every kind;
* per list: sign-ups, which bounds the guest users a list can mint;
* per event and per organiser (the event's creator when the mail goes out):
  mails.

The log has no foreign keys and holds addresses only as keyed hashes
(``guest_tokens.address_hash``), so erasing a guest, rotating a list or
deleting the event resets nothing. Rows go after seven days
(``retention.sweep_guest_data``).

A count followed by an insert holds only if nobody inserts in between, so the
per-address counts run under the advisory lock ``guest-address:{hash}`` and
the per-list count under ``shared-list-day:{list id}``, both held until
commit; the per-event and per-organiser counts are not serialised across
addresses and may overshoot by the number of concurrent senders, which a
coarse fence can afford. The locks are taken under ``settings.TESTING`` too;
only the counting is skipped there, as for the invitation limits, because the
E2E suite signs the same addresses up all day.

``guest_mail_suppressions`` holds the addresses that answered "Das war ich
nicht" through a link in a mail to them. A suppressed address may still sign
up; it is only never mailed, and the sign-up says ``mail_queued=false``
exactly as without SMTP, so the answer reveals nothing. Only the operator
lifts a suppression, when the address's owner asks (:func:`lift_suppression`).
"""

import datetime as dt
import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.core.errors import raise_problem
from app.core.logger import get_logger
from app.crud.shared_list_guest import shared_list_guest as crud_guest
from app.logic import clock
from app.logic.shared_lists.guest_tokens import address_hash
from app.models.event import Event
from app.models.shared_list import (
    GuestActivityLog,
    GuestMailKind,
    GuestMailSuppression,
)

logger = get_logger(__name__)

_WINDOW = dt.timedelta(hours=24)


def _limits_apply() -> bool:
    return not settings.TESTING


async def _lock(session: AsyncSession, key: str) -> None:
    """A transaction-scoped advisory lock, as ``crud.voucher.lock_ledger`` takes."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": key},
    )


async def lock_address(session: AsyncSession, hashed: str) -> None:
    """Serialise everything one address does until commit: its sign-ups, the
    per-person limit counted by address, and the mails to it."""
    await _lock(session, f"guest-address:{hashed}")


async def lock_account(session: AsyncSession, event_id: uuid.UUID, hashed: str) -> None:
    """Serialise the confirmations of one address at one event until commit,
    so it gets one guest account (``guest_account.confirm``). Taken right
    after the event row and before any guest row; nothing else takes it."""
    await _lock(session, f"guest-account:{event_id}:{hashed}")


async def admit_signup(
    session: AsyncSession, *, hashed: str, event_id: uuid.UUID
) -> None:
    """Take the address's lock and refuse a sign-up over its daily ceilings:
    429 ``shared_list.too_many_for_address``.

    One ceiling counts sign-ups, the other the events signed up for besides
    ``event_id``: an address may sign up again where it already did today.
    """
    await lock_address(session, hashed)
    if not _limits_apply():
        return
    recent = (
        col(GuestActivityLog.kind) == "signup",
        col(GuestActivityLog.address_hash) == hashed,
        col(GuestActivityLog.created_at) > clock.utc_now() - _WINDOW,
    )
    signups = await session.scalar(select(func.count()).where(*recent))
    other_events = await session.scalar(
        select(func.count(func.distinct(col(GuestActivityLog.event_id)))).where(
            *recent, col(GuestActivityLog.event_id) != event_id
        )
    )
    if (signups or 0) >= settings.GUEST_SIGNUPS_PER_ADDRESS_PER_DAY or (
        other_events or 0
    ) >= settings.GUEST_SIGNUP_EVENTS_PER_ADDRESS_PER_DAY:
        raise_problem(
            429,
            code="shared_list.too_many_for_address",
            detail="This address has signed up for enough today. Try again tomorrow.",
        )


async def admit_list_signup(
    session: AsyncSession, *, shared_list_id: uuid.UUID
) -> None:
    """Take the list's day lock and refuse a sign-up over its daily ceiling:
    429 ``shared_list.daily_limit``. Counted in the log, so neither undoing
    nor erasing sign-ups makes room."""
    await _lock(session, f"shared-list-day:{shared_list_id}")
    if not _limits_apply():
        return
    signups = await session.scalar(
        select(func.count()).where(
            col(GuestActivityLog.kind) == "signup",
            col(GuestActivityLog.shared_list_id) == shared_list_id,
            col(GuestActivityLog.created_at) > clock.utc_now() - _WINDOW,
        )
    )
    if (signups or 0) >= settings.SHARED_LIST_SIGNUPS_PER_LIST_PER_DAY:
        raise_problem(
            429,
            code="shared_list.daily_limit",
            detail="This list has taken all the sign-ups it can today",
        )


def record_signup(
    session: AsyncSession,
    *,
    hashed: str | None,
    event_id: uuid.UUID,
    shared_list_id: uuid.UUID,
    booking_id: uuid.UUID,
) -> None:
    """Append the ``signup`` row the ceilings count."""
    session.add(
        GuestActivityLog(
            kind="signup",
            address_hash=hashed,
            event_id=event_id,
            shared_list_id=shared_list_id,
            booking_id=booking_id,
        )
    )


async def _suppressed(session: AsyncSession, hashed: str) -> bool:
    found = await session.scalar(
        select(col(GuestMailSuppression.id)).where(
            col(GuestMailSuppression.address_hash) == hashed
        )
    )
    return found is not None


async def _over_mail_ceiling(
    session: AsyncSession,
    *,
    hashed: str,
    event_id: uuid.UUID,
    organiser_id: uuid.UUID | None,
) -> str | None:
    """Which daily mail ceiling a mail to ``hashed`` about ``event_id`` breaks."""
    since = clock.utc_now() - _WINDOW
    mails = (
        col(GuestActivityLog.kind) != "signup",
        col(GuestActivityLog.created_at) > since,
    )
    to_address = await session.scalar(
        select(func.count()).where(*mails, col(GuestActivityLog.address_hash) == hashed)
    )
    if (to_address or 0) >= settings.GUEST_MAILS_PER_ADDRESS_PER_DAY:
        return "address"
    about_event = await session.scalar(
        select(func.count()).where(*mails, col(GuestActivityLog.event_id) == event_id)
    )
    if (about_event or 0) >= settings.GUEST_MAILS_PER_EVENT_PER_DAY:
        return "event"
    # The organiser deleted their account: the event's ceiling still holds.
    if organiser_id is None:
        return None
    by_organiser = await session.scalar(
        select(func.count()).where(
            *mails, col(GuestActivityLog.organiser_id) == organiser_id
        )
    )
    if (by_organiser or 0) >= settings.GUEST_MAILS_PER_ORGANISER_PER_DAY:
        return "organiser"
    return None


async def _organiser_of(session: AsyncSession, event_id: uuid.UUID) -> uuid.UUID | None:
    return await session.scalar(
        select(col(Event.created_by_id)).where(col(Event.id) == event_id)
    )


async def reserve_mail(
    session: AsyncSession,
    *,
    address: str,
    kind: GuestMailKind,
    event_id: uuid.UUID,
    booking_id: uuid.UUID,
    shared_list_id: uuid.UUID | None = None,
) -> bool:
    """Whether a guest mail may go out; if so, the log row it counts as.

    False without SMTP, for a suppressed address, and over a ceiling; then
    nothing is written. Without SMTP nothing is reserved at all: the
    transactional mail path would log the link instead, and a manage link
    reads, cancels and erases until retention. Log lines name the kind and
    the event, never the address.

    One row per mail, however many shifts it names: the ceilings count
    mails. ``event_id`` is the event the mail names, ``booking_id`` the
    booking it is about, the first of several.
    """
    if not settings.emails_configured:
        logger.info(f"guest mail not sent: SMTP not configured ({kind})")
        return False
    hashed = address_hash(address)
    await lock_address(session, hashed)
    if await _suppressed(session, hashed):
        logger.info(f"guest mail not sent: the address opted out ({kind})")
        return False
    organiser_id = await _organiser_of(session, event_id)
    if _limits_apply():
        ceiling = await _over_mail_ceiling(
            session, hashed=hashed, event_id=event_id, organiser_id=organiser_id
        )
        if ceiling is not None:
            logger.warning(
                f"guest mail not sent: {kind} over the daily {ceiling} ceiling "
                f"(event {event_id})"
            )
            return False
    session.add(
        GuestActivityLog(
            kind=kind,
            address_hash=hashed,
            event_id=event_id,
            shared_list_id=shared_list_id,
            booking_id=booking_id,
            organiser_id=organiser_id,
        )
    )
    await session.flush()
    return True


async def rejection_suppresses(session: AsyncSession, *, address: str) -> bool:
    """Whether "Das war ich nicht" on a chain mailed at ``address`` also stops
    all mail to it. Not while the address has a confirmed guest account at
    any event: the suppression is global, so it would stop the mail about the
    sign-ups the address's owner confirmed too."""
    return not await crud_guest.has_live_account(session, email=address)


async def suppress(session: AsyncSession, *, address: str) -> None:
    """Never mail ``address`` again ("Das war ich nicht")."""
    hashed = address_hash(address)
    await lock_address(session, hashed)
    if not await _suppressed(session, hashed):
        session.add(GuestMailSuppression(address_hash=hashed))
        await session.flush()


async def lift_suppression(session: AsyncSession, *, address: str) -> bool:
    """Mail ``address`` again; False when nothing stopped mail to it."""
    hashed = address_hash(address)
    await lock_address(session, hashed)
    result = cast(
        CursorResult[Any],
        await session.execute(
            delete(GuestMailSuppression).where(
                col(GuestMailSuppression.address_hash) == hashed
            )
        ),
    )
    return result.rowcount > 0
