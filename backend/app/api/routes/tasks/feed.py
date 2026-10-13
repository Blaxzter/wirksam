# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false
# SQLAlchemy column-level selects produce types that basedpyright cannot resolve.
import datetime as dt
import uuid
from collections import defaultdict

from fastapi import APIRouter, Query
from sqlalchemy import case, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.event_membership import event_membership as crud_membership
from app.crud.task import task as crud_task
from app.logic.booking_conflicts import mark_collisions
from app.logic.event_scope import get_user_event_scope, get_visible_event_ids
from app.logic.permissions import get_event_role
from app.models.booking import Booking
from app.models.shift import Shift
from app.models.task import Task
from app.schemas.feed import (
    FeedFocusMode,
    FeedShiftEntry,
    FeedTaskItem,
    FeedView,
    ShiftWindowResponse,
    TaskFeedResponse,
)
from app.schemas.task import TaskRead

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_shift(row) -> FeedShiftEntry:  # noqa: ANN001 – SA Row is untyped
    return FeedShiftEntry(
        id=row.id,
        date=row.date,
        start_time=row.start_time,
        end_time=row.end_time,
        max_bookings=row.max_bookings,
        current_bookings=row.current_bookings,
        is_booked_by_me=bool(row.is_booked_by_me),
    )


def _shift_select(cnt_sub, my_booking_exists):  # noqa: ANN001, ANN202
    """Base SELECT for shift queries with booking counts."""
    return select(
        col(Shift.id),
        col(Shift.task_id),
        col(Shift.date),
        col(Shift.start_time),
        col(Shift.end_time),
        col(Shift.max_bookings),
        func.coalesce(cnt_sub.c.cnt, 0).label("current_bookings"),
        my_booking_exists.label("is_booked_by_me"),
    ).outerjoin(cnt_sub, col(Shift.id) == cnt_sub.c.shift_id)


def _booking_count_sub():  # noqa: ANN202
    return (
        select(
            col(Booking.shift_id),
            func.count().label("cnt"),
        )
        .where(col(Booking.status) == "confirmed")
        .group_by(col(Booking.shift_id))
        .subquery("cnt_sub")
    )


def _my_booking_exists(user_id: uuid.UUID):  # noqa: ANN202
    return (
        select(literal_column("1"))
        .where(
            col(Booking.shift_id) == col(Shift.id),
            col(Booking.user_id) == user_id,
            col(Booking.status) == "confirmed",
        )
        .correlate(Shift)
        .exists()
    )


