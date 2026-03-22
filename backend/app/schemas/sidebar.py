import datetime as dt
import uuid

from pydantic import BaseModel


class SidebarEventGroup(BaseModel):
    id: uuid.UUID
    name: str


class SidebarEvent(BaseModel):
    id: uuid.UUID
    name: str
    open_slots: int
    next_slot_date: dt.date | None = None
    next_slot_start_time: dt.time | None = None


class SidebarBooking(BaseModel):
    id: uuid.UUID
    slot_id: uuid.UUID
    event_id: uuid.UUID
    slot_title: str
    slot_date: dt.date
    slot_start_time: dt.time | None = None


class SidebarResponse(BaseModel):
    event_groups: list[SidebarEventGroup]
    events: list[SidebarEvent]
    bookings: list[SidebarBooking]
