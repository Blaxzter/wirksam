import datetime as dt
import uuid
from collections.abc import Callable, Mapping
from typing import Any, Literal

from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, aliased
from sqlmodel import col

from app.core.config import settings
from app.crud.base import CRUDBase
from app.logic import clock
from app.models.event import Event
from app.models.shift import Shift
from app.models.task import Task
from app.schemas.shift import ShiftCreate, ShiftUpdate

ShiftSortField = Literal["title", "date", "start_time", "category", "created_at"]

#: "Now" per zone (:func:`wall_clocks`), for a view across events.
WallClocks = Mapping[str, dt.datetime]

# Aliased, so the zone subqueries below mean the same whether or not the query
# around them has joined tasks or events itself.
_zone_task = aliased(Task, name="zone_task")
_zone_event = aliased(Event, name="zone_event")


async def wall_clocks(db: AsyncSession) -> WallClocks:
    """The time on every clock a shift can be on, in one query.

    Every zone any event uses and the setting (for tasks without an event), not
    only those of the events in view: a zone left out would silently drop that
    event's shifts from a list, and almost every installation has one zone.
    """
    result = await db.execute(select(col(Event.timezone)).distinct())
    zones = {settings.EVENT_TIMEZONE, *result.scalars()}
    return {zone: clock.wall_clock_now(zone) for zone in zones}


def task_zone() -> ColumnElement[str]:
    """The zone of the Task row's event, for :func:`on_own_clock`."""
    return func.coalesce(
        select(col(_zone_event.timezone))
        .where(col(_zone_event.id) == col(Task.event_id))
        .correlate(Task)
        .scalar_subquery(),
        settings.EVENT_TIMEZONE,
    )


def shift_zone() -> ColumnElement[str]:
    """The zone of the Shift row's event, for :func:`on_own_clock`."""
    return func.coalesce(
        select(col(_zone_event.timezone))
        .select_from(_zone_task)
        .join(_zone_event, col(_zone_event.id) == col(_zone_task.event_id))
        .where(col(_zone_task.id) == col(Shift.task_id))
        .correlate(Shift)
        .scalar_subquery(),
        settings.EVENT_TIMEZONE,
    )


def on_own_clock(
    clocks: WallClocks,
    zone: ColumnElement[str] | Mapped[str],
    condition: Callable[[dt.datetime], ColumnElement[bool]],
) -> ColumnElement[bool]:
    """``condition(now)``, with each row judged on the clock of its own event.

    One ``or_`` branch per zone, so it stays one query however many events are
    in view. With a single zone in use, the plain condition.
    """
    if len(clocks) == 1:
        return condition(next(iter(clocks.values())))
    return or_(*(and_(zone == name, condition(now)) for name, now in clocks.items()))


def upcoming_condition(clocks: WallClocks) -> ColumnElement[bool]:
    """The Shift row has not started yet, on its event's wall clock.

    Later than today, or today with a start at or after now; a shift with no
    start time counts as not started until its day is over. Shift times carry
    no zone, so comparing them with the server's UTC clock would let an 18:00
    shift in a German summer "start" at 20:00.

    The one definition the task feed, the sidebar and the dashboard's open
    shifts share, so a shift counts as coming up in all three or in none.
    """

    def not_started(now: dt.datetime) -> ColumnElement[bool]:
        return or_(
            col(Shift.date) > now.date(),
            and_(
                col(Shift.date) == now.date(),
                or_(
                    col(Shift.start_time).is_(None),
                    col(Shift.start_time) >= now.time(),
                ),
            ),
        )

    return on_own_clock(clocks, shift_zone(), not_started)


class CRUDShift(CRUDBase[Shift, ShiftCreate, ShiftUpdate]):
    @staticmethod
    def _apply_event_scope(
        query: Select[Any],
        *,
        restrict_to_event_ids: list[uuid.UUID] | None,
        status: str | None = None,
        also_include_event_ids: list[uuid.UUID] | None = None,
        also_include_task_ids: list[uuid.UUID] | None = None,
    ) -> Select[Any]:
        """Limit a shift query to the events the caller may see.

        Shifts carry no event of their own, so the scope has to come through
        their task. ``None`` means unrestricted - the platform superadmin -
        and even then demo tasks are excluded, because a sandbox belongs to one
        guest and nobody else, superadmin included.

        An empty list means "nothing", and must never be allowed to degrade to
        "everything": that is the difference between a new account seeing no
        shifts and seeing every shift in the database.

        ``status`` keeps only shifts of tasks with that status, widened (as on
        the task list) by the events the caller runs and the tasks they are in
        charge of, where drafts are theirs to see.
        """
        query = query.join(Task, col(Shift.task_id) == col(Task.id))
        if restrict_to_event_ids is None:
            query = query.where(col(Task.is_sandbox).is_(False))
        else:
            query = query.where(col(Task.event_id).in_(restrict_to_event_ids))
        if status:
            status_filter = col(Task.status) == status
            if also_include_event_ids:
                status_filter = or_(
                    status_filter, col(Task.event_id).in_(also_include_event_ids)
                )
            if also_include_task_ids:
                status_filter = or_(
                    status_filter, col(Task.id).in_(also_include_task_ids)
                )
            query = query.where(status_filter)
        return query

    async def get_multi_filtered(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        task_id: str | None = None,
        category: str | None = None,
        search: str | None = None,
        sort_by: ShiftSortField = "date",
        sort_dir: Literal["asc", "desc"] = "asc",
        restrict_to_event_ids: list[uuid.UUID] | None = None,
        status: str | None = None,
        also_include_event_ids: list[uuid.UUID] | None = None,
        also_include_task_ids: list[uuid.UUID] | None = None,
    ) -> list[Shift]:
        query = self._apply_event_scope(
            select(Shift),
            restrict_to_event_ids=restrict_to_event_ids,
            status=status,
            also_include_event_ids=also_include_event_ids,
            also_include_task_ids=also_include_task_ids,
        )
        if task_id:
            query = query.where(col(Shift.task_id) == task_id)
        if category:
            query = query.where(col(Shift.category) == category)
        if search:
            query = query.where(
                col(Shift.title).ilike(f"%{search}%")
                | col(Shift.description).ilike(f"%{search}%")
            )
        order_col = getattr(Shift, sort_by)
        query = query.order_by(
            col(order_col).asc() if sort_dir == "asc" else col(order_col).desc()
        )
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_count_filtered(
        self,
        db: AsyncSession,
        *,
        task_id: str | None = None,
        category: str | None = None,
        search: str | None = None,
        restrict_to_event_ids: list[uuid.UUID] | None = None,
        status: str | None = None,
        also_include_event_ids: list[uuid.UUID] | None = None,
        also_include_task_ids: list[uuid.UUID] | None = None,
    ) -> int:
        query = self._apply_event_scope(
            select(func.count()).select_from(Shift),
            restrict_to_event_ids=restrict_to_event_ids,
            status=status,
            also_include_event_ids=also_include_event_ids,
            also_include_task_ids=also_include_task_ids,
        )
        if task_id:
            query = query.where(col(Shift.task_id) == task_id)
        if category:
            query = query.where(col(Shift.category) == category)
        if search:
            query = query.where(
                col(Shift.title).ilike(f"%{search}%")
                | col(Shift.description).ilike(f"%{search}%")
            )
        result = await db.execute(query)
        return result.scalar_one()


shift = CRUDShift(Shift)
