"""Per-event locations (#182).

A location is a named place inside one event. Tasks, shift batches and shifts
point at it through ``location_id`` and keep its name in their ``location``
text, so renaming rewrites that copy (:func:`propagate_rename`) and deleting
leaves it behind as free text.

Gates, per the design: reads go through :func:`require_event_visible` (a
stranger gets 404 for a private event), mutations additionally through
:func:`require_event_role` with ``minimum="admin"``. The two member-only reads
(pins and the per-day shift list) turn a visible-but-not-member caller into a
404 as well, so the venue map never leaks to someone outside the event.
"""

import datetime as dt
import uuid
from typing import NoReturn, cast

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.event import event as crud_event
from app.crud.location import location as crud_location
from app.logic.locations import propagate_rename
from app.logic.permissions import (
    require_event_role,
    require_event_visible,
    role_at_least,
)
from app.models.booking import Booking
from app.models.event import Event
from app.models.location import Location
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.event_membership import EventRole
from app.schemas.location import (
    LocationCreate,
    LocationDetailRead,
    LocationRead,
    LocationShiftRead,
    LocationUpdate,
)

router = APIRouter(tags=["locations"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _visible_event(
    user: User, session: AsyncSession, event_id: uuid.UUID
) -> tuple[Event, EventRole | None]:
    """The event, if the caller may see it at all (404 otherwise)."""
    event = await crud_event.get(session, event_id, raise_404_error=True)
    role = await require_event_visible(user, session, event)
    return event, role


async def _member_event(
    user: User, session: AsyncSession, event_id: uuid.UUID
) -> tuple[Event, EventRole]:
    """The event, if the caller is a member of it.

    A visitor on a public event passes :func:`require_event_visible` with no
    role; for member-only data that is the same 404 a stranger gets.
    """
    event, role = await _visible_event(user, session, event_id)
    if role is None:
        raise_problem(404, code="event.not_found", detail="Event not found")
    return event, role


async def _load_location(session: AsyncSession, location_id: uuid.UUID) -> Location:
    loc = await crud_location.get(session, location_id=location_id)
    if loc is None:
        raise_problem(404, code="location.not_found", detail="Location not found")
    return loc


async def _admin_location(
    user: User, session: AsyncSession, location_id: uuid.UUID
) -> Location:
    """Load a location for a mutation: 404 if unseen, 403 below event admin."""
    loc = await _load_location(session, location_id)
    await _visible_event(user, session, loc.event_id)
    await require_event_role(user, session, loc.event_id, minimum="admin")
    return loc


async def _ensure_name_free(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> None:
    clash = await crud_location.get_by_name_ci(
        session, event_id=event_id, name=name, exclude_id=exclude_id
    )
    if clash is not None:
        _raise_name_taken()


def _raise_name_taken() -> NoReturn:
    raise_problem(
        409,
        code="location.name_taken",
        detail="This event already has a location with that name",
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/events/{event_id}/locations", response_model=list[LocationRead])
async def list_event_locations(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> list[LocationRead]:
    """All locations of an event, alphabetically."""
    await _visible_event(current_user, session, event_id)
    locations = await crud_location.list_for_event(session, event_id=event_id)
    return [LocationRead.model_validate(loc) for loc in locations]


@router.post(
    "/events/{event_id}/locations", response_model=LocationRead, status_code=201
)
async def create_event_location(
    event_id: uuid.UUID,
    payload: LocationCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> LocationRead:
    """Add a location. Names are unique per event, ignoring case."""
    await _visible_event(current_user, session, event_id)
    await require_event_role(current_user, session, event_id, minimum="admin")
    await _ensure_name_free(session, event_id=event_id, name=payload.name)
    try:
        # A savepoint, so losing a race on the unique constraint (after the
        # pre-check above passed) leaves the transaction usable for the 409.
        async with session.begin_nested():
            loc = await crud_location.create(session, event_id=event_id, data=payload)
    except IntegrityError:
        _raise_name_taken()
    return LocationRead.model_validate(loc)


@router.get("/locations/{location_id}", response_model=LocationDetailRead)
async def get_location(
    location_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> LocationDetailRead:
    """One location, with its venue-plan pins for members of the event."""
    loc = await _load_location(session, location_id)
    _, role = await _visible_event(current_user, session, loc.event_id)
    read = LocationDetailRead.model_validate(loc)
    if role is not None:
        read.pins = await crud_location.pins_for_location(session, location_id=loc.id)
    return read


@router.patch("/locations/{location_id}", response_model=LocationRead)
async def update_location(
    location_id: uuid.UUID,
    payload: LocationUpdate,
    session: DBDep,
    current_user: CurrentUser,
) -> LocationRead:
    """Edit a location. A rename rewrites the text on every row pointing at it."""
    loc = await _admin_location(current_user, session, location_id)
    old_name = loc.name
    if payload.name is not None and payload.name != old_name:
        await _ensure_name_free(
            session, event_id=loc.event_id, name=payload.name, exclude_id=loc.id
        )
    try:
        async with session.begin_nested():
            loc = await crud_location.update(session, location=loc, data=payload)
    except IntegrityError:
        _raise_name_taken()
    if loc.name != old_name:
        await propagate_rename(session, loc.id, loc.name)
    return LocationRead.model_validate(loc)


@router.delete("/locations/{location_id}", status_code=204)
async def delete_location(
    location_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Delete a location. Tasks and shifts keep its name as free text."""
    loc = await _admin_location(current_user, session, location_id)
    await crud_location.delete(session, location=loc)


@router.get("/locations/{location_id}/shifts", response_model=list[LocationShiftRead])
async def list_location_shifts(
    location_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    on: dt.date | None = Query(
        default=None, description="Day to list; defaults to today"
    ),
) -> list[LocationShiftRead]:
    """The shifts at a location on one day, for the map's location sheet.

    Members only. Shifts of unpublished tasks are listed for event admins
    alone, matching the task feed.
    """
    loc = await _load_location(session, location_id)
    _, role = await _member_event(current_user, session, loc.event_id)
    day = on or dt.date.today()

    count_sq = (
        select(func.count())
        .select_from(Booking)
        .where(
            col(Booking.shift_id) == col(Shift.id),
            col(Booking.status) == "confirmed",
        )
        .correlate(Shift)
        .scalar_subquery()
    )
    my_booking_sq = (
        select(col(Booking.id))
        .where(
            col(Booking.shift_id) == col(Shift.id),
            col(Booking.user_id) == current_user.id,
            col(Booking.status) == "confirmed",
        )
        .correlate(Shift)
        .limit(1)
        .scalar_subquery()
    )
    query = (
        select(
            Shift,
            col(Task.name),
            count_sq.label("current_bookings"),
            my_booking_sq.label("my_booking_id"),
        )
        .join(Task, col(Task.id) == col(Shift.task_id))
        .where(
            col(Shift.location_id) == loc.id,
            col(Shift.date) == day,
            col(Task.event_id) == loc.event_id,
        )
        .order_by(
            col(Shift.start_time).asc().nulls_first(),
            col(Shift.title),
            col(Shift.id),
        )
    )
    if not role_at_least(role, "admin"):
        query = query.where(col(Task.status) == "published")

    result = await session.execute(query)
    shifts: list[LocationShiftRead] = []
    for shift, task_name, current, booking_id in result.all():
        # A scalar subquery is NULL when nothing matched, whatever its type says.
        my_booking_id = cast(uuid.UUID | None, booking_id)
        shifts.append(
            LocationShiftRead(
                id=shift.id,
                task_id=shift.task_id,
                task_name=task_name,
                title=shift.title,
                date=shift.date,
                start_time=shift.start_time,
                end_time=shift.end_time,
                max_bookings=shift.max_bookings,
                current_bookings=current or 0,
                is_booked_by_me=my_booking_id is not None,
                my_booking_id=my_booking_id,
            )
        )
    return shifts
