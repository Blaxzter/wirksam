import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel

from app.schemas.task import TaskRead

FeedView = Literal["list", "cards", "calendar"]
FeedFocusMode = Literal["today", "first_available"]


class FeedShiftEntry(BaseModel):
    """Lightweight shift for the feed — no title/description, just booking info."""

    id: uuid.UUID
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    max_bookings: int = 1
    current_bookings: int = 0
    is_booked_by_me: bool = False
    #: Overlaps a shift the user has already booked, so booking it would fail.
    collides_with_my_booking: bool = False
    #: The task needs a team the user is not an approved member of.
    locked_by_team: bool = False


class FeedTaskItem(TaskRead):
    """Task with view-dependent embedded data."""

    # List view: embedded shifts for the visible 5-day window
    shifts: list[FeedShiftEntry] | None = None
    slot_window_start: dt.date | None = None

    # Cards / calendar view: aggregated stats
    total_shifts: int | None = None
    available_shifts: int | None = None


class TaskFeedResponse(BaseModel):
    items: list[FeedTaskItem]
    total: int
    skip: int
    limit: int


class ShiftWindowResponse(BaseModel):
    """Response for the shift-window endpoint (next/prev day navigation)."""

    shifts: list[FeedShiftEntry]
    start_date: dt.date
    days: int
