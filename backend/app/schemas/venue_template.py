"""Schemas for venue plan templates: reusable drawings saved on the user."""

import datetime as dt
import uuid
from typing import Final, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    computed_field,
    field_validator,
    model_validator,
)

from app.logic.venue_shapes import MAX_POINTS_PER_SHAPE, validate_geometry
from app.schemas.venue_map import (
    Coordinate,
    LabelSize,
    PlanName,
    PropRotation,
    PropType,
    ShapeKind,
    ShapeLabel,
    ShapePoint,
    ShapeStyle,
)

#: How many templates one account may keep. Each can hold a picture of up to
#: 2 MB, so this bounds what one account can store; 409
#: ``venue_template.limit_reached`` beyond it.
MAX_TEMPLATES_PER_USER: Final = 20

TEMPLATE_NOT_FOUND: Final = "venue_template.not_found"
TEMPLATE_LIMIT_REACHED: Final = "venue_template.limit_reached"


class VenueTemplateShape(BaseModel):
    """One shape of a template's drawing.

    A ``VenueShape`` without its plan and without a location link: a template
    belongs to no event, so it cannot point at one of its places. The geometry
    is checked by the same ``validate_geometry`` as a plan's shapes, both when
    the snapshot is stored and when it is read back.
    """

    id: uuid.UUID = Field(description="Stable within the template; a list key")
    kind: ShapeKind
    style: ShapeStyle
    points: list[ShapePoint] = Field(min_length=1, max_length=MAX_POINTS_PER_SHAPE)
    label: ShapeLabel | None = None
    label_size: LabelSize = "md"
    label_x: Coordinate | None = None
    label_y: Coordinate | None = None
    stroke_width: float | None = None
    prop: PropType | None = None
    rotation: PropRotation | None = None
    scale: float | None = None
    sort_order: int = Field(default=0, description="z order, ascending")

    @field_validator("label")
    @classmethod
    def _blank_label(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _geometry(self) -> "VenueTemplateShape":
        geometry = validate_geometry(
            kind=self.kind,
            style=self.style,
            points=self.points,
            label=self.label,
            stroke_width=self.stroke_width,
            location_id=None,
            label_x=self.label_x,
            label_y=self.label_y,
            prop=self.prop,
            rotation=self.rotation,
            scale=self.scale,
        )
        self.points = geometry.points
        self.stroke_width = geometry.stroke_width
        self.style = cast(ShapeStyle, geometry.style)
        self.prop = cast(PropType | None, geometry.prop)
        self.rotation = geometry.rotation
        self.scale = geometry.scale
        return self


template_shapes_adapter: Final = TypeAdapter(list[VenueTemplateShape])


class VenueTemplateCreate(BaseModel):
    name: PlanName


class VenueTemplateUpdate(BaseModel):
    name: PlanName | None = None


class VenueTemplateSummary(BaseModel):
    """A template as the picker lists it: no shapes, just enough to show it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    canvas_width: int
    canvas_height: int
    image_etag: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    shape_count: int = Field(default=0, description="How many shapes it draws")
    created_at: dt.datetime
    updated_at: dt.datetime

    @computed_field(description="Effective width: the image's, else the canvas's")  # type: ignore[prop-decorator]
    @property
    def width(self) -> int:
        return self.image_width or self.canvas_width

    @computed_field(description="Effective height: the image's, else the canvas's")  # type: ignore[prop-decorator]
    @property
    def height(self) -> int:
        return self.image_height or self.canvas_height


class VenueTemplateRead(VenueTemplateSummary):
    """A template with its drawing, for the preview and the thumbnail."""

    shapes: list[VenueTemplateShape] = Field(
        default_factory=list, description="In drawing order (``sort_order``)"
    )
