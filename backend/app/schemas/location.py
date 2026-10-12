"""Schemas for per-event locations (#182)."""

import datetime as dt
import uuid
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

# Stripped before the length check, so "   " is rejected as empty rather than
# stored as a name nobody can pick from a list.
LocationName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]


def _require_http_url(value: str) -> str:
    """Only ``http(s)`` links: the value is rendered as a clickable link, and a
    ``javascript:`` or ``data:`` URL there would run in the viewer's session."""
    scheme, sep, rest = value.partition("://")
    if not sep or scheme.lower() not in ("http", "https"):
        raise ValueError("Map link must start with http:// or https://")
    if not rest.strip():
        raise ValueError("Map link must include an address")
    return value


HttpUrlStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=2048),
    AfterValidator(_require_http_url),
]

_OPTIONAL_TEXT_FIELDS = ("description", "address", "map_url", "contact")


def _blank_to_none(value: Any) -> Any:
    """Treat an empty or whitespace-only optional field as "not set"."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


class LocationBase(BaseModel):
    name: LocationName
    description: str | None = Field(
        default=None, max_length=10_000, description="Markdown"
    )
    address: str | None = Field(default=None, max_length=255)
    map_url: HttpUrlStr | None = Field(
        default=None, description="External map link (http or https only)"
    )
    contact: str | None = Field(
        default=None, max_length=255, description="Free text, e.g. name and phone"
    )

    @field_validator(*_OPTIONAL_TEXT_FIELDS, mode="before")
    @classmethod
    def _blank_optional_to_none(cls, value: Any) -> Any:
        return _blank_to_none(value)


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    """Partial update; apply with ``model_dump(exclude_unset=True)``."""

    name: LocationName | None = None
    description: str | None = Field(default=None, max_length=10_000)
    address: str | None = Field(default=None, max_length=255)
    map_url: HttpUrlStr | None = None
    contact: str | None = Field(default=None, max_length=255)

    @field_validator(*_OPTIONAL_TEXT_FIELDS, mode="before")
    @classmethod
    def _blank_optional_to_none(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("name")
    @classmethod
    def _name_not_null(cls, value: str | None) -> str:
        # Only runs when the client sent the field: leaving ``name`` out is
        # fine, sending ``"name": null`` is not.
        if value is None:
            raise ValueError("Name cannot be empty")
        return value


class LocationRead(LocationBase):
    model_config = ConfigDict(from_attributes=True)

    # Reads never re-validate the stored URL; the write path already did.
    map_url: str | None = None
    id: uuid.UUID
    event_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class LocationPin(BaseModel):
    """Where a location sits on one venue plan."""

    plan_id: uuid.UUID
    plan_name: str
    marker_id: uuid.UUID
    image_etag: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    x: float
    y: float


class LocationDetailRead(LocationRead):
    pins: list[LocationPin] = Field(
        default_factory=list,
        description="Placements on the event's venue plans; empty for non-members",
    )


class LocationShiftRead(BaseModel):
    """A shift at a location on one day, as listed in the map's location sheet."""

    id: uuid.UUID
    task_id: uuid.UUID
    task_name: str
    title: str
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    max_bookings: int
    current_bookings: int = 0
    is_booked_by_me: bool = False
    my_booking_id: uuid.UUID | None = None
