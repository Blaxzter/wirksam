"""Confirming a guest's address: one guest account per event and address.

Someone opens the link in a mail to a sign-up chain and presses "Ja, das bin
ich" (``POST /public/guest-signups/confirm``). Only a mail link can confirm,
since anyone can type anyone's address into a form. Then:

- if the address has no account at that event yet, the chain **becomes** it,
  in place: ``confirmed_at`` is set, and nothing moves;
- otherwise the chain is **merged** into the account (:func:`merge_guest`):
  its bookings, reminders, earnings and ledger entries move to the account's
  user, and its user is deleted. An alias keeps its old mail links working.

Either way the chain's unused voucher codes are deleted, and the token its
sign-up answered with stops working (``guest_tokens.resolve``): whoever only
typed the address loses the chain, and with it every code shown from it.
Each booking keeps its own name, phone and first-name consent, so pooling
adds vouchers up and never puts one person's name on another's shift.

Locks, in this order (docs/SHARED_LISTS.md has the whole table): the event
row ``FOR KEY SHARE``, ``guest-account:{event_id}:{address hash}``, the guest
rows of the chain and the account in one statement, and for a merge then the
ledger locks of both users in every event the chain's rows name, and last the
chain's ``users`` row. :func:`confirm` is the only code that promotes or
merges guest users.
"""

import datetime as dt
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, NoReturn, cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.core.errors import raise_problem
from app.core.logger import get_logger
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.crud.event import event as crud_event
from app.crud.shared_list_guest import shared_list_guest as crud_guest
from app.crud.voucher import voucher as crud_voucher
from app.logic import clock, vouchers
from app.logic.shared_lists import guest_quota, guest_tokens, guest_vouchers
from app.logic.shared_lists.guest_tokens import GuestKey, Peeked
from app.models.booking import Booking
from app.models.event import Event
from app.models.shared_list import SharedListGuest, SharedListGuestAlias
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MergeResult:
    #: Bookings now the target's.
    moved: int
    #: Bookings deleted because both had one on the same shift.
    dropped: int
    #: The source's unused voucher codes, deleted.
    passes_deleted: int


def _not_found() -> NoReturn:
    raise_problem(
        404, code="guest_signup.not_found", detail="This link does not work (any more)"
    )


def _mail_link_required() -> NoReturn:
    raise_problem(
        403,
        code="guest_signup.mail_link_required",
        detail="Only the link in the mail can confirm the address",
    )


async def confirm(
    session: AsyncSession, *, peeked: Peeked, token: str, now: dt.datetime
) -> GuestKey:
    """Confirm the address of the chain behind a mail token; returns the
    account's key (``from_mail``). ``now`` is naive UTC.

    ``peeked`` is the token's row or alias as :func:`guest_tokens.peek` read
    it, verified and alive, without a lock; a retired response token never
    gets here. Confirming an account, or a merged chain's link, answers with
    the account again. 403 ``guest_signup.mail_link_required`` for a live
    chain's response token, 404 ``guest_signup.not_found`` for a chain
    without an address, and for one erased in the meantime.
    """
    if peeked.alias is not None or (
        peeked.guest is not None and peeked.guest.confirmed_at is not None
    ):
        # Confirmed already, promoted or merged: only a mail token opens it.
        key = await guest_tokens.resolve(session, token)
        if key is None:
            _not_found()
        return key
    chain = peeked.guest
    assert chain is not None  # Peeked holds a row or an alias
    if not peeked.from_mail:
        _mail_link_required()
    email = chain.email
    if email is None:
        # A list that asks for no address: there is nothing to confirm.
        _not_found()

    event = await crud_event.lock(session, chain.event_id, mode="key_share")
    if event is None:
        _not_found()
    await guest_quota.lock_account(session, event.id, guest_tokens.address_hash(email))
    found = await crud_guest.find_account(session, event_id=event.id, email=email)
    locked = await crud_guest.lock_many(
        session,
        user_ids={chain.user_id} | ({found.user_id} if found is not None else set()),
    )

    # Again under the lock: the chain may have been erased, or confirmed by a
    # second press of the same link, in between.
    key = await guest_tokens.resolve(session, token)
    if key is None:
        _not_found()
    if not key.from_mail:
        _mail_link_required()
    if key.guest.confirmed_at is not None:
        return key
    chain = key.guest

    # An erase does not take the account lock, so it may have won the race
    # since the account was found, anonymising the row or deleting it with its
    # user; then this chain becomes the account.
    account = locked.get(found.user_id) if found is not None else None
    if account is not None and (
        account.confirmed_at is None
        or account.erased_at is not None
        or account.event_id != chain.event_id
        or account.email != email
    ):
        account = None

    if account is None:
        chain.confirmed_at = now
        session.add(chain)
        await crud_voucher.delete_unused_passes(session, user_ids=[chain.user_id])
        # uq_shared_list_guests_account is the backstop, unreachable under the
        # account lock; a violation stays a 500.
        await session.flush()
        return GuestKey(guest=chain, from_mail=True)

    await _lock_ledgers(session, chain=chain, account=account)
    # Last, after every ledger lock: a redemption holding one inserts its
    # entry under this row's key-share lock.
    await crud_guest.lock_guest_user(session, user_id=chain.user_id)
    await merge_guest(session, source=chain, target_user_id=account.user_id)
    # Name, phone and language stay the account's: each booking carries its
    # own person, so nothing is copied from the chain.
    account.last_signup_at = max(account.last_signup_at, chain.last_signup_at)
    session.add(account)
    assert chain.manage_nonce is not None  # resolve() found it alive
    session.add(
        SharedListGuestAlias(
            user_id=chain.user_id,
            manage_nonce=chain.manage_nonce,
            account_user_id=account.user_id,
        )
    )
    # Its contact row goes by CASCADE.
    await session.execute(
        delete(User).where(col(User.id) == chain.user_id, col(User.is_list_guest))
    )
    return GuestKey(guest=account, from_mail=True)


