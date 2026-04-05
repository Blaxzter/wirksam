import uuid
from datetime import date, time
from typing import Any

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base

if __name__ != "__main__":
    from app.models.duty_slot import DutySlot  # noqa: F401

if __name__ != "__main__":
    from app.models.event_group import EventGroup  # noqa: F401

if __name__ != "__main__":
    from app.models.slot_batch import SlotBatch  # noqa: F401


class Event(Base, table=True):
    __tablename__ = "events"  # type: ignore[assignment]

    name: str = Field(sa_column=sa.Column(sa.String, nullable=False, index=True))
    description: str | None = Field(
        default=None, sa_column=sa.Column(sa.Text, nullable=True)
    )
    start_date: date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    end_date: date = Field(sa_column=sa.Column(sa.Date, nullable=False))
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
    event_group_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("event_groups.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )

    # Generation config fields (stored for re-generation)
    location: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    category: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    slot_duration_minutes: int | None = Field(
        default=None, sa_column=sa.Column(sa.Integer, nullable=True)
    )
    default_start_time: time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    default_end_time: time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    people_per_slot: int | None = Field(
        default=None, sa_column=sa.Column(sa.Integer, nullable=True)
    )
    schedule_overrides: list[dict[str, Any]] | None = Field(
        default=None, sa_column=sa.Column(sa.JSON, nullable=True)
    )

    duty_slots: list["DutySlot"] = Relationship(
        back_populates="event",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    slot_batches: list["SlotBatch"] = Relationship(
        back_populates="event",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    event_group: "EventGroup" = Relationship(back_populates="events")
