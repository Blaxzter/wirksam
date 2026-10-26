import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.schemas.event import EventCreate, EventRead
from app.schemas.event_team import TeamMemberStatus

TaskStatus = Literal["draft", "published", "archived"]


class TaskBase(BaseModel):
    name: str
    description: str | None = None
    start_date: dt.date
    end_date: dt.date
    status: TaskStatus = "draft"
    created_by_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None
    location: str | None = None
    location_id: uuid.UUID | None = None
    category: str | None = None
    #: Only approved members of this team may book the task's shifts.
    team_id: uuid.UUID | None = None

    @field_validator("end_date")
    @classmethod
    def end_date_after_start(cls, v: dt.date, info: Any) -> dt.date:
        start = info.data.get("start_date")
        if start and v < start:
            msg = "end_date must be on or after start_date"
            raise ValueError(msg)
        return v


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    status: TaskStatus | None = None
    event_id: uuid.UUID | None = None
    location: str | None = None
    location_id: uuid.UUID | None = None
    category: str | None = None
    team_id: uuid.UUID | None = None


class TaskRead(TaskBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    shift_duration_minutes: int | None = None
    default_start_time: dt.time | None = None
    default_end_time: dt.time | None = None
    people_per_shift: int | None = None
    schedule_overrides: list[dict[str, Any]] | None = None
    #: Viewer-relative, filled in by the read routes (task page and feed) for
    #: a task with a team: the team's name, whether joining it needs approval,
    #: the caller's standing in it, and whether that bars them from booking.
    team_name: str | None = None
    team_requires_approval: bool | None = None
    my_team_status: TeamMemberStatus | None = None
    locked_by_team: bool = False


class TaskListResponse(BaseModel):
    items: list[TaskRead]
    total: int
    skip: int
    limit: int


# --- Shift generation schemas ---


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


class ExcludedShift(BaseModel):
    date: dt.date
    start_time: dt.time
    end_time: dt.time


class ShiftGenerationConfig(BaseModel):
    default_start_time: dt.time
    default_end_time: dt.time
    shift_duration_minutes: int
    people_per_shift: int = 1
    remainder_mode: RemainderMode = "drop"
    overrides: list[ScheduleOverride] = []
    excluded_shifts: list[ExcludedShift] = []
    #: Restrict generation to these calendar dates. The "specific dates" mode in
    #: the task wizard lets the user pick non-contiguous days; without this the
    #: request can only say start_date=min, end_date=max, and every day in
    #: between gets shifts the user was never shown (#144).
    #:
    #: `None` and `[]` both mean "no restriction", matching the frontend
    #: preview's `specificDates?.length ? … : null`. Dates outside
    #: [start_date, end_date] are simply never reached.
    specific_dates: list[dt.date] | None = None

    @field_validator("shift_duration_minutes")
    @classmethod
    def valid_duration(cls, v: int) -> int:
        if v < 1:
            msg = "shift_duration_minutes must be at least 1"
            raise ValueError(msg)
        return v

    @field_validator("people_per_shift")
    @classmethod
    def valid_people(cls, v: int) -> int:
        if v < 1:
            msg = "people_per_shift must be at least 1"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def end_after_start(self) -> "ShiftGenerationConfig":
        if self.default_end_time <= self.default_start_time:
            msg = "default_end_time must be after default_start_time"
            raise ValueError(msg)
        return self


class TaskCreateWithShifts(BaseModel):
    name: str
    description: str | None = None
    start_date: dt.date
    end_date: dt.date
    status: TaskStatus = "draft"
    location: str | None = None
    location_id: uuid.UUID | None = None
    category: str | None = None
    team_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None
    new_event: EventCreate | None = None
    schedule: ShiftGenerationConfig

    @field_validator("end_date")
    @classmethod
    def end_date_after_start(cls, v: dt.date, info: Any) -> dt.date:
        start = info.data.get("start_date")
        if start and v < start:
            msg = "end_date must be on or after start_date"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_event(self) -> "TaskCreateWithShifts":
        if self.event_id and self.new_event:
            msg = "Cannot specify both event_id and new_event"
            raise ValueError(msg)
        return self


class TaskCreateWithShiftsResponse(BaseModel):
    task: TaskRead
    shifts_created: int
    event: EventRead | None = None


# --- Shift regeneration schemas ---


class TaskUpdateWithShifts(BaseModel):
    name: str | None = None
    description: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    location: str | None = None
    location_id: uuid.UUID | None = None
    category: str | None = None
    schedule: ShiftGenerationConfig


class AddShiftsToTask(BaseModel):
    start_date: dt.date
    end_date: dt.date
    location: str | None = None
    location_id: uuid.UUID | None = None
    category: str | None = None
    schedule: ShiftGenerationConfig

    @field_validator("end_date")
    @classmethod
    def end_date_after_start(cls, v: dt.date, info: Any) -> dt.date:
        start = info.data.get("start_date")
        if start and v < start:
            msg = "end_date must be on or after start_date"
            raise ValueError(msg)
        return v


class AddShiftsResponse(BaseModel):
    task: TaskRead
    shifts_added: int


class AffectedBookingInfo(BaseModel):
    booking_id: uuid.UUID
    user_id: uuid.UUID
    slot_title: str
    slot_date: dt.date
    slot_start_time: dt.time | None = None
    slot_end_time: dt.time | None = None


class ShiftRegenerationResult(BaseModel):
    task: TaskRead
    shifts_added: int
    shifts_removed: int
    shifts_kept: int
    affected_bookings: list[AffectedBookingInfo]
