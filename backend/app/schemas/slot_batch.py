import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.event import RemainderMode


class SlotBatchBase(BaseModel):
    event_id: uuid.UUID
    label: str | None = None
    start_date: dt.date
    end_date: dt.date
    location: str | None = None
    category: str | None = None
    default_start_time: dt.time | None = None
    default_end_time: dt.time | None = None
    slot_duration_minutes: int | None = None
    people_per_slot: int | None = None
    remainder_mode: RemainderMode | None = "drop"
    schedule_overrides: list[dict[str, Any]] | None = None


class SlotBatchCreate(SlotBatchBase):
    pass


class SlotBatchUpdate(BaseModel):
    label: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    location: str | None = None
    category: str | None = None
    default_start_time: dt.time | None = None
    default_end_time: dt.time | None = None
    slot_duration_minutes: int | None = None
    people_per_slot: int | None = None
    remainder_mode: RemainderMode | None = None
    schedule_overrides: list[dict[str, Any]] | None = None


class SlotBatchRead(SlotBatchBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
