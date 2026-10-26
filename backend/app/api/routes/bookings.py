import datetime as dt
import uuid

from fastapi import APIRouter, BackgroundTasks, Query
from sqlalchemy import func, select
from sqlmodel import col

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.crud.shift import shift as crud_shift
from app.crud.task import task as crud_task
from app.logic.booking_conflicts import find_conflicting_booking
from app.logic.event_scope import get_user_event_scope
from app.logic.notifications.triggers import (
    dispatch_booking_cancelled_by_user,
    dispatch_booking_cobooked,
    dispatch_booking_confirmed,
)
from app.logic.permissions import require_team_for_booking
from app.models.booking import Booking
from app.models.shift import Shift
from app.schemas.booking import (
    BookingBase,
    BookingCreate,
    BookingRead,
    BookingReadWithShift,
    BookingUpdate,
    MyBookingsListResponse,
    ShiftConflict,
    ShiftSummary,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("/me", response_model=MyBookingsListResponse)
async def list_my_bookings(
    session: DBDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    status: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    event_id: uuid.UUID | None = Query(default=None),
    all_events: bool = Query(default=False),
) -> MyBookingsListResponse:
    """List the current user's bookings with joined shift + task data.

    Defaults to scoping by the user's selected event. Pass ``all_events=true``
    to opt out of scoping (e.g. archived-bookings view).
    """
    effective_event_id = event_id
    if effective_event_id is None and not all_events:
        effective_event_id = get_user_event_scope(current_user)

    items = await crud_booking.get_multi_by_user(
        session,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        status=status,
        with_shift=True,
        date_from=date_from,
        date_to=date_to,
        event_id=effective_event_id,
    )
    total = await crud_booking.count_by_user(
        session,
        user_id=current_user.id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        event_id=effective_event_id,
    )

    enriched: list[BookingReadWithShift] = []
    for b in items:
        bws = BookingReadWithShift.model_validate(b)
        if b.shift is not None:
            slot_summary = ShiftSummary.model_validate(b.shift)
            slot_summary.task_name = b.shift.task.name if b.shift.task else None
            bws.shift = slot_summary
        enriched.append(bws)

    return MyBookingsListResponse(
        items=enriched,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/me/active-dates", response_model=list[dt.date])
async def my_booking_active_dates(
    session: DBDep,
    current_user: CurrentUser,
    date_from: dt.date = Query(...),
    date_to: dt.date = Query(...),
) -> list[dt.date]:
    """Return distinct shift dates within a range where the user has confirmed bookings."""
    query = (
        select(func.distinct(col(Shift.date)))
        .join(Booking, col(Booking.shift_id) == col(Shift.id))
        .where(
            col(Booking.user_id) == current_user.id,
            col(Booking.status) == "confirmed",
            col(Shift.date) >= date_from,
            col(Shift.date) <= date_to,
        )
        .order_by(col(Shift.date))
    )
    result = await session.execute(query)
    return [row[0] for row in result.all()]


@router.post("/", response_model=BookingRead, status_code=201)
async def create_booking(
    booking_in: BookingCreate,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> Booking:
    """Book a duty shift for the current user."""
    shift = await crud_shift.get(
        session, str(booking_in.shift_id), raise_404_error=True
    )
    task = await crud_task.get(session, str(shift.task_id))
    if task is not None:
        await require_team_for_booking(current_user, session, task)

    existing = await crud_booking.get_by_shift_and_user(
        session, shift_id=shift.id, user_id=current_user.id
    )
    if existing and existing.status == "confirmed":
        raise_problem(
            409,
            code="booking.already_exists",
            detail="You already have a confirmed booking for this shift",
        )

    conflict = await find_conflicting_booking(
        session, user_id=current_user.id, shift=shift
    )
    if conflict is not None:
        conflict_task = await crud_task.get(session, str(conflict.shift.task_id))
        clash = ShiftConflict.model_validate(conflict.shift)
        clash.task_name = conflict_task.name if conflict_task else None
        raise_problem(
            409,
            code="booking.time_conflict",
            detail=f"This shift overlaps your booked shift '{clash.title}'",
            extensions={"conflicting_shift": clash.model_dump(mode="json")},
        )

    confirmed_count = await crud_booking.get_confirmed_count(session, shift_id=shift.id)
    if confirmed_count >= shift.max_bookings:
        raise_problem(
            409, code="booking.slot_full", detail="This duty shift is fully booked"
        )

    # Collect existing confirmed bookers for co-booking notification
    existing_bookings = await crud_booking.get_multi_by_shift(
        session, shift_id=shift.id, status="confirmed"
    )
    existing_user_ids = [
        b.user_id for b in existing_bookings if b.user_id != current_user.id
    ]

    # If previously cancelled, reactivate
    if existing and existing.status == "cancelled":
        result = await crud_booking.update(
            session,
            db_obj=existing,
            obj_in=BookingUpdate(status="confirmed", notes=booking_in.notes),
        )
    else:
        full_booking = BookingBase(
            shift_id=booking_in.shift_id,
            user_id=current_user.id,
            notes=booking_in.notes,
        )
        result = await crud_booking.create(session, obj_in=full_booking)  # type: ignore[arg-type]

    task_name = task.name if task else None

    # Dispatch notifications
    background_tasks.add_task(
        dispatch_booking_confirmed,
        booking_id=result.id,
        user_id=current_user.id,
        slot_title=shift.title,
        slot_date=shift.date,
        slot_start_time=shift.start_time,
        slot_end_time=shift.end_time,
        slot_location=shift.location,
        task_name=task_name,
        slot_id=shift.id,
        task_id=shift.task_id,
        event_id=task.event_id if task else None,
    )
    if existing_user_ids:
        background_tasks.add_task(
            dispatch_booking_cobooked,
            slot_id=shift.id,
            slot_title=shift.title,
            task_id=shift.task_id,
            new_user_name=current_user.name,
            existing_user_ids=existing_user_ids,
        )

    # Create default reminders for this booking
    if current_user.default_reminder_offsets:
        slot_start = _shift_start_datetime(shift.date, shift.start_time)
        await crud_reminder.create_from_defaults(
            session,
            booking_id=result.id,
            user_id=current_user.id,
            shift_id=shift.id,
            slot_start=slot_start,
            defaults=current_user.default_reminder_offsets,
        )

    return result


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> Booking:
    db_booking = await crud_booking.get(session, booking_id, raise_404_error=True)
    if not current_user.is_admin and db_booking.user_id != current_user.id:
        raise_problem(
            403, code="booking.forbidden", detail="You can only view your own bookings"
        )
    return db_booking


@router.patch("/{booking_id}", response_model=BookingRead)
async def update_booking(
    booking_id: str,
    booking_in: BookingUpdate,
    session: DBDep,
    current_user: CurrentUser,
) -> Booking:
    """Update a booking. Only the owner or admin can modify."""
    db_booking = await crud_booking.get(session, booking_id, raise_404_error=True)
    if not current_user.is_admin and db_booking.user_id != current_user.id:
        raise_problem(
            403,
            code="booking.forbidden",
            detail="You can only modify your own bookings",
        )
    if booking_in.status == "confirmed" and db_booking.status != "confirmed":
        # Re-confirming a cancelled booking here would skip every check
        # booking a shift runs: capacity, overlaps and the team gate.
        # POST /bookings/ reactivates a cancelled row with all of them.
        raise_problem(
            422,
            code="booking.rebook_required",
            detail="Book the shift again to reactivate a cancelled booking",
        )
    return await crud_booking.update(session, db_obj=db_booking, obj_in=booking_in)


@router.delete("/{booking_id}", response_model=BookingRead)
async def cancel_booking(
    booking_id: str,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> Booking:
    """Cancel a booking (soft-cancel by setting status to 'cancelled')."""
    db_booking = await crud_booking.get(session, booking_id, raise_404_error=True)
    if not current_user.is_admin and db_booking.user_id != current_user.id:
        raise_problem(
            403,
            code="booking.forbidden",
            detail="You can only cancel your own bookings",
        )
    result = await crud_booking.update(
        session, db_obj=db_booking, obj_in=BookingUpdate(status="cancelled")
    )

    # Cancel pending reminders
    await crud_reminder.cancel_by_booking(session, booking_id=db_booking.id)

    # Dispatch cancellation notification
    if db_booking.shift_id:
        shift = await crud_shift.get(session, str(db_booking.shift_id))
        if shift:
            background_tasks.add_task(
                dispatch_booking_cancelled_by_user,
                booking_id=result.id,
                user_id=db_booking.user_id,
                slot_title=shift.title,
                slot_id=shift.id,
                task_id=shift.task_id,
            )

    return result


@router.delete("/{booking_id}/dismiss", status_code=204)
async def dismiss_booking(
    booking_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Permanently delete a cancelled booking from the user's list."""
    db_booking = await crud_booking.get(session, booking_id, raise_404_error=True)
    if not current_user.is_admin and db_booking.user_id != current_user.id:
        raise_problem(
            403,
            code="booking.forbidden",
            detail="You can only dismiss your own bookings",
        )
    if db_booking.status != "cancelled":
        raise_problem(
            400,
            code="booking.not_cancelled",
            detail="Only cancelled bookings can be dismissed",
        )
    await session.delete(db_booking)
    await session.commit()


def _shift_start_datetime(
    slot_date: dt.date, slot_start_time: dt.time | None
) -> dt.datetime:
    """Combine shift date + time into a naive UTC datetime."""
    if slot_start_time:
        return dt.datetime.combine(slot_date, slot_start_time)
    return dt.datetime.combine(slot_date, dt.time(0, 0))
