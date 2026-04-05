import uuid
from datetime import date, time
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.event import Event

if __name__ != "__main__":
    from app.models.duty_slot import DutySlot  # noqa: F401


class SlotBatch(Base, table=True):
    __tablename__ = "slot_batches"  # type: ignore[assignment]

    event_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    label: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )

    # Date range this batch covers
    start_date: date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    end_date: date = Field(sa_column=sa.Column(sa.Date, nullable=False))

    # Batch-level properties applied to all slots
    location: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    category: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )

    # Generation config
    default_start_time: time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    default_end_time: time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    slot_duration_minutes: int | None = Field(
        default=None, sa_column=sa.Column(sa.Integer, nullable=True)
    )
    people_per_slot: int | None = Field(
        default=None, sa_column=sa.Column(sa.Integer, nullable=True)
    )
    remainder_mode: str | None = Field(
        default="drop", sa_column=sa.Column(sa.String, nullable=True)
    )
    schedule_overrides: list[dict[str, Any]] | None = Field(
        default=None, sa_column=sa.Column(sa.JSON, nullable=True)
    )

    event: "Event" = Relationship(back_populates="slot_batches")
    duty_slots: list["DutySlot"] = Relationship(
        back_populates="batch",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
