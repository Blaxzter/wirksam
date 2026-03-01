import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class DutySlotBase(BaseModel):
    event_id: uuid.UUID
    title: str
    description: str | None = None
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    location: str | None = None
    category: str | None = None
    max_bookings: int = 1


class DutySlotCreate(DutySlotBase):
    pass


class DutySlotUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    date: dt.date | None = None
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    location: str | None = None
    category: str | None = None
    max_bookings: int | None = None


class DutySlotRead(DutySlotBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    current_bookings: int = 0


class DutySlotListResponse(BaseModel):
    items: list[DutySlotRead]
    total: int
    skip: int
    limit: int
