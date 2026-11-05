"""Detect shifts that overlap a user's own confirmed bookings.

A shift occupies the half-open interval ``[start, end)``, so back-to-back
shifts (one ends at 12:00, the next starts at 12:00) do not clash. An
``end_time`` at or before ``start_time`` means the shift runs past midnight
and ends on the following day, which is why every comparison here works on
full datetimes rather than on times within a day.

A shift without both a start and an end time has no interval and never
clashes: there is nothing to compare it against.

Shift times carry no zone and are read on the clock of the shift's event. Two
shifts on one clock compare as written. Two on different clocks compare as
instants, because 10:00 in Tokyo and 10:00 in Berlin are hours apart while 11:00
in Berlin and 10:00 in Lisbon are the same moment.
"""

import datetime as dt
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.crud.shift import WallClocks, shift_zone, wall_clocks
from app.logic import clock
from app.models.booking import Booking
from app.models.shift import Shift

Interval = tuple[dt.datetime, dt.datetime]

#: How far apart one moment's dates can be on two clocks: UTC-12 and UTC+14 are
#: 26 hours apart, which reaches into the second day either way.
ZONE_MARGIN = dt.timedelta(days=2)


@dataclass(frozen=True)
class BookedShift:
    """One of the user's confirmed shifts, reduced to what a clash needs."""

    shift: Shift
    start: dt.datetime
    end: dt.datetime
    #: The zone ``start`` and ``end`` are in.
    zone: str


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


def _in_utc(interval: Interval, zone: str) -> Interval:
    return (
        clock.wall_clock_to_utc(interval[0], zone),
        clock.wall_clock_to_utc(interval[1], zone),
    )


def clash(a: Interval, a_zone: str, b: Interval, b_zone: str) -> bool:
    """True when two shifts share a moment, each read in its own zone."""
    if a_zone == b_zone:
        return overlaps(a, b)
    return overlaps(_in_utc(a, a_zone), _in_utc(b, b_zone))


async def load_booked_shifts(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    date_from: dt.date,
    date_to: dt.date,
    clocks: WallClocks,
) -> list[BookedShift]:
    """The user's confirmed, timed shifts that could touch ``[date_from, date_to]``.

    The window is widened by a day on the left, because a shift that starts
    the evening before ``date_from`` can run into it. On an installation whose
    events are in several zones it widens further and reads each shift's zone;
    with one zone in use the query needs neither.
    """
    several_zones = len(clocks) > 1
    margin = ZONE_MARGIN if several_zones else dt.timedelta()
    query = (
        select(Shift)
        .join(Booking, col(Booking.shift_id) == col(Shift.id))
        .where(
            col(Booking.user_id) == user_id,
            col(Booking.status) == "confirmed",
            col(Shift.date) >= date_from - dt.timedelta(days=1) - margin,
            col(Shift.date) <= date_to + margin,
            col(Shift.start_time).is_not(None),
            col(Shift.end_time).is_not(None),
        )
        .order_by(col(Shift.date), col(Shift.start_time))
    )
    if several_zones:
        query = query.add_columns(shift_zone())
    rows: Sequence[Any] = (await session.execute(query)).all()
    booked: list[BookedShift] = []
    for row in rows:
        shift: Shift = row[0]
        zone: str = row[1] if several_zones else next(iter(clocks))
        interval = shift_interval(shift.date, shift.start_time, shift.end_time)
        if interval is not None:
            booked.append(
                BookedShift(shift=shift, start=interval[0], end=interval[1], zone=zone)
            )
    return booked


def find_collision(
    shift_id: uuid.UUID,
    interval: Interval | None,
    zone: str,
    booked: Iterable[BookedShift],
) -> BookedShift | None:
    """The first booked shift (other than ``shift_id``) that overlaps ``interval``,
    which is in ``zone``."""
    if interval is None:
        return None
    for other in booked:
        if other.shift.id != shift_id and clash(
            interval, zone, (other.start, other.end), other.zone
        ):
            return other
    return None


async def find_conflicting_booking(
    session: AsyncSession, *, user_id: uuid.UUID, shift: Shift, zone: str | None
) -> BookedShift | None:
    """The user's confirmed shift that ``shift`` would overlap, if any.

    ``zone`` is that of the shift's event, as ``crud.event.zone_of`` gives it.
    """
    interval = shift_interval(shift.date, shift.start_time, shift.end_time)
    if interval is None:
        return None
    booked = await load_booked_shifts(
        session,
        user_id=user_id,
        date_from=shift.date,
        # An overnight shift reaches into the next day.
        date_to=interval[1].date(),
        clocks=await wall_clocks(session),
    )
    return find_collision(shift.id, interval, zone or settings.EVENT_TIMEZONE, booked)


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
    clocks = await wall_clocks(session)
    booked = await load_booked_shifts(
        session,
        user_id=user_id,
        date_from=min(e.date for e in entries),
        date_to=max(e.date for e in entries) + dt.timedelta(days=1),
        clocks=clocks,
    )
    if not booked:
        return
    zones = await _zones_of_shifts(session, [e.id for e in entries], clocks)
    for entry in entries:
        if entry.is_booked_by_me:
            continue
        interval = shift_interval(entry.date, entry.start_time, entry.end_time)
        zone = zones.get(entry.id, settings.EVENT_TIMEZONE)
        entry.collides_with_my_booking = (
            find_collision(entry.id, interval, zone, booked) is not None
        )


async def _zones_of_shifts(
    session: AsyncSession, shift_ids: list[uuid.UUID], clocks: WallClocks
) -> dict[uuid.UUID, str]:
    """``{shift_id: zone}`` for a page of shifts; no query with one zone in use."""
    if len(clocks) == 1:
        only = next(iter(clocks))
        return dict.fromkeys(shift_ids, only)
    result = await session.execute(
        select(col(Shift.id), shift_zone()).where(col(Shift.id).in_(shift_ids))
    )
    return {row[0]: row[1] for row in result.all()}
