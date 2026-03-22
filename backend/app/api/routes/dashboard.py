# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false
# SQLAlchemy column-level selects produce types that basedpyright cannot resolve.
import datetime as dt

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlmodel import col

from app.api.deps import CurrentUser, DBDep
from app.crud.event import event as crud_event
from app.crud.event_group import event_group as crud_event_group
from app.models.booking import Booking
from app.models.duty_slot import DutySlot
from app.models.event import Event
from app.models.event_group import EventGroup
from app.models.user import User
from app.schemas.dashboard import (
    DashboardBookingItem,
    DashboardEvent,
    DashboardEventGroup,
    DashboardFeedResponse,
)
from app.schemas.sidebar import (
    SidebarBooking,
    SidebarEvent,
    SidebarEventGroup,
    SidebarResponse,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/feed", response_model=DashboardFeedResponse)
async def dashboard_feed(
    session: DBDep,
    current_user: CurrentUser,
) -> DashboardFeedResponse:
    """Single endpoint powering the /app/home dashboard."""
    effective_status = None if current_user.is_admin else "published"

    # Events + count
    events_list, event_count, groups_list = await _load_events_and_groups(
        session, effective_status
    )

    # User's confirmed bookings with slot info (single query, no N+1)
    bookings, booking_count = await _load_bookings(session, current_user.id)

    # Pending user count (admin only)
    pending_user_count = None
    if current_user.is_admin:
        pending_user_count = await _count_pending_users(session)

    return DashboardFeedResponse(
        events=[DashboardEvent.model_validate(e) for e in events_list],
        event_count=event_count,
        event_groups=[DashboardEventGroup.model_validate(g) for g in groups_list],
        bookings=bookings,
        booking_count=booking_count,
        pending_user_count=pending_user_count,
    )


async def _load_events_and_groups(session, effective_status):  # noqa: ANN001, ANN202
    events_list = await crud_event.get_multi_filtered(
        session, limit=100, status=effective_status
    )
    event_count = await crud_event.get_count_filtered(
        session, status=effective_status
    )
    groups_list = await crud_event_group.get_multi_filtered(
        session, limit=100, status=effective_status
    )
    return events_list, event_count, groups_list


async def _load_bookings(
    session, user_id,  # noqa: ANN001
) -> tuple[list[DashboardBookingItem], int]:
    """Fetch confirmed bookings joined with slot data in a single query."""
    query = (
        select(
            col(Booking.id),
            col(DutySlot.id).label("slot_id"),
            col(DutySlot.date),
            col(DutySlot.title),
            col(DutySlot.start_time),
            col(DutySlot.end_time),
        )
        .join(DutySlot, col(Booking.duty_slot_id) == col(DutySlot.id))
        .where(
            col(Booking.user_id) == user_id,
            col(Booking.status) == "confirmed",
        )
        .order_by(col(DutySlot.date), col(DutySlot.start_time))
        .limit(200)
    )
    result = await session.execute(query)
    rows = result.all()
    items = [
        DashboardBookingItem(
            id=row.id,
            slot_id=row.slot_id,
            date=row.date,
            title=row.title,
            start_time=row.start_time,
            end_time=row.end_time,
        )
        for row in rows
    ]

    # Count
    count_query = (
        select(func.count())
        .select_from(Booking)
        .where(
            col(Booking.user_id) == user_id,
            col(Booking.status) == "confirmed",
        )
    )
    count_result = await session.execute(count_query)
    total = count_result.scalar_one()

    return items, total


async def _count_pending_users(session) -> int:  # noqa: ANN001
    query = (
        select(func.count())
        .select_from(User)
        .where(
            col(User.is_active) == False,  # noqa: E712
            col(User.rejection_reason).is_(None),
        )
    )
    result = await session.execute(query)
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


@router.get("/sidebar", response_model=SidebarResponse)
async def dashboard_sidebar(
    session: DBDep,
    current_user: CurrentUser,
) -> SidebarResponse:
    """Lightweight data for sidebar quick-links."""
    today = dt.date.today()
    effective_status = None if current_user.is_admin else "published"

    groups = await _sidebar_event_groups(session, today, effective_status)
    events = await _sidebar_events(session, today, effective_status)
    bookings = await _sidebar_bookings(session, current_user.id, today)

    return SidebarResponse(
        event_groups=groups,
        events=events,
        bookings=bookings,
    )


async def _sidebar_event_groups(  # noqa: ANN001
    session, today: dt.date, status: str | None
) -> list[SidebarEventGroup]:
    """Published groups whose end_date >= today, limit 5."""
    query = (
        select(col(EventGroup.id), col(EventGroup.name))
        .where(col(EventGroup.end_date) >= today)
        .order_by(col(EventGroup.start_date))
        .limit(5)
    )
    if status:
        query = query.where(col(EventGroup.status) == status)
    result = await session.execute(query)
    return [SidebarEventGroup(id=r.id, name=r.name) for r in result.all()]


async def _sidebar_events(  # noqa: ANN001
    session, today: dt.date, status: str | None
) -> list[SidebarEvent]:
    """Published events with open-slot count and next slot date, limit 10."""
    # Subquery: confirmed booking count per slot
    booking_count_sq = (
        select(func.count())
        .select_from(Booking)
        .where(
            col(Booking.duty_slot_id) == col(DutySlot.id),
            col(Booking.status) == "confirmed",
        )
        .correlate(DutySlot)
        .scalar_subquery()
    )

    # Subquery: count of open slots (date >= today AND has capacity)
    open_slots_sq = (
        select(func.count())
        .select_from(DutySlot)
        .where(
            col(DutySlot.event_id) == col(Event.id),
            col(DutySlot.date) >= today,
            col(DutySlot.max_bookings) > booking_count_sq,
        )
        .correlate(Event)
        .scalar_subquery()
    )

    # Subquery: next open slot date
    next_slot_date_sq = (
        select(func.min(col(DutySlot.date)))
        .where(
            col(DutySlot.event_id) == col(Event.id),
            col(DutySlot.date) >= today,
            col(DutySlot.max_bookings) > booking_count_sq,
        )
        .correlate(Event)
        .scalar_subquery()
    )

    # Subquery: start_time of next open slot (on that date)
    next_slot_time_sq = (
        select(func.min(col(DutySlot.start_time)))
        .where(
            col(DutySlot.event_id) == col(Event.id),
            col(DutySlot.date) == next_slot_date_sq,
            col(DutySlot.max_bookings) > booking_count_sq,
        )
        .correlate(Event)
        .scalar_subquery()
    )

    query = (
        select(
            col(Event.id),
            col(Event.name),
            open_slots_sq.label("open_slots"),
            next_slot_date_sq.label("next_slot_date"),
            next_slot_time_sq.label("next_slot_start_time"),
        )
        .where(col(Event.end_date) >= today)
        .order_by(col(Event.start_date))
        .limit(10)
    )
    if status:
        query = query.where(col(Event.status) == status)

    result = await session.execute(query)
    return [
        SidebarEvent(
            id=r.id,
            name=r.name,
            open_slots=r.open_slots or 0,
            next_slot_date=r.next_slot_date,
            next_slot_start_time=r.next_slot_start_time,
        )
        for r in result.all()
    ]


async def _sidebar_bookings(  # noqa: ANN001
    session, user_id, today: dt.date
) -> list[SidebarBooking]:
    """User's upcoming confirmed bookings, limit 5."""
    query = (
        select(
            col(Booking.id),
            col(DutySlot.id).label("slot_id"),
            col(DutySlot.event_id),
            col(DutySlot.title).label("slot_title"),
            col(DutySlot.date).label("slot_date"),
            col(DutySlot.start_time).label("slot_start_time"),
        )
        .join(DutySlot, col(Booking.duty_slot_id) == col(DutySlot.id))
        .where(
            col(Booking.user_id) == user_id,
            col(Booking.status) == "confirmed",
            col(DutySlot.date) >= today,
        )
        .order_by(col(DutySlot.date), col(DutySlot.start_time))
        .limit(5)
    )
    result = await session.execute(query)
    return [
        SidebarBooking(
            id=r.id,
            slot_id=r.slot_id,
            event_id=r.event_id,
            slot_title=r.slot_title,
            slot_date=r.slot_date,
            slot_start_time=r.slot_start_time,
        )
        for r in result.all()
    ]
