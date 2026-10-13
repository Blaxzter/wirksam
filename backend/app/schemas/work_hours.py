import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.event_membership import EventRole

# One entry covers at most a day; anything longer is several entries.
MAX_WORK_LOG_MINUTES = 24 * 60


class WorkLogCreate(BaseModel):
    user_id: uuid.UUID
    date: dt.date
    minutes: int = Field(gt=0, le=MAX_WORK_LOG_MINUTES)
    description: str = Field(min_length=1, max_length=500)


class WorkLogUpdate(BaseModel):
    date: dt.date | None = None
    minutes: int | None = Field(default=None, gt=0, le=MAX_WORK_LOG_MINUTES)
    description: str | None = Field(default=None, min_length=1, max_length=500)


class WorkLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    user_id: uuid.UUID
    date: dt.date
    minutes: int
    description: str
    created_by_id: uuid.UUID | None = None
    created_by_name: str | None = None
    created_at: dt.datetime


class VolunteerHours(BaseModel):
    """One person's hours in one event.

    ``shift_minutes`` counts confirmed bookings on shifts that have already
    ended; ``upcoming_shift_minutes`` the ones still ahead. Only the former goes
    into ``total_minutes`` — hours are what someone *has* worked.
    """

    user_id: uuid.UUID
    name: str | None = None
    email: str | None = None
    avatar_etag: str | None = None
    role: EventRole | None = Field(
        default=None,
        description="Current role in the event; None once they have left it",
    )
    shift_count: int
    shift_minutes: int
    upcoming_shift_count: int
    upcoming_shift_minutes: int
    untimed_shift_count: int = Field(
        description="Worked shifts with no start or end time, counted as 0 minutes"
    )
    manual_minutes: int
    total_minutes: int


class WorkedShift(BaseModel):
    booking_id: uuid.UUID
    shift_id: uuid.UUID
    task_name: str
    title: str
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    minutes: int
    completed: bool


class VolunteerHoursDetail(BaseModel):
    summary: VolunteerHours
    shifts: list[WorkedShift]
    work_logs: list[WorkLogRead]
