import datetime as dt
import uuid
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

TeamRole = Literal["member", "lead"]
TeamMemberStatus = Literal["pending", "approved", "declined"]

# Stripped before the length check, like LocationName, so "   " is refused
# rather than stored as a team nobody can tell apart.
TeamName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
RequirementLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]

#: At most this many requirements per team. A real team needs two or three;
#: the cap keeps a single request from writing hundreds of rows.
MAX_REQUIREMENTS = 10


def _blank_to_none(value: Any) -> Any:
    """Treat an empty or whitespace-only optional field as "not set"."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


# --- Requirements -------------------------------------------------------


class TeamRequirementIn(BaseModel):
    """One thing a decider has to check before approving a request.

    On an update, an item with an ``id`` edits that requirement and an item
    without one adds a new one; requirements left out are deleted together
    with the checks recorded against them.
    """

    id: uuid.UUID | None = None
    label: RequirementLabel
    description: str | None = Field(default=None, max_length=2000)
    ask_issue_date: bool = False
    valid_for_years: int | None = Field(default=None, ge=1, le=50)
    accepts_document: bool = False

    @field_validator("description", mode="before")
    @classmethod
    def _blank_description(cls, value: Any) -> Any:
        return _blank_to_none(value)


def _unique_labels(requirements: list[TeamRequirementIn] | None) -> None:
    if not requirements:
        return
    seen: set[str] = set()
    for req in requirements:
        key = req.label.lower()
        if key in seen:
            raise ValueError(f'The requirement "{req.label}" is listed twice')
        seen.add(key)


class TeamRequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    description: str | None = None
    ask_issue_date: bool
    valid_for_years: int | None = None
    accepts_document: bool


# --- Teams --------------------------------------------------------------


class EventTeamCreate(BaseModel):
    name: TeamName
    description: str | None = Field(default=None, max_length=2000)
    contact: str | None = Field(default=None, max_length=255)
    requires_approval: bool = True
    requirements: list[TeamRequirementIn] = Field(
        default_factory=list, max_length=MAX_REQUIREMENTS
    )

    @field_validator("description", "contact", mode="before")
    @classmethod
    def _blank_optional_to_none(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def _labels_unique(self) -> "EventTeamCreate":
        _unique_labels(self.requirements)
        return self


class EventTeamUpdate(BaseModel):
    """Partial update; apply with ``model_dump(exclude_unset=True)``.

    ``requirements`` replaces the whole list when sent (see
    :class:`TeamRequirementIn`); leave it out to keep the current ones.
    """

    name: TeamName | None = None
    description: str | None = Field(default=None, max_length=2000)
    contact: str | None = Field(default=None, max_length=255)
    requires_approval: bool | None = None
    requirements: list[TeamRequirementIn] | None = Field(
        default=None, max_length=MAX_REQUIREMENTS
    )

    @field_validator("description", "contact", mode="before")
    @classmethod
    def _blank_optional_to_none(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("name", "requires_approval", "requirements")
    @classmethod
    def _not_null(cls, value: Any) -> Any:
        # Only runs when the client sent the field: leaving it out is fine,
        # sending an explicit null for a column that cannot be empty is not.
        if value is None:
            raise ValueError("This field cannot be empty")
        return value

    @model_validator(mode="after")
    def _labels_unique(self) -> "EventTeamUpdate":
        _unique_labels(self.requirements)
        return self


class TeamDocumentRead(BaseModel):
    """What is known about an attached file without downloading it."""

    model_config = ConfigDict(from_attributes=True)

    requirement_id: uuid.UUID
    filename: str
    content_type: str
    size: int
    uploaded_at: dt.datetime


class TeamTaskRead(BaseModel):
    """A task a team unlocks, for a link to it from the team."""

    id: uuid.UUID
    name: str
    #: Its shifts still to come with a free place.
    open_shift_count: int = 0


class EventTeamRead(BaseModel):
    """A team, decorated with what the caller needs to render it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    name: str
    description: str | None = None
    contact: str | None = None
    requires_approval: bool
    created_at: dt.datetime
    requirements: list[TeamRequirementRead] = []
    member_count: int = 0
    #: Only filled in for callers who may decide requests; 0 otherwise.
    pending_count: int = 0
    task_count: int = 0
    #: The tasks the team unlocks, as the caller can see them (published
    #: ones only, unless the caller runs the event), alphabetically.
    tasks: list[TeamTaskRead] = []
    #: Shifts of those tasks still to come with a free place, all together.
    open_shift_count: int = 0
    #: Who decides requests: the approved leads, by name.
    lead_names: list[str] = []
    #: The caller's own row, if any.
    my_status: TeamMemberStatus | None = None
    my_role: TeamRole | None = None
    #: When the caller asked (their row's creation), for "you asked on …".
    my_requested_at: dt.datetime | None = None
    #: Files the caller attached to their pending request.
    my_documents: list[TeamDocumentRead] = []
    #: The caller is approved, but a check of theirs has expired or is missing.
    my_needs_recheck: bool = False
    #: Whether the caller may decide requests and edit the roster.
    can_manage: bool = False


