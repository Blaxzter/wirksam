"""Which shifts a shared list offers, and whether it is open, on the event's clock.

A list stores its tasks and the shifts it leaves out; what it offers is worked
out here on every read, never stored. A shift is *included* when its task is on
the list, still in the list's event, published and not limited to a team, and
the shift is not excluded. It is *offered* when, in addition, it has not
started: guests never take a shift that is already running.

"Expired" is derived the same way (:func:`effective_status`), so moving shifts,
changing the event's zone or the event's shift dates never leaves it stale.

Every ``now_wall`` here is the event's wall clock, which callers read with
``clock.wall_clock_now(event.timezone)`` through the module attribute, so a test
can pin it. A list belongs to one event, so one reading serves a whole request.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy import ColumnElement, ScalarSelect, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.booking import Booking
from app.models.event import Event
from app.models.shared_list import SharedList, SharedListExcludedShift, SharedListTask
from app.models.shift import Shift
from app.models.task import Task

#: The status a list shows: the stored one, or ``expired`` when a live list has
#: nothing left to be open for.
EffectiveStatus = Literal["live", "paused", "expired", "ended"]

#: How close to its closing day a date list counts as closing soon.
EXPIRES_SOON_DAYS = 3


@dataclass(frozen=True, slots=True)
class OfferedShift:
    """An included shift with its task and how many confirmed bookings it has."""

    shift: Shift
    task: Task
    confirmed: int

    @property
    def free(self) -> int:
        """Places left. Never negative: ``max_bookings`` can be lowered below
        the bookings a shift already has."""
        return max(0, self.shift.max_bookings - self.confirmed)

    @property
    def starts_at(self) -> dt.datetime:
        return starts_at(self.shift.date, self.shift.start_time)


def starts_at(date: dt.date, start: dt.time | None) -> dt.datetime:
    """When a shift starts on its event's wall clock; 00:00 without a start time.

    The rule of booking's "has started" (``bookings._refuse_if_shift_started``),
    not of ``crud.shift.upcoming_condition``, which keeps an untimed shift
    upcoming all day: a guest must not take a shift whose day has begun.
    """
    return dt.datetime.combine(date, start or dt.time())


def starts_at_sql() -> ColumnElement[dt.datetime]:
    """:func:`starts_at` in SQL: in PostgreSQL ``date + time`` is a timestamp."""
    return col(Shift.date) + func.coalesce(col(Shift.start_time), dt.time())


def confirmed_sql() -> ScalarSelect[int]:
    """The confirmed bookings of the ``Shift`` in the enclosing query.

    Correlated, so it counts through ix_bookings_shift_id_status per shift
    instead of grouping every booking in the database.
    """
    return (
        select(func.count())
        .where(
            col(Booking.shift_id) == col(Shift.id),
            col(Booking.status) == "confirmed",
        )
        .correlate(Shift)
        .scalar_subquery()
    )


class _TaskLike(Protocol):
    @property
    def status(self) -> str: ...

    @property
    def team_id(self) -> uuid.UUID | None: ...


def offerable(task: _TaskLike) -> bool:
    """Whether a list can offer this task's shifts at all, its event aside:
    published, and not limited to a team's members, which a guest never is."""
    return task.status == "published" and task.team_id is None


def effective_status(
    shared_list: SharedList,
    *,
    event: Event,
    last_start: dt.datetime | None,
    now_wall: dt.datetime,
) -> EffectiveStatus:
    """The status to show and to act on.

    ``last_start`` is :func:`last_start` of the list. Paused and ended lists
    stay what they are. A live list is expired when its event is not published
    (any more), when its closing day (inclusive, on the event's clock) is over,
    or, closing with its last shift, once that shift has started or when there
    is none. A list that closes by hand stays live even with nothing to offer.
    """
    if shared_list.status == "ended":
        return "ended"
    if shared_list.status == "paused":
        return "paused"
    if event.status != "published":
        return "expired"
    if shared_list.ends_mode == "date":
        # ends_on is set whenever ends_mode is "date" (ck_shared_lists_ends_on).
        assert shared_list.ends_on is not None
        return "expired" if now_wall.date() > shared_list.ends_on else "live"
    if shared_list.ends_mode == "last_shift" and (
        last_start is None or last_start <= now_wall
    ):
        return "expired"
    return "live"


def closes_at(
    shared_list: SharedList, *, last_start: dt.datetime | None
) -> dt.datetime | None:
    """When the list closes by itself, on the event's clock; None for by hand.

    With its last shift: when that starts. On a day: the end of that day.
    """
    if shared_list.ends_mode == "last_shift":
        return last_start
    if shared_list.ends_mode == "date":
        assert shared_list.ends_on is not None
        return dt.datetime.combine(shared_list.ends_on, dt.time.max)
    return None


def expires_soon(
    shared_list: SharedList, *, effective: EffectiveStatus, now_wall: dt.datetime
) -> bool:
    """A live list closing on a day at most :data:`EXPIRES_SOON_DAYS` away."""
    if effective != "live" or shared_list.ends_mode != "date":
        return False
    assert shared_list.ends_on is not None
    return 0 <= (shared_list.ends_on - now_wall.date()).days <= EXPIRES_SOON_DAYS


def _included(shared_list: SharedList) -> list[ColumnElement[bool]]:
    """The conditions on a ``Shift`` joined to its ``Task`` for being on the list.

    The task's event is checked against the list's although a task leaving the
    event is taken off its lists: a link that survived must still not offer a
    shift of another event.
    """
    listed = select(col(SharedListTask.task_id)).where(
        col(SharedListTask.shared_list_id) == shared_list.id
    )
    excluded = select(col(SharedListExcludedShift.shift_id)).where(
        col(SharedListExcludedShift.shared_list_id) == shared_list.id
    )
    return [
        col(Shift.task_id).in_(listed),
        col(Task.event_id) == shared_list.event_id,
        col(Task.status) == "published",
        col(Task.team_id).is_(None),
        col(Shift.id).not_in(excluded),
    ]


async def last_start(
    session: AsyncSession, shared_list: SharedList
) -> dt.datetime | None:
    """When the list's last included shift starts, started or not; None without one."""
    result = await session.execute(
        select(func.max(starts_at_sql()))
        .select_from(Shift)
        .join(Task, col(Task.id) == col(Shift.task_id))
        .where(*_included(shared_list))
    )
    return result.scalar_one()


async def list_shifts(
    session: AsyncSession,
    shared_list: SharedList,
    *,
    now_wall: dt.datetime,
    include_started: bool = False,
) -> list[OfferedShift]:
    """The shifts the list offers, by day, start (untimed first) and task name.

    ``include_started`` adds the included shifts that have started, so a
    sign-up can tell "this shift has started" from "this list has no such
    shift". The public page and the sign-up read shifts only through here.
    """
    query = (
        select(Shift, Task, confirmed_sql())
        .join(Task, col(Task.id) == col(Shift.task_id))
        .where(*_included(shared_list))
        .order_by(
            col(Shift.date),
            col(Shift.start_time).asc().nulls_first(),
            col(Task.name),
            col(Shift.id),
        )
    )
    if not include_started:
        query = query.where(starts_at_sql() > now_wall)
    result = await session.execute(query)
    return [
        OfferedShift(shift=shift, task=task, confirmed=count)
        for shift, task, count in result.all()
    ]
