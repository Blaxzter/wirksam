import datetime as dt
import uuid
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
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
#: The colours an event wears while it is open; ``None`` keeps the app's own.
#: A preset, tuned for contrast in ``frontend/src/index.css``, or an own colour
#: (``HexColour``). The presets must list the same names as
#: ``EVENT_PRIMARY_COLORS`` / ``EVENT_SECONDARY_COLORS`` / ``EVENT_BASE_COLORS``
#: in ``app.models.event``.
EventPrimaryColor = Literal["red", "orange", "teal", "blue", "violet", "pink", "slate"]
EventSecondaryColor = Literal[
    "red", "orange", "yellow", "green", "teal", "blue", "violet", "pink", "slate"
]
#: The tone of the background, cards and menu. ``primary`` follows the main
#: colour, ``neutral`` is grey without a tint.
EventBaseColor = Literal[
    "neutral", "primary", "blue", "teal", "green", "rose", "violet"
]
#: An own colour, ``#1e6bb8``; stored lower-case. The frontend keeps its hue and
#: moves its lightness as far as WCAG AA needs, so any colour is accepted.
HexColour = Annotated[
    str,
    StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$", to_lower=True),
    Field(examples=["#1e6bb8"]),
]
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
    primary_color: EventPrimaryColor | HexColour | None = None
    secondary_color: EventSecondaryColor | HexColour | None = None
    base_color: EventBaseColor | HexColour | None = None

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
    #: Whether people in charge may share their tasks on shared lists. An
    #: explicit ``null`` leaves the value (NOT NULL).
    managers_share_lists: bool | None = None
    #: An explicit ``null`` goes back to the app's own colour.
    primary_color: EventPrimaryColor | HexColour | None = None
    secondary_color: EventSecondaryColor | HexColour | None = None
    base_color: EventBaseColor | HexColour | None = None
    #: Whether dark mode puts the logo on a white tile. An explicit ``null``
    #: leaves the value (NOT NULL).
    logo_dark_tile: bool | None = None


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
    #: People in charge may create, edit, resume and rotate shared lists of
    #: their own tasks; pausing and ending stay theirs either way.
    managers_share_lists: bool = True
    #: Version of the event's logo, ``None`` without one. The image is at
    #: ``GET /events/{id}/logo``; append ``?v=<etag>`` so a new one busts caches.
    logo_etag: str | None = None
    #: The stored logo's size in pixels, so a wordmark can be told from a mark
    #: before the image loads.
    logo_width: int | None = None
    logo_height: int | None = None
    #: The same for the optional logo for dark mode, at
    #: ``GET /events/{id}/logo/dark``. Without one, dark mode shows the logo.
    logo_dark_etag: str | None = None
    logo_dark_width: int | None = None
    logo_dark_height: int | None = None
    #: Whether dark mode puts the logo on a white tile.
    logo_dark_tile: bool = True

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
    #: Tasks of the event the caller is in charge of; members only, like
    #: ``team_count``. The navigation offers shared lists to people in charge
    #: who are not event admins only where this is above zero.
    managed_task_count: int = 0

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
