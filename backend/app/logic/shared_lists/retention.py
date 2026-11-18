"""How long what a guest typed is kept: ``GUEST_DATA_RETENTION_DAYS`` after
their own last shift.

Decided per guest *user*, from that user's bookings, never from the event on
the contact row: a task moved to another event takes its bookings along, and
deleting an event leaves its tasks, and their bookings, behind. A guest's
last day is the latest date among their bookings (a booking whose shift was
removed keeps its date in the cancellation snapshot), or the day of their
last sign-up when they have none. The privacy text promises exactly this.
A guest account's clock is therefore its latest pooled shift, for the names
and phones on its pooled bookings too. Vouchers not redeemed by then expire:
anonymising revokes the manage link, so no code can be shown any more.

Shift dates are wall dates, so the days after the last one are counted on a
wall clock too: that of the guest's event, in which their manage page names
the day (:func:`erase_on`), or ``EVENT_TIMEZONE`` once that event is gone.
Counted on UTC, a guest west of it would lose their data, and their unredeemed
vouchers, the evening before the day they were told.

:func:`sweep_guest_data` runs from the reminder poller, about once an hour,
in one transaction. Running it twice changes nothing more.
"""

import datetime as dt
import uuid
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import CursorResult, Date, delete, exists, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col

from app.core.config import settings
from app.crud.shared_list_guest import shared_list_guest as crud_guest
from app.crud.shift import WallClocks, on_own_clock, wall_clocks
from app.logic.shared_lists.erase import anonymise
from app.models.booking import Booking
from app.models.event import Event
from app.models.shared_list import GuestActivityLog, SharedListGuest
from app.models.shift import Shift
from app.models.user import User
from app.models.voucher import VoucherEarning, VoucherEntry

#: How long ``guest_activity_log`` rows are kept. The ceilings look back a
#: day; the rest is for looking into abuse after the fact.
ACTIVITY_LOG_DAYS = 7


@dataclass(frozen=True, slots=True)
class SweepResult:
    anonymised: int
    deleted: int
    log_rows_pruned: int


def _last_day() -> ColumnElement[dt.date]:
    """A guest's last day, over a query of ``User`` outer-joined to its
    contact row: the latest date among their bookings, else the day of their
    last sign-up, else the day the user was created."""
    last_booked = (
        select(
            func.max(func.coalesce(col(Shift.date), col(Booking.cancelled_shift_date)))
        )
        .select_from(Booking)
        .outerjoin(Shift, col(Shift.id) == col(Booking.shift_id))
        .where(col(Booking.user_id) == col(User.id))
        .correlate(User)
        .scalar_subquery()
    )
    return func.coalesce(
        last_booked,
        sql_cast(col(SharedListGuest.last_signup_at), Date),
        sql_cast(col(User.created_at), Date),
    )


def _zone() -> ColumnElement[str]:
    """The clock a guest's days are counted on, over the same query as
    :func:`_last_day`: their event's, or the default once it is gone."""
    return func.coalesce(
        select(col(Event.timezone))
        .where(col(Event.id) == col(SharedListGuest.event_id))
        .correlate(SharedListGuest)
        .scalar_subquery(),
        settings.EVENT_TIMEZONE,
    )


async def _due_guests(
    session: AsyncSession,
    *,
    clocks: WallClocks,
    retention_days: int,
    among: Collection[uuid.UUID] | None = None,
) -> list[tuple[uuid.UUID, bool]]:
    """Guest users whose last day is more than ``retention_days`` ago on their
    event's clock, and who still hold something to remove: a name or a phone
    number, on the user or on one of their bookings, or a cancelled booking (a
    removed shift can cancel a booking an erasure kept). Each with whether it
    still has a contact row."""
    query = (
        select(col(User.id), col(SharedListGuest.id).is_not(None))
        .outerjoin(SharedListGuest, col(SharedListGuest.user_id) == col(User.id))
        .where(
            col(User.is_list_guest),
            on_own_clock(
                clocks,
                _zone(),
                lambda now: (
                    _last_day() < now.date() - dt.timedelta(days=retention_days)
                ),
            ),
            or_(
                col(User.name).is_not(None),
                col(User.phone_number).is_not(None),
                exists().where(
                    col(Booking.user_id) == col(User.id),
                    or_(
                        col(Booking.status) == "cancelled",
                        col(Booking.guest_name).is_not(None),
                        col(Booking.guest_phone).is_not(None),
                    ),
                ),
            ),
        )
    )
    if among is not None:
        query = query.where(col(User.id).in_(among))
    result = await session.execute(query)
    return [(user_id, has_row) for user_id, has_row in result.all()]