async def _query_shifts_with_bookings(
    session: AsyncSession,
    task_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> list[tuple[uuid.UUID, FeedShiftEntry]]:
    """Return (task_id, FeedShiftEntry) pairs for shifts in the given window."""
    if not task_ids:
        return []

    cnt_sub = _booking_count_sub()
    my_exists = _my_booking_exists(user_id)
    query = _shift_select(cnt_sub, my_exists).where(col(Shift.task_id).in_(task_ids))

    if date_from is not None:
        query = query.where(col(Shift.date) >= date_from)
    if date_to is not None:
        query = query.where(col(Shift.date) <= date_to)

    query = query.order_by(col(Shift.date), col(Shift.start_time))
    result = await session.execute(query)
    pairs = [(row.task_id, _row_to_shift(row)) for row in result.all()]
    await mark_collisions(
        session, user_id=user_id, entries=[entry for _, entry in pairs]
    )
    return pairs


async def _query_shifts_first_available(
    session: AsyncSession,
    task_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    today: dt.date,
    days: int,
) -> tuple[dict[uuid.UUID, list[FeedShiftEntry]], dict[uuid.UUID, dt.date]]:
    """For first-available mode: per-task 5-day window starting from the first shift date.

    Returns (shifts_by_task, window_starts).
    """
    # CTE: first shift date >= today per task
    first_dates_cte = (
        select(
            col(Shift.task_id),
            func.min(col(Shift.date)).label("first_date"),
        )
        .where(
            col(Shift.task_id).in_(task_ids),
            col(Shift.date) >= today,
        )
        .group_by(col(Shift.task_id))
        .cte("first_dates")
    )

    cnt_sub = _booking_count_sub()
    my_exists = _my_booking_exists(user_id)

    query = (
        _shift_select(cnt_sub, my_exists)
        .join(first_dates_cte, col(Shift.task_id) == first_dates_cte.c.task_id)
        .where(
            col(Shift.date) >= first_dates_cte.c.first_date,
            col(Shift.date) <= first_dates_cte.c.first_date + (days - 1),
        )
        .order_by(col(Shift.date), col(Shift.start_time))
    )

    result = await session.execute(query)
    shifts_by_task: dict[uuid.UUID, list[FeedShiftEntry]] = defaultdict(list)
    window_starts: dict[uuid.UUID, dt.date] = {}
    for row in result.all():
        shifts_by_task[row.task_id].append(_row_to_shift(row))
    await mark_collisions(
        session,
        user_id=user_id,
        entries=[e for entries in shifts_by_task.values() for e in entries],
    )

    # Derive window starts from the CTE result (query it once more, lightweight)
    fd_query = select(
        first_dates_cte.c.task_id,
        first_dates_cte.c.first_date,
    )
    fd_result = await session.execute(fd_query)
    for row in fd_result.all():
        window_starts[row.task_id] = row.first_date

    return dict(shifts_by_task), window_starts


async def _get_aggregated_stats(
    session: AsyncSession,
    task_ids: list[uuid.UUID],
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> dict[uuid.UUID, tuple[int, int]]:
    """Return {task_id: (total_shifts, available_shifts)}."""
    if not task_ids:
        return {}

    cnt_sub = _booking_count_sub()

    query = (
        select(
            col(Shift.task_id),
            func.count().label("total_shifts"),
            func.sum(
                case(
                    (func.coalesce(cnt_sub.c.cnt, 0) < col(Shift.max_bookings), 1),
                    else_=0,
                )
            ).label("available_shifts"),
        )
        .outerjoin(cnt_sub, col(Shift.id) == cnt_sub.c.shift_id)
        .where(col(Shift.task_id).in_(task_ids))
    )

    if date_from is not None:
        query = query.where(col(Shift.date) >= date_from)
    if date_to is not None:
        query = query.where(col(Shift.date) <= date_to)

    query = query.group_by(col(Shift.task_id))
    result = await session.execute(query)
    return {
        row.task_id: (row.total_shifts, int(row.available_shifts or 0))
        for row in result.all()
    }


# ---------------------------------------------------------------------------
# Builders per view
# ---------------------------------------------------------------------------


async def _build_list_feed(
    session: AsyncSession,
    tasks: list[Task],
    task_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    focus_mode: FeedFocusMode,
    days: int,
) -> list[FeedTaskItem]:
    today = dt.date.today()

    if focus_mode == "first_available":
        shifts_by_task, window_starts = await _query_shifts_first_available(
            session, task_ids, user_id, today, days
        )
    else:
        # today-centered: shared window for all tasks
        date_from = today
        date_to = today + dt.timedelta(days=days - 1)
        pairs = await _query_shifts_with_bookings(
            session, task_ids, user_id, date_from, date_to
        )
        shifts_by_task: dict[uuid.UUID, list[FeedShiftEntry]] = defaultdict(list)
        for eid, entry in pairs:
            shifts_by_task[eid].append(entry)
        window_starts = dict.fromkeys(task_ids, today)

    items: list[FeedTaskItem] = []
    for ev in tasks:
        ev_read = TaskRead.model_validate(ev)
        items.append(
            FeedTaskItem(
                **ev_read.model_dump(),
                shifts=shifts_by_task.get(ev.id, []),
                slot_window_start=window_starts.get(ev.id),
            )
        )
    return items


async def _build_aggregated_feed(
    session: AsyncSession,
    tasks: list[Task],
    task_ids: list[uuid.UUID],
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> list[FeedTaskItem]:
    stats = await _get_aggregated_stats(session, task_ids, date_from, date_to)

    items: list[FeedTaskItem] = []
    for ev in tasks:
        ev_read = TaskRead.model_validate(ev)
        total, available = stats.get(ev.id, (0, 0))
        items.append(
            FeedTaskItem(
                **ev_read.model_dump(),
                total_shifts=total,
                available_shifts=available,
            )
        )
    return items


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/feed", response_model=TaskFeedResponse)
async def task_feed(
    session: DBDep,
    current_user: CurrentUser,
    view: FeedView = Query(default="list"),
    focus_mode: FeedFocusMode = Query(default="today"),
    search: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    my_bookings: bool = Query(default=False),
    days: int = Query(default=5, ge=1, le=31),
    event_id: uuid.UUID | None = Query(default=None),
    all_events: bool = Query(default=False),
) -> TaskFeedResponse:
    """Unified feed endpoint — returns tasks with view-specific embedded data.

    Defaults to scoping by the current user's selected event. Pass an explicit
    ``event_id`` to override, or ``all_events=true`` to disable scoping.
    """
    effective_status: str | None = None
    also_include_group_ids: list[uuid.UUID] | None = None

    visible_event_ids = await get_visible_event_ids(session, current_user)
    if visible_event_ids is not None:
        manageable_ids = await crud_membership.list_event_ids_for_user(
            session, user_id=current_user.id, minimum_role="admin"
        )
        effective_status = "published"
        if manageable_ids:
            also_include_group_ids = manageable_ids

    effective_event_id = event_id
    if effective_event_id is None and not all_events:
        effective_event_id = get_user_event_scope(current_user)

    booked_by_user_id = str(current_user.id) if my_bookings else None

    today = dt.date.today()
    now = dt.datetime.now()
    ev_date_from = date_from if date_from else today
    ev_date_to = date_to if view == "calendar" else None
    # Only enforce future-shift filter when no explicit date_from is provided
    # (i.e. user hasn't picked a custom date range to look at past tasks)
    future_shifts_cutoff = now if (not date_from and view != "calendar") else None

    tasks = await crud_task.get_multi_filtered(
        session,
        skip=skip,
        limit=limit,
        search=search,
        status=effective_status,
        booked_by_user_id=booked_by_user_id,
        date_from=ev_date_from,
        date_to=ev_date_to,
        has_future_shifts=future_shifts_cutoff,
        also_include_group_ids=also_include_group_ids,
        event_id=effective_event_id,
        restrict_to_event_ids=visible_event_ids,
    )
    total = await crud_task.get_count_filtered(
        session,
        search=search,
        status=effective_status,
        booked_by_user_id=booked_by_user_id,
        date_from=ev_date_from,
        date_to=ev_date_to,
        has_future_shifts=future_shifts_cutoff,
        also_include_group_ids=also_include_group_ids,
        event_id=effective_event_id,
        restrict_to_event_ids=visible_event_ids,
    )

    if not tasks:
        return TaskFeedResponse(items=[], total=total, skip=skip, limit=limit)

    task_ids = [e.id for e in tasks]

    if view == "list":
        items = await _build_list_feed(
            session, tasks, task_ids, current_user.id, focus_mode, days
        )
    else:
        # cards and calendar both get aggregated stats
        items = await _build_aggregated_feed(
            session, tasks, task_ids, date_from, date_to
        )

    return TaskFeedResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/active-dates", response_model=list[dt.date])
async def task_active_dates(
    session: DBDep,
    current_user: CurrentUser,
    date_from: dt.date = Query(...),
    date_to: dt.date = Query(...),
) -> list[dt.date]:
    """Return distinct shift dates within a range where published tasks have shifts."""
    query = (
        select(func.distinct(col(Shift.date)))
        .join(Task, col(Shift.task_id) == col(Task.id))
        .where(
            col(Shift.date) >= date_from,
            col(Shift.date) <= date_to,
        )
        .order_by(col(Shift.date))
    )

    visible_event_ids = await get_visible_event_ids(session, current_user)
    if visible_event_ids is not None:
        query = query.where(col(Task.event_id).in_(visible_event_ids))
        manageable_ids = await crud_membership.list_event_ids_for_user(
            session, user_id=current_user.id, minimum_role="admin"
        )
        status_filter = col(Task.status) == "published"
        if manageable_ids:
            status_filter = or_(status_filter, col(Task.event_id).in_(manageable_ids))
        query = query.where(status_filter)

    result = await session.execute(query)
    return [row[0] for row in result.all()]


@router.get("/{task_id}/shift-window", response_model=ShiftWindowResponse)
async def get_shift_window(
    task_id: str,
    session: DBDep,
    current_user: CurrentUser,
    start_date: dt.date = Query(...),
    days: int = Query(default=5, ge=1, le=31),
) -> ShiftWindowResponse:
    """Get shifts for a single task within a date window (for next/prev navigation)."""
    db_task = await crud_task.get(session, task_id, raise_404_error=True)
    role = await get_event_role(current_user, session, db_task.event_id)
    if role is None:
        raise_problem(404, code="task.not_found", detail="Task not found")
    if db_task.status != "published" and role not in ("owner", "admin"):
        raise_problem(403, code="task.not_published", detail="Task is not published")

    end_date = start_date + dt.timedelta(days=days - 1)
    pairs = await _query_shifts_with_bookings(
        session,
        task_ids=[db_task.id],
        user_id=current_user.id,
        date_from=start_date,
        date_to=end_date,
    )

    return ShiftWindowResponse(
        shifts=[entry for _, entry in pairs],
        start_date=start_date,
        days=days,
    )
