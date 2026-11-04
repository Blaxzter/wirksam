import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.event import EventCreate, EventRead
from app.schemas.event_team import TeamMemberStatus
from app.schemas.task_manager import TaskManagerBrief, TaskManagerInviteResult

TaskStatus = Literal["draft", "published", "archived"]

#: The most vouchers one shift of a task may earn.
MAX_VOUCHERS_PER_SHIFT = 50


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
    #: Vouchers a volunteer earns for each confirmed shift once it is over.
    #: 0 means none. A change only affects shifts that are not over yet: what
    #: ended shifts earned is settled first and stays.
    vouchers_per_shift: int = Field(default=0, ge=0, le=MAX_VOUCHERS_PER_SHIFT)
    #: Vouchers can be redeemed here, in the app. Who may also redeem without
    #: a code is the event's ``voucher_manual_redeem``.
    is_voucher_point: bool = False

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
    vouchers_per_shift: int | None = Field(
        default=None, ge=0, le=MAX_VOUCHERS_PER_SHIFT
    )
    is_voucher_point: bool | None = None


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
    #: Viewer-relative, filled in by ``app.logic.task_managers``: True for event
    #: admins, the superadmin and the task's people in charge.
    can_manage: bool = False
    #: Viewer-relative: the caller may add, move, resize and delete this
    #: task's shifts. True for event admins; for people in charge unless the
    #: task earns vouchers and the event keeps those shifts with its admins
    #: (``permissions.voucher_shifts_locked``).
    can_manage_shifts: bool = False
    #: The task's people in charge, by name.
    managers: list[TaskManagerBrief] = []
    #: Viewer-relative: the task takes vouchers and the caller may redeem
    #: them here right now (an event admin, a person in charge, or on a
    #: running shift of it).
    can_redeem: bool = False


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
    vouchers_per_shift: int = Field(default=0, ge=0, le=MAX_VOUCHERS_PER_SHIFT)
    is_voucher_point: bool = False
    event_id: uuid.UUID | None = None
    new_event: EventCreate | None = None
    schedule: ShiftGenerationConfig
    #: Members of ``event_id`` to put in charge of the new task. Not on
    #: ``TaskCreate``: ``TaskBase`` is also the base of ``TaskRead``.
    manager_ids: list[uuid.UUID] = []
    #: Addresses to put in charge: a member's is added like ``manager_ids``,
    #: anyone else is invited (``POST /tasks/{id}/managers/invite``). Each
    #: outcome comes back in ``manager_invites``.
    manager_emails: list[EmailStr] = Field(default=[], max_length=20)

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

    @model_validator(mode="after")
    def dedupe_manager_emails(self) -> "TaskCreateWithShifts":
        """One entry per address, whatever its case; the first spelling wins."""
        seen: set[str] = set()
        unique: list[EmailStr] = []
        for address in self.manager_emails:
            key = str(address).lower()
            if key not in seen:
                seen.add(key)
                unique.append(address)
        self.manager_emails = unique
        return self


class TaskCreateWithShiftsResponse(BaseModel):
    task: TaskRead
    shifts_created: int
    event: EventRead | None = None
    #: One result per address in ``manager_emails``: ``added``, ``invited``,
    #: or ``skipped`` (a daily limit, or a demo event) instead of failing the
    #: task the organiser just built. The address of someone already named in
    #: ``manager_ids`` is left out.
    manager_invites: list[TaskManagerInviteResult] = []


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
    #: The booker's name, so whoever confirms the regenerate can tell them.
    user_name: str | None = None
    slot_title: str
    slot_date: dt.date
    slot_start_time: dt.time | None = None
    slot_end_time: dt.time | None = None
    #: Only an event admin may remove this shift: it has started and people
    #: are booked on it (``permissions.check_shift_history``). Always False
    #: for event admins.
    locked: bool = False


class ShiftRegenerationResult(BaseModel):
    task: TaskRead
    shifts_added: int
    shifts_removed: int
    shifts_kept: int
    affected_bookings: list[AffectedBookingInfo]
