import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

BookingStatus = Literal["confirmed", "cancelled"]


class BookingBase(BaseModel):
    duty_slot_id: uuid.UUID | None = None
    user_id: uuid.UUID
    status: BookingStatus = "confirmed"
    notes: str | None = None


class BookingCreate(BaseModel):
    """User only provides the slot and optional notes. user_id is set server-side."""

    duty_slot_id: uuid.UUID
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
    cancelled_slot_title: str | None = None
    cancelled_slot_date: dt.date | None = None
    cancelled_slot_start_time: dt.time | None = None
    cancelled_slot_end_time: dt.time | None = None
    cancelled_event_name: str | None = None


class DutySlotSummary(BaseModel):
    """Lightweight slot info nested inside a booking response."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_id: uuid.UUID
    title: str
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    location: str | None = None
    category: str | None = None
    event_name: str | None = None


class BookingReadWithSlot(BookingRead):
    """BookingRead enriched with nested slot + event name (for /me endpoint)."""

    duty_slot: DutySlotSummary | None = None


class MyBookingsListResponse(BaseModel):
    items: list[BookingReadWithSlot]
    total: int
    skip: int
    limit: int


class SlotBookingEntry(BaseModel):
    """A confirmed booking for a slot, with basic user info."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str | None = None
    user_email: str | None = None
    user_picture: str | None = None
    notes: str | None = None
    created_at: dt.datetime