async def _lock_ledgers(
    session: AsyncSession, *, chain: SharedListGuest, account: SharedListGuest
) -> None:
    """Both users' ledger locks in every event the chain's rows name, sorted.

    A redemption or a correction for the chain lands before the merge and
    moves with it, or comes after and finds the chain gone.
    """
    events = await guest_vouchers.ledger_event_ids(session, user_id=chain.user_id)
    pairs = sorted(
        (str(event_id), str(user_id), event_id, user_id)
        for event_id in events
        for user_id in (chain.user_id, account.user_id)
    )
    for _, _, event_id, user_id in pairs:
        await crud_voucher.lock_ledger(session, event_id=event_id, user_id=user_id)


async def merge_guest(
    session: AsyncSession, *, source: SharedListGuest, target_user_id: uuid.UUID
) -> MergeResult:
    """Move everything of ``source``'s user to ``target_user_id``.

    Takes no locks: the caller holds both guest rows, both users' ledger
    locks in every event the source's rows name, and the source's ``users``
    row. Leaves the source user in place for the caller, and
    ``guest_activity_log`` alone (it holds no user ids, and booking ids
    survive). The target may be any user, so claiming sign-ups into a real
    account can use it later.
    """
    # A code on a screen now belongs to whoever held the chain's tokens, who
    # may only have typed the address: moved, it would spend the pooled
    # vouchers. The confirmer's code dialog asks for a new one.
    passes_deleted = await crud_voucher.delete_unused_passes(
        session, user_ids=[source.user_id]
    )
    drops, both_confirmed = await _collisions(
        session, source=source.user_id, target=target_user_id
    )
    if both_confirmed:
        # Cannot arise: the same address is never confirmed twice on a shift.
        # Should it, the dropped booking's ended shift keeps what it earned.
        await _settle(session, both_confirmed)
        logger.warning(
            f"guest merge: {len(both_confirmed)} shift(s) confirmed on both sides"
        )
    if drops:
        # Their reminders go by CASCADE.
        await session.execute(delete(Booking).where(col(Booking.id).in_(drops)))
    moved = cast(
        CursorResult[Any],
        await session.execute(
            update(Booking)
            .where(col(Booking.user_id) == source.user_id)
            .values(user_id=target_user_id)
        ),
    ).rowcount
    await crud_reminder.reassign_user(
        session, from_user=source.user_id, to_user=target_user_id
    )
    # Earnings and entries move to whose bookings they are now; of the codes
    # only used ones are left, kept for the history.
    await crud_voucher.reassign_user(
        session, from_user=source.user_id, to_user=target_user_id
    )
    return MergeResult(moved=moved, dropped=len(drops), passes_deleted=passes_deleted)


async def _collisions(
    session: AsyncSession, *, source: uuid.UUID, target: uuid.UUID
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """The bookings to drop because both users have one on the same shift
    (``uq_booking_shift_user`` covers every status), and the shifts both had
    confirmed. The source's goes, unless only it is confirmed."""
    rows = await session.execute(
        select(
            col(Booking.id),
            col(Booking.user_id),
            col(Booking.shift_id),
            col(Booking.status),
        ).where(
            col(Booking.user_id).in_([source, target]),
            col(Booking.shift_id).is_not(None),
        )
    )
    by_shift: dict[uuid.UUID, dict[uuid.UUID, tuple[uuid.UUID, str]]] = defaultdict(
        dict
    )
    for booking_id, user_id, shift_id, status in rows.all():
        assert shift_id is not None  # filtered above; for the checker
        by_shift[shift_id][user_id] = (booking_id, status)
    drops: list[uuid.UUID] = []
    both_confirmed: list[uuid.UUID] = []
    for shift_id, held in by_shift.items():
        if len(held) < 2:
            continue
        (source_id, source_status), (target_id, target_status) = (
            held[source],
            held[target],
        )
        if source_status == "confirmed" and target_status == "confirmed":
            both_confirmed.append(shift_id)
        if source_status == "confirmed" and target_status != "confirmed":
            drops.append(target_id)
        else:
            drops.append(source_id)
    return drops, both_confirmed


async def _settle(session: AsyncSession, shift_ids: list[uuid.UUID]) -> None:
    """Settle these shifts, each on its own event's clock, so a booking
    dropped from one keeps what its ended shift earned (earned is earned)."""
    rows = await session.execute(
        select(col(Shift.id), col(Event.timezone))
        .join(Task, col(Task.id) == col(Shift.task_id))
        .outerjoin(Event, col(Event.id) == col(Task.event_id))
        .where(col(Shift.id).in_(shift_ids))
    )
    by_zone: dict[str, list[uuid.UUID]] = defaultdict(list)
    for shift_id, zone in rows.all():
        by_zone[zone or settings.EVENT_TIMEZONE].append(shift_id)
    for zone, ids in by_zone.items():
        await vouchers.settle_earnings(
            session, now=clock.wall_clock_now(zone), shift_ids=ids
        )
