# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false
# SQLAlchemy column-level selects produce types that basedpyright cannot resolve.
import csv
import datetime as dt
import io
import uuid
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.logic.event_scope import get_manageable_event_ids
from app.logic.work_hours import shift_minutes
from app.models.booking import Booking
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.reporting import (
    BookingsByHour,
    BookingsTrendPoint,
    CategoryBreakdown,
    ReportingOverviewStats,
    ReportingResponse,
    TaskFillRate,
    TopVolunteer,
)

router = APIRouter(prefix="/reporting", tags=["reporting"])


@router.get("/overview", response_model=ReportingResponse)
async def reporting_overview(
    session: DBDep,
    current_user: CurrentUser,
    date_from: dt.date | None = Query(None, description="Start date filter"),
    date_to: dt.date | None = Query(None, description="End date filter"),
) -> ReportingResponse:
    """Reporting for the events you run.

    The platform superadmin sees everything; everyone else sees the tasks in
    events where they hold owner or admin, plus tasks they created.
    """
    task_ids_filter = await _get_managed_task_ids(current_user, session)
    overview = await _overview_stats(session, date_from, date_to, task_ids_filter)
    bookings_trend = await _bookings_trend(session, date_from, date_to, task_ids_filter)
    top_volunteers = await _top_volunteers(session, date_from, date_to, task_ids_filter)
    category_breakdown = await _category_breakdown(
        session, date_from, date_to, task_ids_filter
    )
    bookings_by_hour = await _bookings_by_hour(
        session, date_from, date_to, task_ids_filter
    )
    task_fill_rates = await _task_fill_rates(
        session, date_from, date_to, task_ids_filter
    )

    return ReportingResponse(
        overview=overview,
        bookings_trend=bookings_trend,
        top_volunteers=top_volunteers,
        category_breakdown=category_breakdown,
        bookings_by_hour=bookings_by_hour,
        task_fill_rates=task_fill_rates,
    )


@router.get("/export")
async def reporting_export(
    session: DBDep,
    current_user: CurrentUser,
    date_from: dt.date | None = Query(None),
    date_to: dt.date | None = Query(None),
) -> StreamingResponse:
    """Export booking data as CSV, scoped the same way as the overview."""
    task_ids_filter = await _get_managed_task_ids(current_user, session)
    query = (
        select(
            col(Booking.id).label("booking_id"),
            col(Booking.status),
            col(Booking.created_at),
            col(Booking.cancellation_reason),
            col(User.name).label("volunteer_name"),
            col(User.email).label("volunteer_email"),
            col(Shift.title).label("slot_title"),
            col(Shift.date).label("slot_date"),
            col(Shift.start_time).label("slot_start_time"),
            col(Shift.end_time).label("slot_end_time"),
            col(Shift.location).label("slot_location"),
            col(Shift.category).label("slot_category"),
            col(Task.name).label("task_name"),
        )
        .join(User, col(Booking.user_id) == col(User.id))
        .outerjoin(Shift, col(Booking.shift_id) == col(Shift.id))
        .outerjoin(Task, col(Shift.task_id) == col(Task.id))
        .order_by(col(Booking.created_at).desc())
    )
    if task_ids_filter is not None:
        query = query.where(col(Task.id).in_(task_ids_filter))
    else:
        query = query.where(col(Task.id).notin_(_non_sandbox_tasks()))
    query = _apply_shift_date_filters(query, date_from, date_to)

    result = await session.execute(query)
    rows = result.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Booking ID",
            "Status",
            "Booked At",
            "Cancellation Reason",
            "Volunteer Name",
            "Volunteer Email",
            "Shift Title",
            "Shift Date",
            "Start Time",
            "End Time",
            "Hours",
            "Location",
            "Category",
            "Task Name",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                str(row.booking_id),
                row.status,
                str(row.created_at) if row.created_at else "",
                row.cancellation_reason or "",
                row.volunteer_name or "",
                row.volunteer_email or "",
                row.slot_title or "",
                str(row.slot_date) if row.slot_date else "",
                str(row.slot_start_time) if row.slot_start_time else "",
                str(row.slot_end_time) if row.slot_end_time else "",
                _csv_hours(row.slot_start_time, row.slot_end_time),
                row.slot_location or "",
                row.slot_category or "",
                row.task_name or "",
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bookings-report.csv"},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _csv_hours(start: dt.time | None, end: dt.time | None) -> str:
    """Shift length as decimal hours; blank when the shift has no times."""
    if start is None or end is None:
        return ""
    return f"{shift_minutes(start, end) / 60:.2f}"


