import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas.event_membership import AssignableEventRole


class EventInvitationCreate(BaseModel):
    """Create either a targeted invite (``email`` set) or a share link."""

    email: EmailStr | None = None
    role: AssignableEventRole = "member"
    expires_in_days: int | None = Field(
        default=14, ge=1, le=365, description="Null means the invite never expires"
    )


class EventInvitationBulkCreate(BaseModel):
    """Invite several addresses in one go, all with the same role."""

    emails: list[EmailStr] = Field(min_length=1, max_length=100)
    role: AssignableEventRole = "member"
    expires_in_days: int | None = Field(default=14, ge=1, le=365)

    @model_validator(mode="after")
    def dedupe_emails(self) -> "EventInvitationBulkCreate":
        seen: set[str] = set()
        unique: list[EmailStr] = []
        for address in self.emails:
            key = str(address).lower()
            if key not in seen:
                seen.add(key)
                unique.append(address)
        self.emails = unique
        return self


class InvitationTaskBrief(BaseModel):
    """A task an invitation asks its invitee to be in charge of."""

    task_id: uuid.UUID
    name: str
    start_date: dt.date
    end_date: dt.date


class EventInvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    email: str | None = None
    role: AssignableEventRole
    token: str
    invited_by_id: uuid.UUID | None = None
    expires_at: dt.datetime | None = None
    revoked_at: dt.datetime | None = None
    accepted_at: dt.datetime | None = None
    use_count: int = 0
    #: The tasks this invitation asks the person to be in charge of.
    tasks: list[InvitationTaskBrief] = Field(default_factory=list)
    #: Created by inviting someone to be in charge; revoked when its last task
    #: link goes.
    for_tasks_only: bool = False
    last_sent_at: dt.datetime | None = None


class EventInvitationPreview(BaseModel):
    """What an invitee sees before deciding to accept.

    Deliberately narrow: it is reachable by anyone holding the token, so it
    exposes the event's identity and nothing about its members or contents.
    """

    event_id: uuid.UUID
    event_name: str
    event_description: str | None = None
    start_date: dt.date
    end_date: dt.date
    role: AssignableEventRole
    invited_by_name: str | None = None
    is_valid: bool
    invalid_reason: str | None = Field(
        default=None,
        description="One of: expired, revoked, already_used, email_mismatch",
    )
    already_member: bool = False
    #: The tasks the invitee is asked to be in charge of. Only for the
    #: addressee: empty on ``email_mismatch``.
    tasks: list[InvitationTaskBrief] = Field(default_factory=list)


class EventInvitationBulkResult(BaseModel):
    created: list[EventInvitationRead]
    skipped_existing_members: list[str] = Field(default_factory=list)
    skipped_already_invited: list[str] = Field(default_factory=list)
    #: Not sent because of the daily limits (per organiser, per address).
    skipped_rate_limited: list[str] = Field(default_factory=list)
