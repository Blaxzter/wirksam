from pydantic import BaseModel, Field


class SiteSettingsRead(BaseModel):
    has_approval_password: bool = Field(
        default=False,
        description="Whether an approval password is currently configured",
    )


class SiteSettingsUpdate(BaseModel):
    approval_password: str | None = Field(
        default=None,
        description="Set or clear the approval password (null to clear)",
    )


class SelfApproveRequest(BaseModel):
    password: str = Field(
        ...,
        description="The approval password to verify",
    )
