import uuid
from typing import Final, Literal

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import Base

#: ``light`` is the logo; ``dark`` an optional second one for dark mode, such
#: as the same mark with white lettering.
LogoVariant = Literal["light", "dark"]
LOGO_VARIANTS: Final[tuple[LogoVariant, ...]] = ("light", "dark")


class EventLogo(Base, table=True):
    """An event's logo (WebP, fits 512x512); the bytes live in ``app.core.storage``.

    The same shape as ``UserAvatar``, one row per variant. ``events.logo_etag``
    and ``events.logo_dark_etag`` mirror ``etag`` so a list of events can build
    the logo URLs without a join.
    """

    __tablename__ = "event_logos"  # type: ignore[assignment]
    __table_args__ = (
        sa.UniqueConstraint("event_id", "variant", name="uq_event_logos_event_variant"),
        sa.CheckConstraint(
            "variant IN ('light', 'dark')", name="ck_event_logos_variant"
        ),
    )

    event_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    variant: str = Field(
        default="light",
        sa_column=sa.Column(sa.String(8), nullable=False, server_default="light"),
        description="One of LOGO_VARIANTS",
    )
    storage_key: str = Field(
        sa_column=sa.Column(sa.String(255), nullable=False, unique=True, index=True),
        description="Key of the image bytes in app.core.storage (WebP)",
    )
    content_type: str = Field(
        default="image/webp",
        sa_column=sa.Column(sa.String(64), nullable=False, server_default="image/webp"),
    )
    etag: str = Field(
        sa_column=sa.Column(sa.String(64), nullable=False, index=True),
        description="sha256 hex digest of the bytes; used for HTTP ETag and cache busting",
    )
