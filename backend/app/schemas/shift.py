import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.schemas.event_team import TeamMemberStatus


class ShiftBase(BaseModel):
    task_id: uuid.UUID
    title: str
    description: str | None = None
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    location: str | None = None
    location_id: uuid.UUID | None = None
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
    location_id: uuid.UUID | None = None
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
    #: The event the shift's task belongs to, so a client can link to that
    #: event's pages rather than whichever event happens to be selected.
    event_id: uuid.UUID | None = None
    #: The team the shift's task requires, if any.
    team_id: uuid.UUID | None = None
    team_name: str | None = None
    #: Whether joining that team needs a lead's approval ("Ask to join") or
    #: is immediate ("Join").
    team_requires_approval: bool | None = None
    #: The caller's own standing in that team: pending, approved or declined.
    my_team_status: TeamMemberStatus | None = None
    #: The caller is not an approved member of that team, so booking would fail.
    locked_by_team: bool = False


class ShiftListResponse(BaseModel):
    items: list[ShiftRead]
    total: int
    skip: int
    limit: int
