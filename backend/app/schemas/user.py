import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Where an account stands in the queue ``REGISTRATION_MODE=approval`` puts in
# front of signup. Every account outside that mode is "approved".
ApprovalStatus = Literal["approved", "pending", "rejected"]


class UserCreate(BaseModel):
    subject: str = Field(..., description="Opaque local identity string")
    email: EmailStr | None = Field(default=None, description="User's email address")
    name: str | None = Field(default=None, description="User's display name")
    email_verified: bool = Field(
        default=False, description="Whether the user's email is verified"
    )
    roles: list[str] = Field(
        default_factory=list, description="List of role identifiers"
    )
    is_active: bool = Field(default=True, description="Whether the user is active")
    approval_status: ApprovalStatus = Field(
        default="approved", description="Registration approval status"
    )
    preferred_language: str = Field(default="en", description="Preferred language")
    time_format: str = Field(
        default="locale", description="Display preference for times"
    )
    theme: str = Field(default="default", description="Selected color palette")


class UserUpdate(BaseModel):
    email: EmailStr | None = Field(default=None, description="User's email address")
    name: str | None = Field(default=None, description="User's display name")
    roles: list[str] | None = Field(
        default=None, description="List of role identifiers"
    )
    is_active: bool | None = Field(
        default=None, description="Whether the user is active"
    )
    rejection_reason: str | None = Field(
        default=None, description="Reason for account rejection"
    )
    preferred_language: str | None = Field(
        default=None, description="Preferred language"
    )
    time_format: str | None = Field(
        default=None, description="Display preference for times"
    )
    theme: str | None = Field(default=None, description="Selected color palette")


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject: str
    email: EmailStr | None = None
    name: str | None = None
    avatar_etag: str | None = None
    phone_number: str | None = None
    preferred_language: str = "en"
    time_format: str = "locale"
    theme: str = "default"
    roles: list[str]
    is_active: bool
    approval_status: ApprovalStatus = "approved"
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class UserCounts(BaseModel):
    all: int
    active: int
    pending: int
    rejected: int
    suspended: int


class RejectRegistrationRequest(BaseModel):
    reason: str | None = Field(
        default=None,
        max_length=1000,
        description="Shown to the person whose registration was rejected",
    )


class UserOwnedContent(BaseModel):
    """Counts of content created (owned) by a user."""

    events: int = Field(..., description="Number of events created by the user")
    tasks: int = Field(..., description="Number of tasks created by the user")
    total: int = Field(..., description="Total number of owned items")


class OwnershipTransferRequest(BaseModel):
    """Request body for transferring a user's owned content to another user."""

    target_user_id: uuid.UUID = Field(
        ..., description="User who takes over ownership of all events and tasks"
    )


class OwnershipTransferResult(BaseModel):
    """Summary of a completed ownership transfer."""

    events_transferred: int = Field(
        ..., description="Number of events reassigned to the target user"
    )
    tasks_transferred: int = Field(
        ..., description="Number of tasks reassigned to the target user"
    )


class UserListResponse(BaseModel):
    items: list[UserRead]
    skip: int
    limit: int
    counts: UserCounts
