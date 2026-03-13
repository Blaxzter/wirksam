import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.schemas.event_group import EventGroupCreate, EventGroupRead

EventStatus = Literal["draft", "published", "archived"]


class EventBase(BaseModel):
    name: str
    description: str | None = None
    start_date: dt.date
    end_date: dt.date
    status: EventStatus = "draft"
    created_by_id: uuid.UUID | None = None
    event_group_id: uuid.UUID | None = None
    location: str | None = None
    category: str | None = None

    @field_validator("end_date")
    @classmethod
    def end_date_after_start(cls, v: dt.date, info: Any) -> dt.date:
        start = info.data.get("start_date")
        if start and v < start:
            msg = "end_date must be on or after start_date"
            raise ValueError(msg)
        return v


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    status: EventStatus | None = None
    event_group_id: uuid.UUID | None = None
    location: str | None = None
    category: str | None = None


class EventRead(EventBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    slot_duration_minutes: int | None = None
    default_start_time: dt.time | None = None
    default_end_time: dt.time | None = None
    people_per_slot: int | None = None
    schedule_overrides: list[dict[str, Any]] | None = None


class EventListResponse(BaseModel):
    items: list[EventRead]
    total: int
    skip: int
    limit: int


# --- Slot generation schemas ---


class ScheduleOverride(BaseModel):
    date: dt.date
    start_time: dt.time
    end_time: dt.time

    @model_validator(mode="after")
    def end_after_start(self) -> "ScheduleOverride":
        if self.end_time <= self.start_time:
            msg = "end_time must be after start_time"
            raise ValueError(msg)
        return self


RemainderMode = Literal["drop", "short", "extend"]


class ExcludedSlot(BaseModel):
    date: dt.date
    start_time: dt.time
    end_time: dt.time


class SlotGenerationConfig(BaseModel):
    default_start_time: dt.time
    default_end_time: dt.time
    slot_duration_minutes: int
    people_per_slot: int = 1
    remainder_mode: RemainderMode = "drop"
    overrides: list[ScheduleOverride] = []
    excluded_slots: list[ExcludedSlot] = []

    @field_validator("slot_duration_minutes")
    @classmethod
    def valid_duration(cls, v: int) -> int:
        if v < 1:
            msg = "slot_duration_minutes must be at least 1"
            raise ValueError(msg)
        return v

    @field_validator("people_per_slot")
    @classmethod
    def valid_people(cls, v: int) -> int:
        if v < 1:
            msg = "people_per_slot must be at least 1"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def end_after_start(self) -> "SlotGenerationConfig":
        if self.default_end_time <= self.default_start_time:
            msg = "default_end_time must be after default_start_time"
            raise ValueError(msg)
        return self


class EventCreateWithSlots(BaseModel):
    name: str
    description: str | None = None
    start_date: dt.date
    end_date: dt.date
    location: str | None = None
    category: str | None = None
    event_group_id: uuid.UUID | None = None
    new_event_group: EventGroupCreate | None = None
    schedule: SlotGenerationConfig

    @field_validator("end_date")
    @classmethod
    def end_date_after_start(cls, v: dt.date, info: Any) -> dt.date:
        start = info.data.get("start_date")
        if start and v < start:
            msg = "end_date must be on or after start_date"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_event_group(self) -> "EventCreateWithSlots":
        if self.event_group_id and self.new_event_group:
            msg = "Cannot specify both event_group_id and new_event_group"
            raise ValueError(msg)
        return self


class EventCreateWithSlotsResponse(BaseModel):
    event: EventRead
    duty_slots_created: int
    event_group: EventGroupRead | None = None


# --- Slot regeneration schemas ---


class EventUpdateWithSlots(BaseModel):
    name: str | None = None
    description: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    location: str | None = None
    category: str | None = None
    schedule: SlotGenerationConfig


class AddSlotsToEvent(BaseModel):
    start_date: dt.date
    end_date: dt.date
    location: str | None = None
    category: str | None = None
    schedule: SlotGenerationConfig

    @field_validator("end_date")
    @classmethod
    def end_date_after_start(cls, v: dt.date, info: Any) -> dt.date:
        start = info.data.get("start_date")
        if start and v < start:
            msg = "end_date must be on or after start_date"
            raise ValueError(msg)
        return v


class AddSlotsResponse(BaseModel):
    event: EventRead
    slots_added: int


class AffectedBookingInfo(BaseModel):
    booking_id: uuid.UUID
    user_id: uuid.UUID
    slot_title: str
    slot_date: dt.date
    slot_start_time: dt.time | None = None
    slot_end_time: dt.time | None = None


class SlotRegenerationResult(BaseModel):
    event: EventRead
    slots_added: int
    slots_removed: int
    slots_kept: int
    affected_bookings: list[AffectedBookingInfo]