def _apply_shift_date_filters(query, date_from, date_to):  # noqa: ANN001, ANN202
    """Apply optional date range filters on Shift.date."""
    if date_from:
        query = query.where(col(Shift.date) >= date_from)
    if date_to:
        query = query.where(col(Shift.date) <= date_to)
    return query


async def _get_managed_task_ids(
    user: User, session: AsyncSession
) -> list[uuid.UUID] | None:
    """Return list of task IDs the user may see in reporting.

    The platform superadmin gets None (= no filter, see everything). Everyone
    else sees every task in an event where they hold owner or admin.

    Raises 403 when the caller runs no event at all: reporting is a tool for
    the people organising something, and there is nothing coherent to show
    someone who only participates.
    """
    managed_group_ids = await get_manageable_event_ids(session, user)
    if managed_group_ids is None:
        return None
    if not managed_group_ids:
        raise_problem(
            403,
            code="reporting.no_managed_events",
            detail="Reporting is available to owners and admins of an event",
        )

    group_tasks_result = await session.execute(
        select(col(Task.id)).where(col(Task.event_id).in_(managed_group_ids))
    )
    return list(group_tasks_result.scalars().all())


def _non_sandbox_tasks() -> Any:
    """Subquery of every task that belongs to a demo.

    Reporting is the one place where a caller may legitimately have no event
    filter at all - the platform superadmin sees the whole installation - so
    the sandbox exclusion cannot ride along on an event scope the way it does
    everywhere else. It has to be its own clause, applied exactly where the
    scope filter would otherwise have gone.
    """
    return select(col(Task.id)).where(col(Task.is_sandbox).is_(True))


async def _overview_stats(  # noqa: ANN001
    session,
    date_from: dt.date | None,
    date_to: dt.date | None,
    task_ids_filter: list[uuid.UUID] | None = None,
) -> ReportingOverviewStats:
    # Booking counts
    booking_query = (
        select(
            func.count().label("total"),
            func.count().filter(col(Booking.status) == "confirmed").label("confirmed"),
            func.count().filter(col(Booking.status) == "cancelled").label("cancelled"),
        )
        .select_from(Booking)
        .outerjoin(Shift, col(Booking.shift_id) == col(Shift.id))
    )
    if task_ids_filter is not None:
        booking_query = booking_query.where(col(Shift.task_id).in_(task_ids_filter))
    else:
        booking_query = booking_query.where(
            col(Shift.task_id).notin_(_non_sandbox_tasks())
        )
    booking_query = _apply_shift_date_filters(booking_query, date_from, date_to)
    result = await session.execute(booking_query)
    row = result.one()
    total_bookings = row.total
    confirmed_bookings = row.confirmed
    cancelled_bookings = row.cancelled
    cancellation_rate = (
        cancelled_bookings / total_bookings * 100 if total_bookings > 0 else 0.0
    )

    # Task count
    task_query = select(func.count()).select_from(Task)
    if task_ids_filter is not None:
        task_query = task_query.where(col(Task.id).in_(task_ids_filter))
    else:
        task_query = task_query.where(col(Task.id).notin_(_non_sandbox_tasks()))
    if date_from:
        task_query = task_query.where(col(Task.end_date) >= date_from)
    if date_to:
        task_query = task_query.where(col(Task.start_date) <= date_to)
    task_result = await session.execute(task_query)
    total_tasks = task_result.scalar_one()

    # Shift stats
    slot_query = select(
        func.count().label("total_shifts"),
        func.coalesce(func.sum(col(Shift.max_bookings)), 0).label("total_capacity"),
    ).select_from(Shift)
    if task_ids_filter is not None:
        slot_query = slot_query.where(col(Shift.task_id).in_(task_ids_filter))
    else:
        slot_query = slot_query.where(col(Shift.task_id).notin_(_non_sandbox_tasks()))
    if date_from:
        slot_query = slot_query.where(col(Shift.date) >= date_from)
    if date_to:
        slot_query = slot_query.where(col(Shift.date) <= date_to)
    slot_result = await session.execute(slot_query)
    slot_row = slot_result.one()
    total_shifts = slot_row.total_shifts
    total_capacity = slot_row.total_capacity

    # Filled shifts (shifts with at least one confirmed booking)
    confirmed_count_sq = (
        select(func.count())
        .select_from(Booking)
        .where(
            col(Booking.shift_id) == col(Shift.id),
            col(Booking.status) == "confirmed",
        )
        .correlate(Shift)
        .scalar_subquery()
    )
    filled_query = select(func.count()).select_from(Shift).where(confirmed_count_sq > 0)
    if task_ids_filter is not None:
        filled_query = filled_query.where(col(Shift.task_id).in_(task_ids_filter))
    else:
        filled_query = filled_query.where(
            col(Shift.task_id).notin_(_non_sandbox_tasks())
        )
    if date_from:
        filled_query = filled_query.where(col(Shift.date) >= date_from)
    if date_to:
        filled_query = filled_query.where(col(Shift.date) <= date_to)
    filled_result = await session.execute(filled_query)
    filled_shifts = filled_result.scalar_one()

    # Confirmed bookings as % of total capacity
    fill_rate = confirmed_bookings / total_capacity * 100 if total_capacity > 0 else 0.0

    # Volunteer counts
    volunteer_query = select(
        func.count().label("total"),
        func.count().filter(col(User.is_active) == True).label("active"),  # noqa: E712
    ).select_from(User)
    vol_result = await session.execute(volunteer_query)
    vol_row = vol_result.one()

    return ReportingOverviewStats(
        total_bookings=total_bookings,
        confirmed_bookings=confirmed_bookings,
        cancelled_bookings=cancelled_bookings,
        cancellation_rate=round(cancellation_rate, 1),
        total_tasks=total_tasks,
        total_shifts=total_shifts,
        total_shift_capacity=total_capacity,
        filled_shifts=filled_shifts,
        fill_rate=round(fill_rate, 1),
        active_volunteers=vol_row.active,
        total_volunteers=vol_row.total,
    )


