"""Erasing guests who signed up through a shared list.

One rule for every way it happens: the guest's own "Meine Daten löschen" and
"Das war ich nicht", an event admin removing sign-ups with ``erase``, the
operator answering a request (``POST /list-guests/{id}/erase``), and, for the
anonymising part, the retention sweep.

What goes: every booking whose shift is not over yet, which frees the place
at once, and every cancelled one (their reminders go with them). What stays:
confirmed bookings of shifts that are over, without a name, so fill rates and
hours remain true. The guest user and its kept bookings lose their names and
phone numbers, the contact row its address and its manage link
(``manage_nonce``), a guest account the aliases of the chains merged into it.
Unused voucher codes are deleted, and vouchers not redeemed expire with the
manage link: no code can be shown any more. A guest with no booking left is
deleted outright, unless it has ledger entries or earnings worth something:
deleting it would CASCADE away a stand's redemptions.

Erasing a guest account erases everything pooled in it, and nothing else: a
chain with the same address that nobody confirmed stays.

Only ever a guest's: an account that is not ``is_list_guest`` is left alone
whatever id it is given, so no booking that came through a list can take a
member's account or bookings with it.

``guest_activity_log`` is never touched: erasing must not reset a daily
ceiling.
"""

import datetime as dt
import uuid
from collections.abc import Collection, Sequence
from typing import cast

from sqlalchemy import delete, exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.crud.shift import wall_clocks
from app.crud.voucher import voucher as crud_voucher
from app.logic.work_hours import shift_ends_at
from app.models.booking import Booking
from app.models.event import Event
from app.models.shared_list import SharedListGuest, SharedListGuestAlias
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.models.voucher import VoucherEarning, VoucherEntry

#: A guest's booking, when its shift runs and on which clock. Outer joins: the
#: shift's columns are None for a booking whose shift was removed, and the
#: zone for a task without an event.
_BookingRow = tuple[
    uuid.UUID,
    uuid.UUID,
    str,
    dt.date | None,
    dt.time | None,
    dt.time | None,
    str | None,
]


async def anonymise(
    session: AsyncSession, *, user_ids: Collection[uuid.UUID], now: dt.datetime
) -> None:
    """Strip guests of what names or reaches them; ``now`` is naive UTC.

    Their contact rows are marked erased once, so ``erased_at`` says when.
    The notes of their corrections go too: a note is free text, and the
    natural one names the person. The amounts stay, so the books still add
    up. A booking without a name is never named, so ``show_first_name`` may
    stay.
    """
    guests = list(
        (
            await session.execute(
                select(col(User.id)).where(
                    col(User.id).in_(user_ids), col(User.is_list_guest)
                )
            )
        ).scalars()
    )
    if not guests:
        return
    await session.execute(
        update(User)
        .where(col(User.id).in_(guests))
        .values(name=None, phone_number=None)
    )
    await session.execute(
        update(Booking)
        .where(col(Booking.user_id).in_(guests))
        .values(guest_name=None, guest_phone=None)
    )
    await session.execute(
        update(SharedListGuest)
        .where(
            col(SharedListGuest.user_id).in_(guests),
            col(SharedListGuest.erased_at).is_(None),
        )
        .values(email=None, manage_nonce=None, erased_at=now)
    )
    await session.execute(
        delete(SharedListGuestAlias).where(
            col(SharedListGuestAlias.account_user_id).in_(guests)
        )
    )
    await crud_voucher.delete_unused_passes(session, user_ids=guests)
    await session.execute(
        update(VoucherEntry)
        .where(
            col(VoucherEntry.user_id).in_(guests),
            col(VoucherEntry.kind) == "adjustment",
        )
        .values(note=None)
    )


async def erase_guests(
    session: AsyncSession, *, user_ids: Collection[uuid.UUID], now: dt.datetime
) -> int:
    """Erase these guests, in a fixed number of statements; ``now`` is naive UTC.
    Returns how many confirmed bookings went: the sign-ups whose shift was
    still ahead.

    The caller holds their contact rows ``FOR UPDATE`` (a guest whose event
    was deleted has none). Whether a shift is over is judged on the clock of
    its own event: a moved task takes its bookings to another one.
    """
    keeping: set[uuid.UUID] = set(
        (
            await session.execute(
                select(col(User.id)).where(
                    col(User.id).in_(user_ids),
                    col(User.is_list_guest),
                    or_(
                        exists().where(col(VoucherEntry.user_id) == col(User.id)),
                        exists().where(
                            col(VoucherEarning.user_id) == col(User.id),
                            col(VoucherEarning.amount) > 0,
                        ),
                    ),
                )
            )
        ).scalars()
    )
    rows = await session.execute(
        select(
            col(Booking.id),
            col(Booking.user_id),
            col(Booking.status),
            col(Shift.date),
            col(Shift.start_time),
            col(Shift.end_time),
            col(Event.timezone),
        )
        .join(User, col(User.id) == col(Booking.user_id))
        .outerjoin(Shift, col(Shift.id) == col(Booking.shift_id))
        .outerjoin(Task, col(Task.id) == col(Shift.task_id))
        .outerjoin(Event, col(Event.id) == col(Task.event_id))
        .where(col(Booking.user_id).in_(user_ids), col(User.is_list_guest))
    )
    clocks = await wall_clocks(session)
    gone: list[uuid.UUID] = []
    confirmed_gone = 0
    for booking_id, user_id, status, date, start, end, zone in cast(
        Sequence[_BookingRow], rows.all()
    ):
        if (
            status == "confirmed"
            and date is not None
            and shift_ends_at(date, start, end)
            <= clocks[zone or settings.EVENT_TIMEZONE]
        ):
            keeping.add(user_id)
        else:
            gone.append(booking_id)
            if status == "confirmed":
                confirmed_gone += 1
    if gone:
        await session.execute(delete(Booking).where(col(Booking.id).in_(gone)))
    leaving = [user_id for user_id in user_ids if user_id not in keeping]
    if leaving:
        # Their contact rows, and with them the addresses, go by CASCADE.
        await session.execute(
            delete(User).where(col(User.id).in_(leaving), col(User.is_list_guest))
        )
    if keeping:
        await anonymise(session, user_ids=keeping, now=now)
    return confirmed_gone
