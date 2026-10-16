"""Schemas for venue plans, their markers, drawn shapes and the map view (#185)."""

import datetime as dt
import uuid
from typing import Annotated, Final, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.logic.venue_shapes import (
    MAX_LABEL_LENGTH,
    MAX_OPS_PER_BATCH,
    MAX_POINTS_PER_SHAPE,
    validate_geometry,
)
from app.schemas.location import LocationRead

MarkerKind = Literal[
    "location",
    "entrance",
    "info_desk",
    "first_aid",
    "toilets",
    "parking",
    "kitchen",
]

# z order. Bounded well inside the 32-bit column, so "put it on top" (max + 1)
# can never overflow it either.
SortOrder = Annotated[int, Field(ge=-1_000_000, le=1_000_000)]

PlanName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]

# Normalised image coordinate: 0 is the left/top edge, 1 the right/bottom one.
Coordinate = Annotated[float, Field(ge=0, le=1)]

MARKER_LOCATION_REQUIRED = "venue_marker.location_required"


def marker_kind_mismatch(kind: str, location_id: uuid.UUID | None) -> bool:
    """True when ``kind`` and ``location_id`` disagree.

    A ``location`` marker must name a location and every other kind must not.
    Shared by the create schema and the PATCH route, which checks the merged
    result (raising 422 ``venue_marker.location_required``).
    """
    return (kind == "location") != (location_id is not None)


class VenueMarkerCreate(BaseModel):
    kind: MarkerKind
    location_id: uuid.UUID | None = None
    label: str | None = Field(default=None, max_length=120)
    x: Coordinate
    y: Coordinate

    @model_validator(mode="after")
    def _kind_matches_location(self) -> "VenueMarkerCreate":
        if marker_kind_mismatch(self.kind, self.location_id):
            raise PydanticCustomError(
                MARKER_LOCATION_REQUIRED,
                "A location marker needs a location_id, and only a location marker may have one",
            )
        return self


class VenueMarkerUpdate(BaseModel):
    """Partial update. The kind/location pairing is checked on the merged row."""

    kind: MarkerKind | None = None
    location_id: uuid.UUID | None = None
    label: str | None = Field(default=None, max_length=120)
    x: Coordinate | None = None
    y: Coordinate | None = None


class VenueMarkerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    kind: MarkerKind
    location_id: uuid.UUID | None = None
    label: str | None = None
    x: float
    y: float


# ── Shapes ─────────────────────────────────────────────────────────────────

ShapeKind = Literal["rect", "polygon", "path", "label", "prop"]
ShapeStyle = Literal[
    "building",
    "room",
    "area",
    "stage",
    "furniture",
    "green",
    "water",
    "parking",
    "path",
    "wall",
    "hedge",
    "fence",
    "sand",
]
# Decoration glyphs, in the order of ``app.logic.venue_shapes.PROP_TYPES``
# (a test keeps the two in step).
PropType = Literal[
    "tree",
    "conifer",
    "bush",
    "flowers",
    "plant",
    "bench",
    "picnic_table",
    "round_table",
    "bin",
    "bike_rack",
    "sign",
    "parasol",
    "tent",
    "lamp",
]
PropRotation = Annotated[
    float,
    Field(ge=-720, le=720, description="Props only: degrees clockwise"),
]
LabelSize = Literal["sm", "md", "lg"]
CanvasPreset = Literal["landscape", "portrait", "square"]
CANVAS_PRESETS: Final[dict[str, tuple[int, int]]] = {
    "landscape": (1600, 1000),
    "portrait": (1000, 1600),
    "square": (1200, 1200),
}

ShapePoint = Annotated[list[Coordinate], Field(min_length=2, max_length=2)]
ShapeLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=MAX_LABEL_LENGTH)
]


def _empty_to_none(value: str | None) -> str | None:
    return value or None


class VenueShapeCreate(BaseModel):
    """A new shape. The whole geometry is checked by ``validate_geometry``."""

    id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Optional client-chosen id, so undoing a delete can re-create the "
            "shape under the same id"
        ),
    )
    kind: ShapeKind
    style: ShapeStyle
    points: list[ShapePoint] = Field(min_length=1, max_length=MAX_POINTS_PER_SHAPE)
    label: ShapeLabel | None = None
    label_size: LabelSize = "md"
    label_x: Coordinate | None = None
    label_y: Coordinate | None = None
    stroke_width: float | None = Field(
        default=None,
        description="Paths only: width as a fraction of the plan's shorter side",
    )
    location_id: uuid.UUID | None = Field(
        default=None, description="Rect and polygon only"
    )
    sort_order: SortOrder | None = Field(
        default=None, description="z order; left out, the shape goes on top"
    )
    prop: PropType | None = Field(
        default=None, description="Props only (required there): the glyph"
    )
    rotation: PropRotation | None = None
    scale: float | None = Field(
        default=None, description="Props only: size factor, 0.25..4 (default 1)"
    )

    @field_validator("label")
    @classmethod
    def _blank_label(cls, value: str | None) -> str | None:
        return _empty_to_none(value)

    @model_validator(mode="after")
    def _geometry(self) -> "VenueShapeCreate":
        geometry = validate_geometry(
            kind=self.kind,
            style=self.style,
            points=self.points,
            label=self.label,
            stroke_width=self.stroke_width,
            location_id=self.location_id,
            label_x=self.label_x,
            label_y=self.label_y,
            prop=self.prop,
            rotation=self.rotation,
            scale=self.scale,
        )
        self.points = geometry.points
        self.stroke_width = geometry.stroke_width
        # A prop's style is its family's (always a ShapeStyle); the prop
        # itself comes back as sent, so both casts only narrow the type.
        self.style = cast(ShapeStyle, geometry.style)
        self.prop = cast(PropType | None, geometry.prop)
        self.rotation = geometry.rotation
        self.scale = geometry.scale
        return self


