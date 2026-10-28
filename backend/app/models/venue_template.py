import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import Base


class VenueTemplate(Base, table=True):
    """A saved venue drawing an organiser can start new plans from.

    Owned by a *user*, not an event, so the same drawing can be reused across
    events. A template is only the drawing: the canvas size, an optional
    picture (bytes in ``venue_template_images``) and the shapes. It has no
    markers and no links to locations, because those belong to one event.

    Both directions copy, never link: a plan made from a template and the
    template it was saved from change independently afterwards.

    ``shapes`` is a JSONB snapshot rather than a child table: a template is
    immutable apart from its name, so it is always written and read whole.
    Every element is validated by ``app.schemas.venue_template.VenueTemplateShape``
    on the way in and on the way out, with the same geometry rules as
    ``venue_shapes``.
    """

    __tablename__ = "venue_templates"  # type: ignore[assignment]

    user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        description="Owner; only they can see or use the template",
    )
    name: str = Field(sa_column=sa.Column(sa.String(120), nullable=False))
    canvas_width: int = Field(sa_column=sa.Column(sa.Integer, nullable=False))
    canvas_height: int = Field(sa_column=sa.Column(sa.Integer, nullable=False))
    image_etag: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(64), nullable=True),
        description="sha256 of the stored image; NULL while the template has none",
    )
    image_width: int | None = Field(
        default=None, sa_column=sa.Column(sa.Integer, nullable=True)
    )
    image_height: int | None = Field(
        default=None, sa_column=sa.Column(sa.Integer, nullable=True)
    )
    shapes: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=sa.Column(JSONB, nullable=False, server_default="[]"),
        description="The drawing, in drawing order (see VenueTemplateShape)",
    )


class VenueTemplateImage(Base, table=True):
    """The picture of a venue template (WebP). The same shape as ``VenuePlanImage``."""

    __tablename__ = "venue_template_images"  # type: ignore[assignment]

    template_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("venue_templates.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
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
