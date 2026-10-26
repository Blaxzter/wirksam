import datetime as dt
import uuid

from pydantic import BaseModel


class SidebarEvent(BaseModel):
    id: uuid.UUID
    name: str
    status: str = "published"


class SidebarTask(BaseModel):
    id: uuid.UUID
    name: str
    status: str = "published"
    open_shifts: int
    next_shift_date: dt.date | None = None
    next_shift_start_time: dt.time | None = None
    #: The team the task is reserved for, if any.
    team_name: str | None = None
    #: Reserved for a team the viewer is not in (and not an event admin).
    locked_by_team: bool = False


class SidebarBooking(BaseModel):
    id: uuid.UUID
    slot_id: uuid.UUID
    task_id: uuid.UUID
    slot_title: str
    slot_date: dt.date
    slot_start_time: dt.time | None = None


class SidebarResponse(BaseModel):
    events: list[SidebarEvent]
    tasks: list[SidebarTask]
    bookings: list[SidebarBooking]