async def _lock_due(
    session: AsyncSession, *, clocks: WallClocks, retention_days: int
) -> list[uuid.UUID]:
    """The guests due now, their contact rows locked until commit.

    A row another transaction holds is left for the next run rather than
    waited for: a confirmation merging a chain into this account, a sign-up
    adding a shift, an erasure. The others are judged again once locked,
    since such a transaction may have committed a later shift since the
    first look; anonymising then would leave that shift's booking with its
    name and without a manage link.
    """
    due = await _due_guests(session, clocks=clocks, retention_days=retention_days)
    if not due:
        return []
    locked = await crud_guest.lock_unheld(
        session, user_ids=[user_id for user_id, has_row in due if has_row]
    )
    free = [user_id for user_id, has_row in due if not has_row or user_id in locked]
    if not free:
        return []
    still = await _due_guests(
        session, clocks=clocks, retention_days=retention_days, among=free
    )
    return [user_id for user_id, _ in still]


async def erase_on(
    session: AsyncSession, *, user_id: uuid.UUID, retention_days: int
) -> dt.date:
    """The first day the sweep counts this guest as due, on the clock of
    their event: ``retention_days`` after their last day. What the manage
    page tells them."""
    last_day = await session.scalar(
        select(_last_day())
        .select_from(User)
        .outerjoin(SharedListGuest, col(SharedListGuest.user_id) == col(User.id))
        .where(col(User.id) == user_id)
    )
    assert last_day is not None  # the user exists, and was created some day
    return last_day + dt.timedelta(days=retention_days + 1)


async def sweep_guest_data(
    session: AsyncSession, *, now: dt.datetime, retention_days: int
) -> SweepResult:
    """Anonymise the guests whose time is up, delete those with nothing left,
    and prune the activity log. ``now`` is naive UTC.

    1. Due guests lose their cancelled bookings, then everything
       ``erase.anonymise`` takes: names and phones, address, manage link,
       aliases, unused voucher codes and the notes of their corrections. No
       shift of theirs is ahead any more, so what stays are worked shifts,
       kept without a name. Guests whose event was deleted have no contact
       row left; they are anonymised all the same. A guest whose row another
       transaction holds waits for the next run (:func:`_lock_due`).
    2. Anonymous guests without a booking are deleted. Never one with
       bookings: a booking in the event a task moved to outlives the event
       the guest signed up in. Nor one with ledger entries or earnings worth
       something: a CASCADE would take a stand's redemptions with it.
    3. Activity log rows older than :data:`ACTIVITY_LOG_DAYS` go.
    """
    due = await _lock_due(
        session,
        clocks=await wall_clocks(session, at=now),
        retention_days=retention_days,
    )
    if due:
        await session.execute(
            delete(Booking).where(
                col(Booking.user_id).in_(due), col(Booking.status) == "cancelled"
            )
        )
        await anonymise(session, user_ids=due, now=now)
    deleted = cast(
        CursorResult[Any],
        await session.execute(
            delete(User).where(
                col(User.is_list_guest),
                col(User.name).is_(None),
                ~exists().where(col(Booking.user_id) == col(User.id)),
                ~exists().where(col(VoucherEntry.user_id) == col(User.id)),
                ~exists().where(
                    col(VoucherEarning.user_id) == col(User.id),
                    col(VoucherEarning.amount) > 0,
                ),
            )
        ),
    )
    pruned = cast(
        CursorResult[Any],
        await session.execute(
            delete(GuestActivityLog).where(
                col(GuestActivityLog.created_at)
                < now - dt.timedelta(days=ACTIVITY_LOG_DAYS)
            )
        ),
    )
    return SweepResult(
        anonymised=len(due), deleted=deleted.rowcount, log_rows_pruned=pruned.rowcount
    )
