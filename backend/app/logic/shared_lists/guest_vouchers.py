"""A guest's vouchers ("Marken"): where they have some, what their page shows
of them, and the code they show at a stand.

A guest of a shared list earns like a member (``logic/vouchers.py``) and
redeems by code only. The code comes from their manage page, through the
public routes the manage token opens, under the members' rules: six
characters, two minutes, single use, and a new one replaces the last.
Whose vouchers they are is the guest user's, a chain's or an account's
(``guest_account.py``).
"""

import datetime as dt
import uuid

from sqlalchemy import Select, select, union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.errors import raise_problem
from app.crud.event import event as crud_event
from app.logic import clock, vouchers
from app.logic.work_hours import counts_as_worked
from app.models.booking import Booking
from app.models.event import Event
from app.models.shared_list import SharedListGuest
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.models.voucher import VoucherEarning, VoucherEntry, VoucherPass
from app.schemas.public_shared_list import GuestVoucherAccount
from app.schemas.voucher import VoucherPassRead, VoucherPassStatus


def _booked_event_ids(
    user_id: uuid.UUID, *, earning_only: bool
) -> Select[uuid.UUID | None]:
    """The events of the guest's confirmed bookings, on tasks that earn
    vouchers or on any task."""
    query = (
        select(col(Task.event_id))
        .select_from(Booking)
        .join(Shift, col(Shift.id) == col(Booking.shift_id))
        .join(Task, col(Task.id) == col(Shift.task_id))
        .where(
            col(Booking.user_id) == user_id,
            counts_as_worked(),
            col(Task.event_id).is_not(None),
        )
    )
    if earning_only:
        query = query.where(col(Task.vouchers_per_shift) > 0)
    return query


async def voucher_event_ids(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[uuid.UUID]:
    """The events in which the guest has, or will have, vouchers: confirmed
    bookings on tasks that earn some, earnings worth something, ledger
    entries, and unused codes.

    Usually one. A task moved to another event makes two: what it earns
    there is still earned. Drives the vouchers on the manage page and which
    events a code may be asked for.
    """
    result = await session.execute(
        union(
            _booked_event_ids(user_id, earning_only=True),
            select(col(VoucherEarning.event_id)).where(
                col(VoucherEarning.user_id) == user_id, col(VoucherEarning.amount) > 0
            ),
            select(col(VoucherEntry.event_id)).where(
                col(VoucherEntry.user_id) == user_id
            ),
            select(col(VoucherPass.event_id)).where(
                col(VoucherPass.user_id) == user_id, col(VoucherPass.used_at).is_(None)
            ),
        )
    )
    return [event_id for (event_id,) in result.all() if event_id is not None]


async def ledger_event_ids(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[uuid.UUID]:
    """Every event whose ledger lock a merge of this guest must hold.

    Wider than :func:`voucher_event_ids` on purpose: a correction is allowed
    wherever ``vouchers.appears_in_event`` holds, which counts confirmed
    bookings on tasks without vouchers too, and every row of the guest's that
    the merge moves names an event.
    """
    result = await session.execute(
        union(
            _booked_event_ids(user_id, earning_only=False),
            select(col(VoucherEarning.event_id)).where(
                col(VoucherEarning.user_id) == user_id
            ),
            select(col(VoucherEntry.event_id)).where(
                col(VoucherEntry.user_id) == user_id
            ),
            select(col(VoucherPass.event_id)).where(
                col(VoucherPass.user_id) == user_id
            ),
        )
    )
    return [event_id for (event_id,) in result.all() if event_id is not None]


async def guest_vouchers(
    session: AsyncSession, *, user_id: uuid.UUID, own_event_id: uuid.UUID | None
) -> list[GuestVoucherAccount]:
    """The guest's vouchers per event, ``own_event_id`` first, then by date.

    By user id, not by contact row: a guest whose event was deleted has
    none, and may still have vouchers elsewhere (the Art. 15 export). A guest
    page shows no member's name and no organiser's free text, so the entries
    lose ``actor_name`` and ``note``, and the summary its ``email``.
    """
    event_ids = await voucher_event_ids(session, user_id=user_id)
    if not event_ids:
        return []
    user = await session.get(User, user_id)
    assert user is not None  # the caller read the guest's rows
    events = (
        await session.execute(select(Event).where(col(Event.id).in_(event_ids)))
    ).scalars()
    out: list[GuestVoucherAccount] = []
    for event in sorted(
        events, key=lambda e: (e.id != own_event_id, e.start_date, e.name, e.id)
    ):
        account = await vouchers.account(
            session, event.id, user, now=clock.wall_clock_now(event.timezone)
        )
        account.summary.email = None
        for entry in account.entries:
            entry.actor_name = None
            entry.note = None
        out.append(
            GuestVoucherAccount(
                event_id=event.id, event_name=event.name, account=account
            )
        )
    return out


async def issue_pass(
    session: AsyncSession,
    *,
    guest: SharedListGuest,
    event_id: uuid.UUID,
    now_utc: dt.datetime,
) -> VoucherPassRead:
    """A fresh code for the guest in ``event_id``, as members get theirs.

    404 ``guest_signup.not_found`` for an event in which the guest has no
    vouchers: one answer for every failure, as for tokens. No ledger lock, as
    for members.
    """
    if event_id not in await voucher_event_ids(session, user_id=guest.user_id):
        raise_problem(
            404,
            code="guest_signup.not_found",
            detail="This link does not work (any more)",
        )
    event = await session.get(Event, event_id)
    assert event is not None  # it holds the guest's vouchers
    p = await vouchers.issue_pass(
        session, event_id=event_id, user_id=guest.user_id, now=now_utc
    )
    return vouchers.pass_read(p, event_name=event.name)


async def pass_status(
    session: AsyncSession,
    *,
    guest: SharedListGuest,
    event_id: uuid.UUID,
    pass_id: uuid.UUID,
) -> VoucherPassStatus:
    """What happened to one of the guest's codes, on the event's clock.

    404 ``voucher.pass_not_found`` once it was replaced, or deleted by a
    confirmation: the code screen then asks for a new one.
    """
    zone = await crud_event.zone_of(session, event_id)
    return await vouchers.pass_status(
        session,
        event_id=event_id,
        user_id=guest.user_id,
        pass_id=pass_id,
        utc_now=clock.utc_now(),
        wall_now=clock.wall_clock_now(zone),
    )
