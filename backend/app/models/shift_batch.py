import uuid
from datetime import date, time
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.task import Task

if __name__ != "__main__":
    from app.models.shift import Shift  # noqa: F401


class ShiftBatch(Base, table=True):
    __tablename__ = "shift_batches"  # type: ignore[assignment]

    task_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
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

    # Batch-level properties applied to all shifts
    location: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    location_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("locations.id", ondelete="SET NULL"),
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

    # Generation config
    default_start_time: time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    default_end_time: time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    shift_duration_minutes: int | None = Field(
        default=None, sa_column=sa.Column(sa.Integer, nullable=True)
    )
    people_per_shift: int | None = Field(
        default=None, sa_column=sa.Column(sa.Integer, nullable=True)
    )
    remainder_mode: str | None = Field(
        default="drop", sa_column=sa.Column(sa.String, nullable=True)
    )
    schedule_overrides: list[dict[str, Any]] | None = Field(
        default=None, sa_column=sa.Column(sa.JSON, nullable=True)
    )

    task: "Task" = Relationship(back_populates="shift_batches")
    shifts: list["Shift"] = Relationship(
        back_populates="batch",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
