import datetime as dt
import uuid
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.schemas.user import ApprovalStatus

TimeFormat = Literal["locale", "h12", "h24"]
Theme = Literal["default", "classic"]


class UserProfileUpdate(BaseModel):
    name: str | None = Field(None, max_length=100, description="User's display name")
    nickname: str | None = Field(None, max_length=50, description="User's nickname")
    bio: str | None = Field(None, max_length=500, description="User's biography")
    phone_number: str | None = Field(
        None, max_length=30, description="User's phone number"
    )
    preferred_language: str | None = Field(
        None, pattern="^(en|de)$", description="Preferred language for notifications"
    )
    time_format: TimeFormat | None = Field(
        None, description="Display preference for times"
    )
    theme: Theme | None = Field(None, description="Selected color palette")
    show_event_switcher_in_nav: bool | None = Field(
        None, description="Show a quick event switcher in the sidebar nav"
    )


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    sub: str = Field(validation_alias=AliasChoices("sub", "subject"))
    name: str | None = None
    nickname: str | None = None
    email: str | None = None
    avatar_etag: str | None = None
    bio: str | None = None
    phone_number: str | None = None
    preferred_language: str = "en"
    time_format: TimeFormat = "locale"
    theme: Theme = "default"
    show_event_switcher_in_nav: bool = False
    email_verified: bool = False
    roles: list[str] = Field(default_factory=list, description="User's roles")
    is_admin: bool = Field(
        default=False, description="Whether user is a platform superadmin"
    )
    is_active: bool = Field(default=True, description="Whether user is active")
    approval_status: ApprovalStatus = Field(
        default="approved",
        description="Registration approval: approved, pending or rejected",
    )
    rejection_reason: str | None = Field(
        default=None,
        description="Reason the account was suspended or its registration rejected",
    )
    event_roles: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "This user's role in each event they belong to, keyed by event id: "
            "owner, admin or member"
        ),
    )
    selected_event_id: uuid.UUID | None = Field(
        default=None,
        description="Event currently selected as the user's dashboard scope",
    )
    is_sandbox: bool = Field(
        default=False,
        description=(
            "This is a throwaway guest account from the 'try a test event' "
            "button, not a real registration"
        ),
    )
    sandbox_expires_at: dt.datetime | None = Field(
        default=None,
        description=(
            "When this guest's demo is purged, in naive UTC. Resolved from the "
            "sandbox event rather than stored on the user, so the countdown "
            "survives a page reload without a second request."
        ),
    )


class SelectedEventUpdate(BaseModel):
    """Request body for PUT /users/me/selected-event."""

    selected_event_id: uuid.UUID | None = None
