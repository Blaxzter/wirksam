"""Schemas for venue plans, their markers and the member map view (#185)."""

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

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


class VenuePlanCreate(BaseModel):
    name: PlanName


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
    created_at: dt.datetime
    updated_at: dt.datetime
    markers: list[VenueMarkerRead] = Field(default_factory=list)


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
