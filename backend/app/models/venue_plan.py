import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import Base


class VenuePlan(Base, table=True):
    """One floor plan or site map of an event: a picture, a drawing, or both.

    The image lives in ``venue_plan_images`` (its bytes in ``app.core.storage``)
    so a plan without one needs no row there. ``image_etag``, ``image_width`` and ``image_height`` are
    denormalised copies the client needs to size the map and bust its cache;
    all three are NULL until an image is uploaded.

    A plan without a picture is a blank canvas of ``canvas_width`` x
    ``canvas_height`` logical units, drawn on with ``VenueShape`` rows. The
    effective size is the image's when there is one, else the canvas's; both
    markers and shapes use coordinates normalised to it.
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
    canvas_width: int = Field(
        default=1600,
        sa_column=sa.Column(sa.Integer, nullable=False, server_default="1600"),
        description="Logical width of the blank canvas; used while there is no image",
    )
    canvas_height: int = Field(
        default=1000,
        sa_column=sa.Column(sa.Integer, nullable=False, server_default="1000"),
        description="Logical height of the blank canvas; used while there is no image",
    )
    shapes_revision: int = Field(
        default=0,
        sa_column=sa.Column(sa.Integer, nullable=False, server_default="0"),
        description=(
            "Bumped by every successful shape batch; cache key and "
            "optimistic-concurrency token"
        ),
    )


class VenuePlanImage(Base, table=True):
    """The picture of a venue plan (WebP). The same shape as ``UserAvatar``."""

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


class VenueShape(Base, table=True):
    """A drawn room, area, line or caption on a venue plan.

    ``points`` are ``[x, y]`` pairs normalised to the plan's effective size,
    like marker coordinates: a rect is its two corners (min, max), a polygon
    3..500 vertices (implicitly closed), a path 2..500 vertices (open, with a
    ``stroke_width`` as a fraction of the plan's shorter side), a label one
    point, a prop one point with a prop type, rotation and scale (decoration,
    never a place). ``style`` is a preset token the client maps to theme colours, never
    a free colour. All of that is enforced by the schema, as for markers.
    """

    __tablename__ = "venue_shapes"  # type: ignore[assignment]

    plan_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("venue_plans.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    # SET NULL next to a CASCADE that the same event delete also reaches is
    # the shape app/models/CLAUDE.md warns about: a user or event delete
    # cascades to the locations (SET NULL here) and to the plans (CASCADE
    # here) in one statement, and Postgres would re-check location_id against
    # a location already removed. Deferring the *check* (the action itself
    # still runs at once) lets both cascades finish first, as on
    # Task.location_id. Pinned by
    # tests/crud/test_venue_map.py::TestEventDeleteWithLocations and
    # tests/api/routes/test_event_members.py::TestUserDeletionCascades.
    location_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey(
                "locations.id",
                ondelete="SET NULL",
                deferrable=True,
                initially="DEFERRED",
            ),
            nullable=True,
            index=True,
        ),
        description="Tapping the area opens this location (rect and polygon only)",
    )
    kind: str = Field(
        sa_column=sa.Column(sa.String(16), nullable=False),
        description="rect, polygon, path, label, prop",
    )
    style: str = Field(
        sa_column=sa.Column(sa.String(16), nullable=False),
        description="Preset token: building, room, area, stage, furniture, ...",
    )
    points: list[list[float]] = Field(
        sa_column=sa.Column(JSONB, nullable=False),
        description="[[x, y], ...] normalised to the plan size",
    )
    label: str | None = Field(
        default=None, sa_column=sa.Column(sa.String(120), nullable=True)
    )
    label_size: str = Field(
        default="md",
        sa_column=sa.Column(sa.String(8), nullable=False, server_default="md"),
    )
    label_x: float | None = Field(
        default=None, sa_column=sa.Column(sa.Float, nullable=True)
    )
    label_y: float | None = Field(
        default=None, sa_column=sa.Column(sa.Float, nullable=True)
    )
    stroke_width: float | None = Field(
        default=None,
        sa_column=sa.Column(sa.Float, nullable=True),
        description="Paths only: line width as a fraction of the plan's shorter side",
    )
    prop: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(16), nullable=True),
        description="Props only: tree, conifer, bush, ...",
    )
    rotation: float | None = Field(
        default=None,
        sa_column=sa.Column(sa.Float, nullable=True),
        description="Props only: degrees clockwise, 0 <= r < 360",
    )
    scale: float | None = Field(
        default=None,
        sa_column=sa.Column(sa.Float, nullable=True),
        description="Props only: size factor, 0.25..4",
    )
    sort_order: int = Field(
        default=0,
        sa_column=sa.Column(sa.Integer, nullable=False, server_default="0"),
        description="z order, ascending: later shapes are drawn on top",
    )
