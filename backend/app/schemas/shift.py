import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class ShiftBase(BaseModel):
    task_id: uuid.UUID
    title: str
    description: str | None = None
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    location: str | None = None
    category: str | None = None
    max_bookings: int = 1
    batch_id: uuid.UUID | None = None


class ShiftCreate(ShiftBase):
    pass


class ShiftUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    date: dt.date | None = None
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    location: str | None = None
    category: str | None = None
    max_bookings: int | None = None


class ShiftRead(ShiftBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    current_bookings: int = 0
    is_booked_by_me: bool = False
    #: Overlaps a shift the user has already booked, so booking it would fail.
    collides_with_my_booking: bool = False


class ShiftListResponse(BaseModel):
    items: list[ShiftRead]
    total: int
    skip: int
    limit: int
