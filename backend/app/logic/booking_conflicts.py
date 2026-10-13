"""Detect shifts that overlap a user's own confirmed bookings.

A shift occupies the half-open interval ``[start, end)``, so back-to-back
shifts (one ends at 12:00, the next starts at 12:00) do not clash. An
``end_time`` at or before ``start_time`` means the shift runs past midnight
and ends on the following day, which is why every comparison here works on
full datetimes rather than on times within a day.

A shift without both a start and an end time has no interval and never
clashes: there is nothing to compare it against.
"""

import datetime as dt
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.booking import Booking
from app.models.shift import Shift

Interval = tuple[dt.datetime, dt.datetime]


@dataclass(frozen=True)
class BookedShift:
    """One of the user's confirmed shifts, reduced to what a clash needs."""

    shift: Shift
    start: dt.datetime
    end: dt.datetime


def shift_interval(
    date: dt.date, start_time: dt.time | None, end_time: dt.time | None
) -> Interval | None:
    """Return the ``[start, end)`` datetimes a shift occupies, or None."""
    if start_time is None or end_time is None:
        return None
    start = dt.datetime.combine(date, start_time)
    end = dt.datetime.combine(date, end_time)
    if end <= start:
        end += dt.timedelta(days=1)
    return start, end


def overlaps(a: Interval, b: Interval) -> bool:
    """True when two half-open intervals share any moment."""
    return a[0] < b[1] and b[0] < a[1]


async def load_booked_shifts(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    date_from: dt.date,
    date_to: dt.date,
) -> list[BookedShift]:
    """The user's confirmed, timed shifts that could touch ``[date_from, date_to]``.

    The window is widened by a day on the left, because a shift that starts
    the evening before ``date_from`` can run into it.
    """
    query = (
        select(Shift)
        .join(Booking, col(Booking.shift_id) == col(Shift.id))
        .where(
            col(Booking.user_id) == user_id,
            col(Booking.status) == "confirmed",
            col(Shift.date) >= date_from - dt.timedelta(days=1),
            col(Shift.date) <= date_to,
            col(Shift.start_time).is_not(None),
            col(Shift.end_time).is_not(None),
        )
        .order_by(col(Shift.date), col(Shift.start_time))
    )
    result = await session.execute(query)
    booked: list[BookedShift] = []
    for shift in result.scalars().all():
        interval = shift_interval(shift.date, shift.start_time, shift.end_time)
        if interval is not None:
            booked.append(BookedShift(shift=shift, start=interval[0], end=interval[1]))
    return booked


def find_collision(
    shift_id: uuid.UUID,
    interval: Interval | None,
    booked: Iterable[BookedShift],
) -> BookedShift | None:
    """The first booked shift (other than ``shift_id``) that overlaps ``interval``."""
    if interval is None:
        return None
    for other in booked:
        if other.shift.id != shift_id and overlaps(interval, (other.start, other.end)):
            return other
    return None


async def find_conflicting_booking(
    session: AsyncSession, *, user_id: uuid.UUID, shift: Shift
) -> BookedShift | None:
    """The user's confirmed shift that ``shift`` would overlap, if any."""
    interval = shift_interval(shift.date, shift.start_time, shift.end_time)
    if interval is None:
        return None
    booked = await load_booked_shifts(
        session,
        user_id=user_id,
        date_from=shift.date,
        # An overnight shift reaches into the next day.
        date_to=interval[1].date(),
    )
    return find_collision(shift.id, interval, booked)


class _ShiftEntry(Protocol):
    id: uuid.UUID
    date: dt.date
    start_time: dt.time | None
    end_time: dt.time | None
    is_booked_by_me: bool
    collides_with_my_booking: bool


async def mark_collisions(
    session: AsyncSession, *, user_id: uuid.UUID, entries: Sequence[_ShiftEntry]
) -> None:
    """Set ``collides_with_my_booking`` on shifts the user could not also book.

    Shifts the user already holds are left unmarked: they are the user's own,
    not a clash with them.
    """
    if not entries:
        return
    booked = await load_booked_shifts(
        session,
        user_id=user_id,
        date_from=min(e.date for e in entries),
        date_to=max(e.date for e in entries) + dt.timedelta(days=1),
    )
    if not booked:
        return
    for entry in entries:
        if entry.is_booked_by_me:
            continue
        interval = shift_interval(entry.date, entry.start_time, entry.end_time)
        entry.collides_with_my_booking = (
            find_collision(entry.id, interval, booked) is not None
        )