class VenueShapeUpdate(BaseModel):
    """Partial update; the merged shape is re-validated as a whole.

    ``kind`` cannot change (delete and re-create instead). An explicit ``null``
    for ``style``, ``points``, ``label_size``, ``sort_order``, ``prop``,
    ``rotation`` or ``scale`` is ignored, as those cannot be cleared. A style
    patch on a prop is overridden by the prop's own style.
    """

    style: ShapeStyle | None = None
    points: list[ShapePoint] | None = Field(
        default=None, min_length=1, max_length=MAX_POINTS_PER_SHAPE
    )
    label: ShapeLabel | None = None
    label_size: LabelSize | None = None
    label_x: Coordinate | None = None
    label_y: Coordinate | None = None
    stroke_width: float | None = None
    location_id: uuid.UUID | None = None
    sort_order: SortOrder | None = None
    prop: PropType | None = None
    rotation: PropRotation | None = None
    scale: float | None = None

    @field_validator("label")
    @classmethod
    def _blank_label(cls, value: str | None) -> str | None:
        return _empty_to_none(value)


class ShapeCreateOp(BaseModel):
    op: Literal["create"]
    shape: VenueShapeCreate


class ShapeUpdateOp(BaseModel):
    op: Literal["update"]
    id: uuid.UUID
    patch: VenueShapeUpdate


class ShapeDeleteOp(BaseModel):
    op: Literal["delete"]
    id: uuid.UUID


ShapeOp = Annotated[
    ShapeCreateOp | ShapeUpdateOp | ShapeDeleteOp, Field(discriminator="op")
]


class VenueShapeBatch(BaseModel):
    """Shape edits, applied in order and all or nothing."""

    ops: list[ShapeOp] = Field(min_length=1, max_length=MAX_OPS_PER_BATCH)
    expected_revision: int | None = Field(
        default=None,
        description=(
            "The plan's ``shapes_revision`` the client last saw; a mismatch is "
            "409 ``venue_shape.revision_conflict``"
        ),
    )


class VenueShapeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    kind: ShapeKind
    style: ShapeStyle
    points: list[list[float]]
    label: str | None = None
    label_size: LabelSize
    label_x: float | None = None
    label_y: float | None = None
    stroke_width: float | None = None
    location_id: uuid.UUID | None = None
    sort_order: int
    prop: PropType | None = None
    rotation: float | None = None
    scale: float | None = None


class VenuePlanShapesRead(BaseModel):
    plan_id: uuid.UUID
    revision: int = Field(description="The plan's ``shapes_revision``")
    shapes: list[VenueShapeRead] = Field(description="In drawing order")


# ── Plans ──────────────────────────────────────────────────────────────────


class VenuePlanCreate(BaseModel):
    name: PlanName
    canvas: CanvasPreset = Field(
        default="landscape",
        description="Aspect of the blank canvas; it cannot be changed later",
    )
    template_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Start from one of the caller's templates: its canvas, picture and "
            "drawing are copied in and ``canvas`` is ignored"
        ),
    )


class VenuePlanUpdate(BaseModel):
    name: PlanName | None = None


class VenuePlanOrder(BaseModel):
    plan_ids: list[uuid.UUID] = Field(
        description="Every plan of the event, exactly once, in the new order"
    )


class VenuePlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    name: str
    sort_order: int
    image_etag: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    canvas_width: int
    canvas_height: int
    shapes_revision: int
    created_at: dt.datetime
    updated_at: dt.datetime
    markers: list[VenueMarkerRead] = Field(default_factory=list)
    shapes: list[VenueShapeRead] = Field(
        default_factory=list, description="In drawing order (``sort_order``)"
    )

    @computed_field(description="Effective width: the image's, else the canvas's")  # type: ignore[prop-decorator]
    @property
    def width(self) -> int:
        return self.image_width or self.canvas_width

    @computed_field(description="Effective height: the image's, else the canvas's")  # type: ignore[prop-decorator]
    @property
    def height(self) -> int:
        return self.image_height or self.canvas_height


class VenueLocationStat(BaseModel):
    """Staffing of one location over the shifts it hosts on the map's day."""

    location_id: uuid.UUID
    shift_count: int = Field(description="Shifts at this location on the day")
    booked: int = Field(description="Active (confirmed) bookings over those shifts")
    capacity: int = Field(description="Sum of ``max_bookings`` over those shifts")
    open_shifts: int = Field(
        description="Shifts that still have a free place (booked < max_bookings)"
    )


class VenueMapRead(BaseModel):
    event_id: uuid.UUID
    on: dt.date = Field(
        description="The day ``my_location_ids`` and ``location_stats`` refer to"
    )
    plans: list[VenuePlanRead]
    locations: list[LocationRead]
    my_location_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Locations of the caller's active bookings on ``on``",
    )
    location_stats: list[VenueLocationStat] = Field(
        default_factory=list,
        description=(
            "Per-location staffing on ``on``. Only locations with at least one "
            "shift that day are listed; for non-admins, shifts of unpublished "
            "tasks are left out, matching ``GET /locations/{id}/shifts``."
        ),
    )