# --- Joining and deciding -----------------------------------------------


class EventTeamJoin(BaseModel):
    message: str | None = Field(default=None, max_length=500)

    @field_validator("message", mode="before")
    @classmethod
    def _blank_message(cls, value: Any) -> Any:
        return _blank_to_none(value)


class TeamCheckIn(BaseModel):
    """The decider ticked this requirement off.

    ``issued_on`` is required when the requirement asks for the issue date
    and ignored otherwise.
    """

    requirement_id: uuid.UUID
    issued_on: dt.date | None = None


class EventTeamDecision(BaseModel):
    approve: bool
    #: Approving a team with requirements needs one entry per requirement.
    checks: list[TeamCheckIn] = Field(default_factory=list, max_length=50)


class EventTeamMemberAdd(BaseModel):
    """Place an event member straight into a team, skipping the request.

    Needs the same checks as approving a request when the team has
    requirements.
    """

    user_id: uuid.UUID
    role: TeamRole = "member"
    checks: list[TeamCheckIn] = Field(default_factory=list, max_length=50)


class EventTeamMemberRoleUpdate(BaseModel):
    role: TeamRole


class TeamChecksUpdate(BaseModel):
    """Record or renew checks for someone already in the team."""

    checks: list[TeamCheckIn] = Field(min_length=1, max_length=50)


class TeamCheckRead(BaseModel):
    requirement_id: uuid.UUID
    label: str
    checked_by_name: str | None = None
    checked_at: dt.datetime
    issued_on: dt.date | None = None
    expires_on: dt.date | None = None
    expired: bool = False
    #: Set on a reusable check: the other team of the same event it was
    #: recorded for. None on the member's own checks.
    source_team_name: str | None = None


class EventTeamMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    team_id: uuid.UUID
    team_name: str | None = None
    user_id: uuid.UUID
    status: TeamMemberStatus
    role: TeamRole
    message: str | None = None
    created_at: dt.datetime
    decided_at: dt.datetime | None = None
    decided_by_name: str | None = None
    user_name: str | None = None
    user_email: str | None = None
    user_avatar_etag: str | None = None
    #: What was checked for this member, one entry per requirement.
    checks: list[TeamCheckRead] = []
    #: Approved, but a requirement's check is missing or has expired. Access
    #: stays; the managers are only told to look again.
    needs_recheck: bool = False
    #: Files attached to a pending request.
    documents: list[TeamDocumentRead] = []
    #: For a pending request: valid checks of the same requirement (by label)
    #: in another team of the same event, which the decider can rely on.
    reusable_checks: list[TeamCheckRead] = []
    #: For a pending request: the requester's other teams in this event.
    other_team_names: list[str] = []
    #: For a pending request: confirmed bookings in this event.
    booked_shift_count: int = 0