async def _bookings_trend(  # noqa: ANN001
    session,
    date_from: dt.date | None,
    date_to: dt.date | None,
    task_ids_filter: list[uuid.UUID] | None = None,
) -> list[BookingsTrendPoint]:
    query = (
        select(
            col(Shift.date).label("date"),
            func.count().filter(col(Booking.status) == "confirmed").label("confirmed"),
            func.count().filter(col(Booking.status) == "cancelled").label("cancelled"),
        )
        .select_from(Booking)
        .join(Shift, col(Booking.shift_id) == col(Shift.id))
        .group_by(col(Shift.date))
        .order_by(col(Shift.date))
    )
    if task_ids_filter is not None:
        query = query.where(col(Shift.task_id).in_(task_ids_filter))
    else:
        query = query.where(col(Shift.task_id).notin_(_non_sandbox_tasks()))
    query = _apply_shift_date_filters(query, date_from, date_to)

    result = await session.execute(query)
    return [
        BookingsTrendPoint(date=r.date, confirmed=r.confirmed, cancelled=r.cancelled)
        for r in result.all()
    ]


async def _top_volunteers(  # noqa: ANN001
    session,
    date_from: dt.date | None,
    date_to: dt.date | None,
    task_ids_filter: list[uuid.UUID] | None = None,
) -> list[TopVolunteer]:
    query = (
        select(
            col(User.id).label("user_id"),
            col(User.name),
            col(User.email),
            func.count().label("booking_count"),
        )
        .select_from(Booking)
        .join(User, col(Booking.user_id) == col(User.id))
        .outerjoin(Shift, col(Booking.shift_id) == col(Shift.id))
        .where(col(Booking.status) == "confirmed")
        .group_by(col(User.id), col(User.name), col(User.email))
        .order_by(func.count().desc())
        .limit(10)
    )
    if task_ids_filter is not None:
        query = query.where(col(Shift.task_id).in_(task_ids_filter))
    else:
        query = query.where(col(Shift.task_id).notin_(_non_sandbox_tasks()))
    query = _apply_shift_date_filters(query, date_from, date_to)

    result = await session.execute(query)
    return [
        TopVolunteer(
            user_id=r.user_id,
            name=r.name,
            email=r.email,
            booking_count=r.booking_count,
        )
        for r in result.all()
    ]


