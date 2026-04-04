import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReminderStatus = Literal["pending", "sent", "cancelled", "expired"]
AllowedOffset = Literal[15, 30, 60, 120, 180, 360, 720, 1440, 2880]
AllowedChannel = Literal["email", "push", "telegram"]

MAX_REMINDERS_PER_BOOKING = 5


class BookingReminderCreate(BaseModel):
    """User provides the offset and channels; remind_at is computed server-side."""

    offset_minutes: AllowedOffset
    channels: list[AllowedChannel] = Field(default=["push"], min_length=1)


class BookingReminderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    offset_minutes: int
    channels: list[str]
    remind_at: dt.datetime
    status: ReminderStatus
    created_at: dt.datetime


class BookingReminderListResponse(BaseModel):
    items: list[BookingReminderRead]


class ReminderOffsetEntry(BaseModel):
    """A single default reminder: offset + which channels to use."""

    offset_minutes: AllowedOffset
    channels: list[AllowedChannel] = Field(default=["push"], min_length=1)


class DefaultReminderOffsetsRead(BaseModel):
    default_reminder_offsets: list[ReminderOffsetEntry]


class DefaultReminderOffsetsUpdate(BaseModel):
    default_reminder_offsets: list[ReminderOffsetEntry] = Field(
        max_length=MAX_REMINDERS_PER_BOOKING
    )
