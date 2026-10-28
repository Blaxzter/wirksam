import uuid

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import Base


class UserAvatar(Base, table=True):
    """A user's avatar (WebP, max 256x256); the bytes live in ``app.core.storage``."""

    __tablename__ = "user_avatars"  # type: ignore[assignment]

    user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        description="Owner user ID",
    )
    storage_key: str = Field(
        sa_column=sa.Column(sa.String(255), nullable=False, unique=True, index=True),
        description="Key of the image bytes in app.core.storage (WebP)",
    )
    content_type: str = Field(
        default="image/webp",
        sa_column=sa.Column(sa.String(64), nullable=False, server_default="image/webp"),
        description="MIME type of stored bytes",
    )
    etag: str = Field(
        sa_column=sa.Column(sa.String(64), nullable=False, index=True),
        description="sha256 hex digest of the bytes; used for HTTP ETag and cache busting",
    )
