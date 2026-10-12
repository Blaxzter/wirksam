import uuid

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import Base


class Location(Base, table=True):
    """A named place inside one event: a stand, a room, the main entrance.

    Tasks, shift batches and shifts point at it through ``location_id`` and
    also keep the name in their own ``location`` text column. That copy is the
    display value every read path uses; renaming a location rewrites it, and
    deleting one (``ON DELETE SET NULL``) leaves it behind as free text.

    There is no relationship on ``Event``: the ``CASCADE`` on ``event_id``
    removes an event's locations in the database.
    """

    __tablename__ = "locations"  # type: ignore[assignment]

    __table_args__ = (
        sa.UniqueConstraint("event_id", "name", name="uq_locations_event_name"),
    )

    event_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    name: str = Field(
        sa_column=sa.Column(sa.String(120), nullable=False),
        description="Display name, unique per event",
    )
    description: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
        description="Markdown shown to helpers",
    )
    address: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(255), nullable=True),
    )
    map_url: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(2048), nullable=True),
        description="External map link; http(s) only, enforced by the schema",
    )
    contact: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(255), nullable=True),
        description="Free text, e.g. a name and a phone number",
    )
