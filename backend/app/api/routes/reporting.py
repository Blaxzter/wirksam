# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false
# SQLAlchemy column-level selects produce types that basedpyright cannot resolve.
import csv
import datetime as dt
import io

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlmodel import col

from app.api.deps import CurrentSuperuser, DBDep
from app.models.booking import Booking
from app.models.duty_slot import DutySlot
from app.models.event import Event
from app.models.user import User
from app.schemas.reporting import (
    BookingsByHour,
    BookingsTrendPoint,
    CategoryBreakdown,
    EventFillRate,
    ReportingOverviewStats,
    ReportingResponse,
    TopVolunteer,
)

router = APIRouter(prefix="/reporting", tags=["reporting"])


@router.get("/overview", response_model=ReportingResponse)
async def reporting_overview(
    session: DBDep,
    _current_user: CurrentSuperuser,
    date_from: dt.date | None = Query(None, description="Start date filter"),
    date_to: dt.date | None = Query(None, description="End date filter"),
) -> ReportingResponse:
    """Admin-only reporting dashboard data."""
    overview = await _overview_stats(session, date_from, date_to)
    bookings_trend = await _bookings_trend(session, date_from, date_to)
    top_volunteers = await _top_volunteers(session, date_from, date_to)
    category_breakdown = await _category_breakdown(session, date_from, date_to)
    bookings_by_hour = await _bookings_by_hour(session, date_from, date_to)
    event_fill_rates = await _event_fill_rates(session, date_from, date_to)

    return ReportingResponse(
        overview=overview,
        bookings_trend=bookings_trend,
        top_volunteers=top_volunteers,
        category_breakdown=category_breakdown,
        bookings_by_hour=bookings_by_hour,
        event_fill_rates=event_fill_rates,
    )


@router.get("/export")
async def reporting_export(
    session: DBDep,
    _current_user: CurrentSuperuser,
    date_from: dt.date | None = Query(None),
    date_to: dt.date | None = Query(None),
) -> StreamingResponse:
    """Export booking data as CSV."""
    query = (
        select(
            col(Booking.id).label("booking_id"),
            col(Booking.status),
            col(Booking.created_at),
            col(Booking.cancellation_reason),
            col(User.name).label("volunteer_name"),
            col(User.email).label("volunteer_email"),
            col(DutySlot.title).label("slot_title"),
            col(DutySlot.date).label("slot_date"),
            col(DutySlot.start_time).label("slot_start_time"),
            col(DutySlot.end_time).label("slot_end_time"),
            col(DutySlot.location).label("slot_location"),
            col(DutySlot.category).label("slot_category"),
            col(Event.name).label("event_name"),
        )
        .join(User, col(Booking.user_id) == col(User.id))
        .outerjoin(DutySlot, col(Booking.duty_slot_id) == col(DutySlot.id))
        .outerjoin(Event, col(DutySlot.event_id) == col(Event.id))
        .order_by(col(Booking.created_at).desc())
    )
    query = _apply_slot_date_filters(query, date_from, date_to)

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
            "Slot Title",
            "Slot Date",
            "Start Time",
            "End Time",
            "Location",
            "Category",
            "Event Name",
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
                row.slot_location or "",
                row.slot_category or "",
                row.event_name or "",
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


def _apply_slot_date_filters(query, date_from, date_to):  # noqa: ANN001, ANN202
    """Apply optional date range filters on DutySlot.date."""
    if date_from:
        query = query.where(col(DutySlot.date) >= date_from)
    if date_to:
        query = query.where(col(DutySlot.date) <= date_to)
    return query


async def _overview_stats(  # noqa: ANN001
    session, date_from: dt.date | None, date_to: dt.date | None
) -> ReportingOverviewStats:
    # Booking counts
    booking_query = (
        select(
            func.count().label("total"),
            func.count().filter(col(Booking.status) == "confirmed").label("confirmed"),
            func.count().filter(col(Booking.status) == "cancelled").label("cancelled"),
        )
        .select_from(Booking)
        .outerjoin(DutySlot, col(Booking.duty_slot_id) == col(DutySlot.id))
    )
    booking_query = _apply_slot_date_filters(booking_query, date_from, date_to)
    result = await session.execute(booking_query)
    row = result.one()
    total_bookings = row.total
    confirmed_bookings = row.confirmed
    cancelled_bookings = row.cancelled
    cancellation_rate = (
        cancelled_bookings / total_bookings * 100 if total_bookings > 0 else 0.0
    )

    # Event count
    event_query = select(func.count()).select_from(Event)
    if date_from:
        event_query = event_query.where(col(Event.end_date) >= date_from)
    if date_to:
        event_query = event_query.where(col(Event.start_date) <= date_to)
    event_result = await session.execute(event_query)
    total_events = event_result.scalar_one()

    # Slot stats
    slot_query = select(
        func.count().label("total_slots"),
        func.coalesce(func.sum(col(DutySlot.max_bookings)), 0).label("total_capacity"),
    ).select_from(DutySlot)
    if date_from:
        slot_query = slot_query.where(col(DutySlot.date) >= date_from)
    if date_to:
        slot_query = slot_query.where(col(DutySlot.date) <= date_to)
    slot_result = await session.execute(slot_query)
    slot_row = slot_result.one()
    total_slots = slot_row.total_slots
    total_capacity = slot_row.total_capacity

    # Filled slots (slots with at least one confirmed booking)
    confirmed_count_sq = (
        select(func.count())
        .select_from(Booking)
        .where(
            col(Booking.duty_slot_id) == col(DutySlot.id),
            col(Booking.status) == "confirmed",
        )
        .correlate(DutySlot)
        .scalar_subquery()
    )
    filled_query = (
        select(func.count()).select_from(DutySlot).where(confirmed_count_sq > 0)
    )
    if date_from:
        filled_query = filled_query.where(col(DutySlot.date) >= date_from)
    if date_to:
        filled_query = filled_query.where(col(DutySlot.date) <= date_to)
    filled_result = await session.execute(filled_query)
    filled_slots = filled_result.scalar_one()

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
        total_events=total_events,
        total_slots=total_slots,
        total_slot_capacity=total_capacity,
        filled_slots=filled_slots,
        fill_rate=round(fill_rate, 1),
        active_volunteers=vol_row.active,
        total_volunteers=vol_row.total,
    )


