"""Shapes for the /app/home dashboard.

The dashboard used to hand the browser three date ranges and let a calendar
work out what they meant. Nothing on it answered the two questions somebody
actually opens it for — *am I due anywhere?* and *where are people still
missing?* — so these schemas carry answers instead of raw rows: every shift
arrives with the job it belongs to, where to turn up, and how full it is.
"""

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class DashboardShift(BaseModel):
    """A shift the signed-in user has already committed to."""

    model_config = ConfigDict(from_attributes=True)

    booking_id: uuid.UUID
    shift_id: uuid.UUID
    task_id: uuid.UUID
    task_name: str
    event_id: uuid.UUID | None = None
    event_name: str | None = None
    title: str
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    location: str | None = None
    taken: int
    capacity: int


class DashboardOpenShift(BaseModel):
    """A shift that still has room, offered to the user to pick up."""

    model_config = ConfigDict(from_attributes=True)

    shift_id: uuid.UUID
    task_id: uuid.UUID
    task_name: str
    event_id: uuid.UUID | None = None
    event_name: str | None = None
    title: str
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    location: str | None = None
    taken: int
    capacity: int
    places_left: int


class DashboardAttention(BaseModel):
    """The organiser's to-do list, counted rather than listed.

    Only populated for someone who administers the event in scope; a plain
    member gets ``None`` and never sees the block.
    """

    pending_join_requests: int = 0
    # Requests to join one of the event's teams; an event admin decides all
    # of them, so this is the whole queue rather than a lead's share.
    pending_team_requests: int = 0
    draft_tasks: int = 0
    empty_shifts_soon: int = 0
    short_shifts_soon: int = 0
    horizon_days: int = 7


class DashboardFeedResponse(BaseModel):
    """Everything /app/home renders, in one request."""

    event_id: uuid.UUID | None = None
    event_name: str | None = None

    # What the user is on the hook for. Deliberately *not* scoped to the
    # selected event: a duty you have promised to turn up to is not something
    # to hide because the event switcher is pointing elsewhere.
    my_shifts: list[DashboardShift]
    my_shift_count: int
    my_minutes: int

    # Where help is still needed, scoped to the event in view.
    open_shifts: list[DashboardOpenShift]
    open_shift_count: int
    open_places: int

    attention: DashboardAttention | None = None

    # Kept top-level: the auth store raises the "people are waiting" toast off
    # this one number, across every event the user administers.
    pending_join_request_count: int = 0

    # Team requests the user may decide, across every event: all of them where
    # they are an event admin, those of the teams they lead elsewhere. Top
    # level because a team lead is no organiser and gets no ``attention``, yet
    # is the one the request is waiting on.
    pending_team_request_count: int = 0
