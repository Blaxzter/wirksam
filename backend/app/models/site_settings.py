import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import Base


class SiteSettings(Base, table=True):
    """Singleton table for application-wide settings."""

    __tablename__ = "site_settings"  # type: ignore[assignment]

    approval_password: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String, nullable=True),
        description="Optional password that pending users can enter to self-approve",
    )
