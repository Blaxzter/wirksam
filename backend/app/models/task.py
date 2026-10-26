import uuid
from datetime import date, time
from typing import Any

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base

if __name__ != "__main__":
    from app.models.shift import Shift  # noqa: F401

if __name__ != "__main__":
    from app.models.event import Event  # noqa: F401

if __name__ != "__main__":
    from app.models.shift_batch import ShiftBatch  # noqa: F401


class Task(Base, table=True):
    __tablename__ = "tasks"  # type: ignore[assignment]

    name: str = Field(sa_column=sa.Column(sa.String, nullable=False, index=True))
    description: str | None = Field(
        default=None, sa_column=sa.Column(sa.Text, nullable=True)
    )
    start_date: date = Field(sa_column=sa.Column(sa.Date, nullable=False, index=True))
    end_date: date = Field(sa_column=sa.Column(sa.Date, nullable=False, index=True))
    status: str = Field(
        default="draft", sa_column=sa.Column(sa.String, nullable=False, index=True)
    )
    created_by_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )
    event_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("events.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    is_sandbox: bool = Field(
        default=False,
        sa_column=sa.Column(
            sa.Boolean, nullable=False, server_default=sa.text("false"), index=True
        ),
        description=(
            "Mirrors Event.is_sandbox, denormalised on purpose. ``event_id`` is "
            "ON DELETE SET NULL, so a task can outlive its event with a NULL "
            "event_id — and a NULL never matches the ``IN (...)`` that every "
            "event-scoped filter is built from, which would make such a row "
            "visible to everyone. This flag survives that and keeps the "
            "exclusion in the WHERE clause."
        ),
    )

    # Generation config fields (stored for re-generation)
    location: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    # SET NULL next to an event FK is the shape app/models/CLAUDE.md warns
    # about: a user delete cascades to the event, the events->tasks SET NULL
    # rewrites this row, and Postgres queues a re-check of location_id that
    # would fire after the events->locations CASCADE removed the location.
    # Deferring the *check* (the SET NULL action itself still runs at once)
    # lets the locations->tasks SET NULL supersede the row first. Pinned by
    # tests/crud/test_venue_map.py::TestEventDeleteWithLocations.
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
        description=(
            "The Location this row points at. ``location`` keeps the name as a "
            "denormalised display string, so deleting the location leaves it "
            "behind as free text."
        ),
    )
    category: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    # Deferred for the same reason as location_id above: a user delete
    # cascades to the event, the events->tasks SET NULL rewrites this row and
    # queues a re-check of team_id, which would fire after the events->teams
    # CASCADE has removed the team. Pinned by
    # tests/api/routes/test_teams.py::TestDeletionCascades.
    team_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey(
                "event_teams.id",
                ondelete="SET NULL",
                deferrable=True,
                initially="DEFERRED",
            ),
            nullable=True,
            index=True,
        ),
        description=(
            "The team whose approved members may book this task's shifts. "
            "None means anyone in the event may book."
        ),
    )
    shift_duration_minutes: int | None = Field(
        default=None, sa_column=sa.Column(sa.Integer, nullable=True)
    )
    default_start_time: time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    default_end_time: time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    people_per_shift: int | None = Field(
        default=None, sa_column=sa.Column(sa.Integer, nullable=True)
    )
    schedule_overrides: list[dict[str, Any]] | None = Field(
        default=None, sa_column=sa.Column(sa.JSON, nullable=True)
    )

    shifts: list["Shift"] = Relationship(
        back_populates="task",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    shift_batches: list["ShiftBatch"] = Relationship(
        back_populates="task",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    event: "Event" = Relationship(back_populates="tasks")
