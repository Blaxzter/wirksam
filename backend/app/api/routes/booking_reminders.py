import datetime as dt
import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.crud.duty_slot import duty_slot as crud_duty_slot
from app.models.booking_reminder import BookingReminder
from app.schemas.booking_reminder import (
    MAX_REMINDERS_PER_BOOKING,
    BookingReminderCreate,
    BookingReminderListResponse,
    BookingReminderRead,
    DefaultReminderOffsetsRead,
    DefaultReminderOffsetsUpdate,
)

router = APIRouter(tags=["booking-reminders"])


# ── Default reminder offsets (user-level) ────────────────────────


@router.get("/users/me/reminder-defaults", response_model=DefaultReminderOffsetsRead)
async def get_reminder_defaults(
    current_user: CurrentUser,
) -> DefaultReminderOffsetsRead:
    """Get the current user's default reminder offsets."""
    return DefaultReminderOffsetsRead(
        default_reminder_offsets=current_user.default_reminder_offsets,
    )


@router.put("/users/me/reminder-defaults", response_model=DefaultReminderOffsetsRead)
async def update_reminder_defaults(
    body: DefaultReminderOffsetsUpdate,
    session: DBDep,
    current_user: CurrentUser,
) -> DefaultReminderOffsetsRead:
    """Update the current user's default reminder offsets."""
    # Deduplicate by offset_minutes, sort by offset
    deduped = {e.offset_minutes: e for e in body.default_reminder_offsets}
    sorted_entries = sorted(deduped.values(), key=lambda e: e.offset_minutes)
    current_user.default_reminder_offsets = [e.model_dump() for e in sorted_entries]  # type: ignore[assignment]
    session.add(current_user)
    await session.flush()
    await session.refresh(current_user)
    return DefaultReminderOffsetsRead(
        default_reminder_offsets=body.default_reminder_offsets,
    )


# ── Per-booking reminders ────────────────────────────────────────


@router.get(
    "/bookings/{booking_id}/reminders",
    response_model=BookingReminderListResponse,
)
async def list_booking_reminders(
    booking_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> BookingReminderListResponse:
    """List reminders for a booking."""
    db_booking = await crud_booking.get(session, str(booking_id), raise_404_error=True)
    if not current_user.is_admin and db_booking.user_id != current_user.id:
        raise_problem(
            403,
            code="reminder.forbidden",
            detail="You can only view your own reminders",
        )
    reminders = await crud_reminder.get_by_booking(session, booking_id=booking_id)
    return BookingReminderListResponse(items=reminders)  # type: ignore[arg-type]


@router.post(
    "/bookings/{booking_id}/reminders",
    response_model=BookingReminderRead,
    status_code=201,
)
async def add_booking_reminder(
    booking_id: uuid.UUID,
    body: BookingReminderCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> BookingReminder:
    """Add a reminder to an existing booking."""
    db_booking = await crud_booking.get(session, str(booking_id), raise_404_error=True)
    if not current_user.is_admin and db_booking.user_id != current_user.id:
        raise_problem(
            403,
            code="reminder.forbidden",
            detail="You can only manage your own reminders",
        )
    if db_booking.status != "confirmed":
        raise_problem(
            400,
            code="reminder.booking_not_confirmed",
            detail="Booking is not confirmed",
        )
    if not db_booking.duty_slot_id:
        raise_problem(400, code="reminder.no_slot", detail="Booking has no linked slot")

    # Check max reminders
    count = await crud_reminder.count_by_booking(session, booking_id=booking_id)
    if count >= MAX_REMINDERS_PER_BOOKING:
        raise_problem(
            422,
            code="reminder.too_many",
            detail=f"Maximum {MAX_REMINDERS_PER_BOOKING} reminders per booking",
        )

    slot = await crud_duty_slot.get(
        session, str(db_booking.duty_slot_id), raise_404_error=True
    )

    # Compute slot start datetime
    slot_start = _slot_start_datetime(slot.date, slot.start_time)

    return await crud_reminder.create_reminder(
        session,
        booking_id=booking_id,
        user_id=current_user.id,
        duty_slot_id=slot.id,
        offset_minutes=body.offset_minutes,
        slot_start=slot_start,
        channels=body.channels,
    )


@router.delete("/reminders/{reminder_id}", status_code=204)
async def delete_reminder(
    reminder_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Delete (cancel) a specific reminder."""
    reminder = await crud_reminder.get(session, str(reminder_id))
    if not reminder:
        raise_problem(404, code="reminder.not_found", detail="Reminder not found")
    if not current_user.is_admin and reminder.user_id != current_user.id:
        raise_problem(
            403,
            code="reminder.forbidden",
            detail="You can only delete your own reminders",
        )
    await session.delete(reminder)


def _slot_start_datetime(
    slot_date: dt.date, slot_start_time: dt.time | None
) -> dt.datetime:
    """Combine slot date + time into a naive UTC datetime."""
    if slot_start_time:
        return dt.datetime.combine(slot_date, slot_start_time)
    # If no start time, default to start of day
    return dt.datetime.combine(slot_date, dt.time(0, 0))
