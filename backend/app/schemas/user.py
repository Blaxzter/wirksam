import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    auth0_sub: str = Field(..., description="Auth0 subject identifier")
    email: EmailStr | None = Field(default=None, description="User's email address")
    name: str | None = Field(default=None, description="User's display name")
    picture: str | None = Field(default=None, description="URL to user's profile picture")
    roles: list[str] = Field(
        default_factory=list, description="List of role identifiers"
    )
    is_active: bool = Field(default=True, description="Whether the user is active")


class UserUpdate(BaseModel):
    email: EmailStr | None = Field(default=None, description="User's email address")
    name: str | None = Field(default=None, description="User's display name")
    roles: list[str] | None = Field(
        default=None, description="List of role identifiers"
    )
    is_active: bool | None = Field(
        default=None, description="Whether the user is active"
    )


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    auth0_sub: str
    email: EmailStr | None = None
    name: str | None = None
    picture: str | None = None
    roles: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
