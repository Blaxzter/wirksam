"""Worked hours per volunteer, per event.

Hours have two sources and only one of them is stored:

* **Shifts** — every confirmed booking on a shift in the event. Nothing is
  written down for these; the duration comes from the shift's own times every
  time it is asked for, so editing a shift corrects everyone's hours with it.
* **Work logs** — minutes an event admin enters by hand for work no shift
  describes (``app.models.work_log``).

A shift counts as *worked* once it has ended and as *upcoming* before that.
Shift times are wall-clock times with no zone attached, compared against naive
UTC "now" — the same convention reminders use (``routes/booking_reminders.py``).
"""

import datetime as dt
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.event_membership import event_membership as crud_membership
from app.crud.work_log import work_log as crud_work_log
from app.models.booking import Booking
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.models.work_log import WorkLog
from app.schemas.event_membership import EventRole
from app.schemas.work_hours import (
    VolunteerHours,
    VolunteerHoursDetail,
    WorkedShift,
    WorkLogRead,
)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def shift_minutes(start: dt.time | None, end: dt.time | None) -> int:
    """Length of a shift in minutes.

    An end at or before the start means the shift runs past midnight
    (22:00–02:00 is four hours, not minus twenty). A shift missing either time
    has no length we could defend, so it counts as zero; callers report how
    many of those there were instead of guessing.
    """
    if start is None or end is None:
        return 0
    start_min = start.hour * 60 + start.minute
    end_min = end.hour * 60 + end.minute
    if end_min <= start_min:
        end_min += 24 * 60
    return end_min - start_min


def shift_ends_at(
    date: dt.date, start: dt.time | None, end: dt.time | None
) -> dt.datetime:
    """When a shift is over. Without an end time, that is the end of its day."""
    if end is None:
        return dt.datetime.combine(date + dt.timedelta(days=1), dt.time())
    ends = dt.datetime.combine(date, end)
    if start is not None and end <= start:
        ends += dt.timedelta(days=1)
    return ends


@dataclass
class _Tally:
    shift_count: int = 0
    shift_minutes: int = 0
    upcoming_shift_count: int = 0
    upcoming_shift_minutes: int = 0
    untimed_shift_count: int = 0
    manual_minutes: int = 0
    shifts: list[WorkedShift] = field(default_factory=list)

    def add_shift(self, shift: WorkedShift) -> None:
        self.shifts.append(shift)
        if not shift.completed:
            self.upcoming_shift_count += 1
            self.upcoming_shift_minutes += shift.minutes
            return
        self.shift_count += 1
        self.shift_minutes += shift.minutes
        if shift.start_time is None or shift.end_time is None:
            self.untimed_shift_count += 1

    def summary(self, user: User, role: EventRole | None) -> VolunteerHours:
        return VolunteerHours(
            user_id=user.id,
            name=user.name,
            email=user.email,
            avatar_etag=user.avatar_etag,
            role=role,
            shift_count=self.shift_count,
            shift_minutes=self.shift_minutes,
            upcoming_shift_count=self.upcoming_shift_count,
            upcoming_shift_minutes=self.upcoming_shift_minutes,
            untimed_shift_count=self.untimed_shift_count,
            manual_minutes=self.manual_minutes,
            total_minutes=self.shift_minutes + self.manual_minutes,
        )


async def _booked_shifts(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None,
    now: dt.datetime,
) -> list[tuple[uuid.UUID, WorkedShift]]:
    query = (
        select(
            col(Booking.id),
            col(Booking.user_id),
            col(Shift.id),
            col(Task.name),
            col(Shift.title),
            col(Shift.date),
            col(Shift.start_time),
            col(Shift.end_time),
        )
        .join(Shift, col(Shift.id) == col(Booking.shift_id))
        .join(Task, col(Task.id) == col(Shift.task_id))
        .where(
            col(Task.event_id) == event_id,
            col(Booking.status) == "confirmed",
        )
        .order_by(col(Shift.date), col(Shift.start_time))
    )
    if user_id is not None:
        query = query.where(col(Booking.user_id) == user_id)
    result = await session.execute(query)

    rows: list[tuple[uuid.UUID, WorkedShift]] = []
    for (
        booking_id,
        booker_id,
        shift_id,
        task_name,
        title,
        date,
        start,
        end,
    ) in result.all():
        rows.append(
            (
                booker_id,
                WorkedShift(
                    booking_id=booking_id,
                    shift_id=shift_id,
                    task_name=task_name,
                    title=title,
                    date=date,
                    start_time=start,
                    end_time=end,
                    minutes=shift_minutes(start, end),
                    completed=shift_ends_at(date, start, end) <= now,
                ),
            )
        )
    return rows


async def _tally(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
    now: dt.datetime | None = None,
) -> tuple[dict[uuid.UUID, _Tally], list[WorkLog]]:
    tallies: dict[uuid.UUID, _Tally] = {}
    for booker_id, shift in await _booked_shifts(
        session, event_id, user_id=user_id, now=now or utc_now()
    ):
        tallies.setdefault(booker_id, _Tally()).add_shift(shift)

    logs = await crud_work_log.list_for_event(
        session, event_id=event_id, user_id=user_id
    )
    for log in logs:
        tallies.setdefault(log.user_id, _Tally()).manual_minutes += log.minutes
    return tallies, logs


async def event_hours(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    now: dt.datetime | None = None,
) -> list[VolunteerHours]:
    """Hours for everyone in the event, plus anyone who has left it with hours.

    A volunteer who worked the weekend and was removed from the event on
    Monday still worked the weekend; dropping them here would make the
    certificate list quietly wrong.
    """
    tallies, _ = await _tally(session, event_id, now=now)

    out: list[VolunteerHours] = []
    seen: set[uuid.UUID] = set()
    for membership, user in await crud_membership.list_members(
        session, event_id=event_id
    ):
        seen.add(user.id)
        tally = tallies.get(user.id, _Tally())
        out.append(tally.summary(user, membership.role))  # type: ignore[arg-type]

    former_ids = [uid for uid in tallies if uid not in seen]
    if former_ids:
        result = await session.execute(
            select(User).where(col(User.id).in_(former_ids)).order_by(col(User.name))
        )
        for user in result.scalars().all():
            out.append(tallies[user.id].summary(user, None))

    out.sort(key=lambda h: (-h.total_minutes, (h.name or h.email or "").lower()))
    return out


async def volunteer_hours(
    session: AsyncSession,
    event_id: uuid.UUID,
    user: User,
    *,
    now: dt.datetime | None = None,
) -> VolunteerHoursDetail:
    """One person's hours in the event, with the shifts and entries behind them."""
    tallies, logs = await _tally(session, event_id, user_id=user.id, now=now)
    tally = tallies.get(user.id, _Tally())
    role = await crud_membership.get_role(session, user_id=user.id, event_id=event_id)
    return VolunteerHoursDetail(
        summary=tally.summary(user, role),
        shifts=tally.shifts,
        work_logs=[WorkLogRead.model_validate(log) for log in logs],
    )
