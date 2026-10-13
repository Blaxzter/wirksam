import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

BookingStatus = Literal["confirmed", "cancelled"]


class BookingBase(BaseModel):
    shift_id: uuid.UUID | None = None
    user_id: uuid.UUID
    status: BookingStatus = "confirmed"
    notes: str | None = None


class BookingCreate(BaseModel):
    """User only provides the shift and optional notes. user_id is set server-side."""

    shift_id: uuid.UUID
    notes: str | None = None


class BookingUpdate(BaseModel):
    status: BookingStatus | None = None
    notes: str | None = None
    cancellation_reason: str | None = None


class BookingRead(BookingBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    cancellation_reason: str | None = None
    cancelled_shift_title: str | None = None
    cancelled_shift_date: dt.date | None = None
    cancelled_shift_start_time: dt.time | None = None
    cancelled_shift_end_time: dt.time | None = None
    cancelled_task_name: str | None = None


class ShiftSummary(BaseModel):
    """Lightweight shift info nested inside a booking response."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    task_id: uuid.UUID
    title: str
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    location: str | None = None
    category: str | None = None
    task_name: str | None = None


class BookingReadWithShift(BookingRead):
    """BookingRead enriched with nested shift + task name (for /me endpoint)."""

    shift: ShiftSummary | None = None


class MyBookingsListResponse(BaseModel):
    items: list[BookingReadWithShift]
    total: int
    skip: int
    limit: int


class ShiftBookingEntry(BaseModel):
    """A confirmed booking for a shift, with basic user info."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str | None = None
    user_email: str | None = None
    user_avatar_etag: str | None = None
    user_phone_number: str | None = None
    notes: str | None = None
    created_at: dt.datetime


class TaskBookingEntry(BaseModel):
    """A confirmed booking with slot_id, for the bulk task bookings endpoint."""

    id: uuid.UUID
    shift_id: uuid.UUID
    user_name: str | None = None
    user_phone_number: str | None = None


class ShiftConflict(BaseModel):
    """The booked shift a new booking would overlap (``booking.time_conflict``)."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    task_id: uuid.UUID
    title: str
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    task_name: str | None = None
