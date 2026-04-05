from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, HttpUrl


class ProfileInit(BaseModel):
    """Profile data from Auth0 ID token for user initialization."""

    email: EmailStr | None = None
    name: str | None = None
    nickname: str | None = None
    picture: str | None = None
    email_verified: bool | None = None
    preferred_language: str | None = None


class UserProfileUpdate(BaseModel):
    name: str | None = Field(None, max_length=100, description="User's display name")
    nickname: str | None = Field(None, max_length=50, description="User's nickname")
    picture: HttpUrl | None = Field(None, description="URL to user's profile picture")
    bio: str | None = Field(None, max_length=500, description="User's biography")
    phone_number: str | None = Field(
        None, max_length=30, description="User's phone number"
    )
    preferred_language: str | None = Field(
        None, pattern="^(en|de)$", description="Preferred language for notifications"
    )


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    sub: str = Field(validation_alias=AliasChoices("sub", "auth0_sub"))
    name: str | None = None
    nickname: str | None = None
    email: str | None = None
    picture: str | None = None
    bio: str | None = None
    phone_number: str | None = None
    preferred_language: str = "en"
    email_verified: bool = False
    roles: list[str] = Field(default_factory=list, description="User's roles")
    is_admin: bool = Field(default=False, description="Whether user has admin role")
    is_active: bool = Field(default=True, description="Whether user is active")
    rejection_reason: str | None = Field(
        default=None, description="Reason for account rejection"
    )
