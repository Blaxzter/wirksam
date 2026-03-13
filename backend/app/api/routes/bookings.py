import datetime as dt

from fastapi import APIRouter, BackgroundTasks, Query

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.duty_slot import duty_slot as crud_duty_slot
from app.logic.notifications.triggers import (
    dispatch_booking_cancelled_by_user,
    dispatch_booking_cobooked,
    dispatch_booking_confirmed,
)
from app.models.booking import Booking
from app.schemas.booking import (
    BookingBase,
    BookingCreate,
    BookingRead,
    BookingReadWithSlot,
    BookingUpdate,
    DutySlotSummary,
    MyBookingsListResponse,
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
) -> MyBookingsListResponse:
    """List the current user's bookings with joined slot + event data."""
    items = await crud_booking.get_multi_by_user(
        session,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        status=status,
        with_slot=True,
        date_from=date_from,
        date_to=date_to,
    )
    total = await crud_booking.count_by_user(
        session, user_id=current_user.id, status=status,
        date_from=date_from, date_to=date_to,
    )

    enriched: list[BookingReadWithSlot] = []
    for b in items:
        bws = BookingReadWithSlot.model_validate(b)
        if b.duty_slot is not None:
            slot_summary = DutySlotSummary.model_validate(b.duty_slot)
            slot_summary.event_name = (
                b.duty_slot.event.name if b.duty_slot.event else None
            )
            bws.duty_slot = slot_summary
        enriched.append(bws)

    return MyBookingsListResponse(
        items=enriched,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/", response_model=BookingRead, status_code=201)
async def create_booking(
    booking_in: BookingCreate,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> Booking:
    """Book a duty slot for the current user."""
    slot = await crud_duty_slot.get(
        session, str(booking_in.duty_slot_id), raise_404_error=True
    )

    existing = await crud_booking.get_by_slot_and_user(
        session, duty_slot_id=slot.id, user_id=current_user.id
    )
    if existing and existing.status == "confirmed":
        raise_problem(
            409,
            code="booking.already_exists",
            detail="You already have a confirmed booking for this slot",
        )

    confirmed_count = await crud_booking.get_confirmed_count(
        session, duty_slot_id=slot.id
    )
    if confirmed_count >= slot.max_bookings:
        raise_problem(
            409, code="booking.slot_full", detail="This duty slot is fully booked"
        )

    # Collect existing confirmed bookers for co-booking notification
    existing_bookings = await crud_booking.get_multi_by_slot(
        session, duty_slot_id=slot.id, status="confirmed"
    )
    existing_user_ids = [b.user_id for b in existing_bookings if b.user_id != current_user.id]

    # If previously cancelled, reactivate
    if existing and existing.status == "cancelled":
        result = await crud_booking.update(
            session,
            db_obj=existing,
            obj_in=BookingUpdate(status="confirmed", notes=booking_in.notes),
        )
    else:
        full_booking = BookingBase(
            duty_slot_id=booking_in.duty_slot_id,
            user_id=current_user.id,
            notes=booking_in.notes,
        )
        result = await crud_booking.create(session, obj_in=full_booking)  # type: ignore[arg-type]

    # Dispatch notifications
    background_tasks.add_task(
        dispatch_booking_confirmed,
        booking_id=result.id,
        user_id=current_user.id,
        slot_title=slot.title,
        slot_id=slot.id,
        event_id=slot.event_id,
        event_group_id=None,
    )
    if existing_user_ids:
        background_tasks.add_task(
            dispatch_booking_cobooked,
            slot_id=slot.id,
            slot_title=slot.title,
            event_id=slot.event_id,
            new_user_name=current_user.name,
            existing_user_ids=existing_user_ids,
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

    # Dispatch cancellation notification
    if db_booking.duty_slot_id:
        slot = await crud_duty_slot.get(session, str(db_booking.duty_slot_id))
        if slot:
            background_tasks.add_task(
                dispatch_booking_cancelled_by_user,
                booking_id=result.id,
                user_id=db_booking.user_id,
                slot_title=slot.title,
                slot_id=slot.id,
                event_id=slot.event_id,
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