async def _category_breakdown(  # noqa: ANN001
    session,
    date_from: dt.date | None,
    date_to: dt.date | None,
    task_ids_filter: list[uuid.UUID] | None = None,
) -> list[CategoryBreakdown]:
    confirmed_count_sq = (
        select(func.count())
        .select_from(Booking)
        .where(
            col(Booking.shift_id) == col(Shift.id),
            col(Booking.status) == "confirmed",
        )
        .correlate(Shift)
        .scalar_subquery()
    )
    query = (
        select(
            col(Shift.category),
            func.count().label("slot_count"),
            func.coalesce(func.sum(col(Shift.max_bookings)), 0).label("total_capacity"),
            func.coalesce(func.sum(confirmed_count_sq), 0).label("confirmed_bookings"),
        )
        .select_from(Shift)
        .group_by(col(Shift.category))
        .order_by(func.count().desc())
    )
    if task_ids_filter is not None:
        query = query.where(col(Shift.task_id).in_(task_ids_filter))
    else:
        query = query.where(col(Shift.task_id).notin_(_non_sandbox_tasks()))
    if date_from:
        query = query.where(col(Shift.date) >= date_from)
    if date_to:
        query = query.where(col(Shift.date) <= date_to)

    result = await session.execute(query)
    return [
        CategoryBreakdown(
            category=r.category,
            slot_count=r.slot_count,
            total_capacity=r.total_capacity,
            confirmed_bookings=r.confirmed_bookings,
            fill_rate=round(
                r.confirmed_bookings / r.total_capacity * 100
                if r.total_capacity > 0
                else 0.0,
                1,
            ),
        )
        for r in result.all()
    ]


async def _bookings_by_hour(  # noqa: ANN001
    session,
    date_from: dt.date | None,
    date_to: dt.date | None,
    task_ids_filter: list[uuid.UUID] | None = None,
) -> list[BookingsByHour]:
    hour_expr = func.extract("hour", col(Shift.start_time))
    query = (
        select(
            hour_expr.label("hour"),
            func.count().label("booking_count"),
        )
        .select_from(Booking)
        .join(Shift, col(Booking.shift_id) == col(Shift.id))
        .where(
            col(Booking.status) == "confirmed",
            col(Shift.start_time).is_not(None),
        )
        .group_by(hour_expr)
        .order_by(hour_expr)
    )
    if task_ids_filter is not None:
        query = query.where(col(Shift.task_id).in_(task_ids_filter))
    else:
        query = query.where(col(Shift.task_id).notin_(_non_sandbox_tasks()))
    query = _apply_shift_date_filters(query, date_from, date_to)

    result = await session.execute(query)
    return [
        BookingsByHour(hour=int(r.hour), booking_count=r.booking_count)
        for r in result.all()
    ]


async def _task_fill_rates(  # noqa: ANN001
    session,
    date_from: dt.date | None,
    date_to: dt.date | None,
    task_ids_filter: list[uuid.UUID] | None = None,
) -> list[TaskFillRate]:
    confirmed_count_sq = (
        select(func.count())
        .select_from(Booking)
        .where(
            col(Booking.shift_id) == col(Shift.id),
            col(Booking.status) == "confirmed",
        )
        .correlate(Shift)
        .scalar_subquery()
    )
    query = (
        select(
            col(Task.id).label("task_id"),
            col(Task.name).label("task_name"),
            func.coalesce(func.sum(col(Shift.max_bookings)), 0).label("total_capacity"),
            func.coalesce(func.sum(confirmed_count_sq), 0).label("confirmed_bookings"),
        )
        .select_from(Task)
        .join(Shift, col(Shift.task_id) == col(Task.id))
        .group_by(col(Task.id), col(Task.name))
        .order_by(col(Task.name))
    )
    if task_ids_filter is not None:
        query = query.where(col(Task.id).in_(task_ids_filter))
    else:
        query = query.where(col(Task.id).notin_(_non_sandbox_tasks()))
    if date_from:
        query = query.where(col(Shift.date) >= date_from)
    if date_to:
        query = query.where(col(Shift.date) <= date_to)

    result = await session.execute(query)
    return [
        TaskFillRate(
            task_id=r.task_id,
            task_name=r.task_name,
            total_capacity=r.total_capacity,
            confirmed_bookings=r.confirmed_bookings,
            fill_rate=round(
                r.confirmed_bookings / r.total_capacity * 100
                if r.total_capacity > 0
                else 0.0,
                1,
            ),
        )
        for r in result.all()
    ]
