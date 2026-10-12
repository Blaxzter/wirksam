import uuid

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import Base


class VenuePlan(Base, table=True):
    """One floor plan or site map of an event, with markers placed on it.

    The image bytes live in ``venue_plan_images`` so listing plans never loads
    a ``bytea``. ``image_etag``, ``image_width`` and ``image_height`` are
    denormalised copies the client needs to size the map and bust its cache;
    all three are NULL until an image is uploaded.
    """

    __tablename__ = "venue_plans"  # type: ignore[assignment]

    event_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    name: str = Field(sa_column=sa.Column(sa.String(120), nullable=False))
    sort_order: int = Field(
        default=0,
        sa_column=sa.Column(sa.Integer, nullable=False, server_default="0"),
    )
    image_etag: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(64), nullable=True),
        description="sha256 of the stored image; NULL while the plan has none",
    )
    image_width: int | None = Field(
        default=None, sa_column=sa.Column(sa.Integer, nullable=True)
    )
    image_height: int | None = Field(
        default=None, sa_column=sa.Column(sa.Integer, nullable=True)
    )


class VenuePlanImage(Base, table=True):
    """Image bytes of a venue plan (WebP). The same shape as ``UserAvatar``."""

    __tablename__ = "venue_plan_images"  # type: ignore[assignment]

    plan_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("venue_plans.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
    )
    data: bytes = Field(
        sa_column=sa.Column(sa.LargeBinary, nullable=False),
        description="Image bytes (WebP)",
    )
    content_type: str = Field(
        default="image/webp",
        sa_column=sa.Column(sa.String(64), nullable=False, server_default="image/webp"),
    )
    etag: str = Field(
        sa_column=sa.Column(sa.String(64), nullable=False, index=True),
        description="sha256 hex digest of data; used for HTTP ETag and cache busting",
    )


class VenueMarker(Base, table=True):
    """A pin on a venue plan, at normalised coordinates (0..1 of the image).

    ``kind == "location"`` markers point at a ``Location`` and may appear only
    once per plan; generic markers (entrance, first aid, ...) carry a NULL
    ``location_id``, and NULLs never collide in the unique constraint. The
    0..1 range and the kind/location pairing are enforced by the schema.
    """

    __tablename__ = "venue_markers"  # type: ignore[assignment]

    __table_args__ = (
        sa.UniqueConstraint(
            "plan_id", "location_id", name="uq_venue_markers_plan_location"
        ),
    )

    plan_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("venue_plans.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    location_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("locations.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )
    kind: str = Field(
        sa_column=sa.Column(sa.String(32), nullable=False),
        description="location, entrance, info_desk, first_aid, toilets, parking, kitchen",
    )
    label: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(120), nullable=True),
        description="Optional caption, mainly for generic markers",
    )
    x: float = Field(sa_column=sa.Column(sa.Float, nullable=False))
    y: float = Field(sa_column=sa.Column(sa.Float, nullable=False))
