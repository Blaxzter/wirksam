import datetime as dt
import uuid
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
)

from app.core.config import parse_timezone, settings
from app.logic import clock
from app.schemas.event_membership import EventRole

EventStatus = Literal["draft", "published", "archived"]
EventVisibility = Literal["public", "private"]
#: Who may redeem vouchers without a code, by picking the person: ``on_shift``
#: also whoever is on a running shift at that point, ``in_charge`` only the
#: event admins and the point's people in charge.
VoucherManualRedeem = Literal["on_shift", "in_charge"]
#: An IANA zone name; an unknown one is a 422. ``max_length`` is the column's:
#: no real name comes close.
EventTimezone = Annotated[
    str,
    Field(max_length=64, examples=["Europe/Berlin"]),
    AfterValidator(parse_timezone),
]


class EventBase(BaseModel):
    name: str
    description: str | None = None
    start_date: dt.date
    end_date: dt.date
    default_start_time: dt.time | None = None
    default_end_time: dt.time | None = None
    status: EventStatus = "draft"
    visibility: EventVisibility = "private"

    @field_validator("end_date")
    @classmethod
    def end_date_after_start(cls, v: dt.date, info: Any) -> dt.date:
        start = info.data.get("start_date")
        if start and v < start:
            msg = "end_date must be on or after start_date"
            raise ValueError(msg)
        return v

    @field_validator("default_end_time")
    @classmethod
    def default_end_time_after_start(
        cls, v: dt.time | None, info: Any
    ) -> dt.time | None:
        start = info.data.get("default_start_time")
        if start is not None and v is not None and v <= start:
            msg = (
                "default_end_time must be after default_start_time. "
                "Overnight windows are not yet supported — leave both empty for "
                "events that span midnight."
            )
            raise ValueError(msg)
        return v


class EventCreate(EventBase):
    created_by_id: uuid.UUID | None = None
    #: The zone the event's shift times are read in.
    timezone: EventTimezone = Field(default_factory=lambda: settings.EVENT_TIMEZONE)


class EventUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    default_start_time: dt.time | None = None
    default_end_time: dt.time | None = None
    status: EventStatus | None = None
    visibility: EventVisibility | None = None
    #: A shift at 10:00 stays at 10:00 and its reminders move with the zone. An
    #: explicit ``null`` leaves the value (NOT NULL).
    timezone: EventTimezone | None = None
    #: The event's voucher rules. Not on ``EventCreate``: a new event starts
    #: with the defaults. An explicit ``null`` leaves the value (NOT NULL).
    voucher_manual_redeem: VoucherManualRedeem | None = None
    managers_edit_voucher_shifts: bool | None = None


class EventRead(EventBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_by_id: uuid.UUID | None = None
    is_featured: bool = False
    is_sandbox: bool = False
    sandbox_expires_at: dt.datetime | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
    #: The IANA zone the event's shift times are read in.
    timezone: str
    #: Who may redeem vouchers without a code at this event's points.
    voucher_manual_redeem: VoucherManualRedeem = "on_shift"
    #: People in charge of a task that earns vouchers may change its shifts.
    managers_edit_voucher_shifts: bool = False

    # Viewer-relative context. Populated by the route from the caller's
    # membership, not stored on the row — the same event reads differently
    # for an owner, a member and a stranger browsing Discover.
    my_role: EventRole | None = None
    member_count: int = 0
    join_request_status: str | None = None
    pending_request_count: int = 0
    #: Plans with an image or at least one shape. A plan with neither (even
    #: one with pins on it) is unfinished editor state, so this is what
    #: decides whether members see the map at all.
    venue_plan_count: int = Field(
        default=0, description="plans with an image or at least one shape"
    )
    #: Teams in the event; members only (0 for a visitor browsing Discover),
    #: so the navigation can offer a Teams page only where there is one.
    team_count: int = 0
    #: Pending team requests the caller may decide: every one in an event
    #: they run, those of the teams they lead otherwise.
    pending_team_request_count: int = 0
    #: Published tasks that earn vouchers, and published tasks that take them
    #: (redemption points); members only, like ``team_count``. The navigation
    #: offers the voucher pages only where either is above zero.
    voucher_task_count: int = 0
    voucher_point_count: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def can_manage(self) -> bool:
        return self.my_role in ("owner", "admin")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_expired(self) -> bool:
        return self.end_date < clock.wall_clock_now(self.timezone).date()


class EventListResponse(BaseModel):
    items: list[EventRead]
    total: int
    skip: int
    limit: int