async def _bookings_trend(  # noqa: ANN001
    session, date_from: dt.date | None, date_to: dt.date | None
) -> list[BookingsTrendPoint]:
    query = (
        select(
            col(DutySlot.date).label("date"),
            func.count().filter(col(Booking.status) == "confirmed").label("confirmed"),
            func.count().filter(col(Booking.status) == "cancelled").label("cancelled"),
        )
        .select_from(Booking)
        .join(DutySlot, col(Booking.duty_slot_id) == col(DutySlot.id))
        .group_by(col(DutySlot.date))
        .order_by(col(DutySlot.date))
    )
    query = _apply_slot_date_filters(query, date_from, date_to)

    result = await session.execute(query)
    return [
        BookingsTrendPoint(date=r.date, confirmed=r.confirmed, cancelled=r.cancelled)
        for r in result.all()
    ]


async def _top_volunteers(  # noqa: ANN001
    session, date_from: dt.date | None, date_to: dt.date | None
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
        .outerjoin(DutySlot, col(Booking.duty_slot_id) == col(DutySlot.id))
        .where(col(Booking.status) == "confirmed")
        .group_by(col(User.id), col(User.name), col(User.email))
        .order_by(func.count().desc())
        .limit(10)
    )
    query = _apply_slot_date_filters(query, date_from, date_to)

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
    session, date_from: dt.date | None, date_to: dt.date | None
) -> list[CategoryBreakdown]:
    confirmed_count_sq = (
        select(func.count())
        .select_from(Booking)
        .where(
            col(Booking.duty_slot_id) == col(DutySlot.id),
            col(Booking.status) == "confirmed",
        )
        .correlate(DutySlot)
        .scalar_subquery()
    )
    query = (
        select(
            col(DutySlot.category),
            func.count().label("slot_count"),
            func.coalesce(func.sum(col(DutySlot.max_bookings)), 0).label(
                "total_capacity"
            ),
            func.coalesce(func.sum(confirmed_count_sq), 0).label("confirmed_bookings"),
        )
        .select_from(DutySlot)
        .group_by(col(DutySlot.category))
        .order_by(func.count().desc())
    )
    if date_from:
        query = query.where(col(DutySlot.date) >= date_from)
    if date_to:
        query = query.where(col(DutySlot.date) <= date_to)

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
    session, date_from: dt.date | None, date_to: dt.date | None
) -> list[BookingsByHour]:
    hour_expr = func.extract("hour", col(DutySlot.start_time))
    query = (
        select(
            hour_expr.label("hour"),
            func.count().label("booking_count"),
        )
        .select_from(Booking)
        .join(DutySlot, col(Booking.duty_slot_id) == col(DutySlot.id))
        .where(
            col(Booking.status) == "confirmed",
            col(DutySlot.start_time).is_not(None),
        )
        .group_by(hour_expr)
        .order_by(hour_expr)
    )
    query = _apply_slot_date_filters(query, date_from, date_to)

    result = await session.execute(query)
    return [
        BookingsByHour(hour=int(r.hour), booking_count=r.booking_count)
        for r in result.all()
    ]


async def _event_fill_rates(  # noqa: ANN001
    session, date_from: dt.date | None, date_to: dt.date | None
) -> list[EventFillRate]:
    confirmed_count_sq = (
        select(func.count())
        .select_from(Booking)
        .where(
            col(Booking.duty_slot_id) == col(DutySlot.id),
            col(Booking.status) == "confirmed",
        )
        .correlate(DutySlot)
        .scalar_subquery()
    )
    query = (
        select(
            col(Event.id).label("event_id"),
            col(Event.name).label("event_name"),
            func.coalesce(func.sum(col(DutySlot.max_bookings)), 0).label(
                "total_capacity"
            ),
            func.coalesce(func.sum(confirmed_count_sq), 0).label("confirmed_bookings"),
        )
        .select_from(Event)
        .join(DutySlot, col(DutySlot.event_id) == col(Event.id))
        .group_by(col(Event.id), col(Event.name))
        .order_by(col(Event.name))
    )
    if date_from:
        query = query.where(col(DutySlot.date) >= date_from)
    if date_to:
        query = query.where(col(DutySlot.date) <= date_to)

    result = await session.execute(query)
    return [
        EventFillRate(
            event_id=r.event_id,
            event_name=r.event_name,
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
