import datetime as dt
import uuid
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.shift_batch import ShiftBatch
    from app.models.task import Task

if __name__ != "__main__":
    from app.models.booking import Booking  # noqa: F401


class Shift(Base, table=True):
    __tablename__ = "shifts"  # type: ignore[assignment]
    __table_args__ = (sa.Index("ix_shifts_task_id_date", "task_id", "date"),)

    task_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    batch_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("shift_batches.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )
    title: str = Field(sa_column=sa.Column(sa.String, nullable=False, index=True))
    description: str | None = Field(
        default=None, sa_column=sa.Column(sa.Text, nullable=True)
    )
    date: dt.date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    start_time: dt.time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    end_time: dt.time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
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
        default=None, sa_column=sa.Column(sa.String, nullable=True, index=True)
    )
    max_bookings: int = Field(
        default=1, sa_column=sa.Column(sa.Integer, nullable=False)
    )

    task: "Task" = Relationship(back_populates="shifts")
    batch: Optional["ShiftBatch"] = Relationship(back_populates="shifts")
    bookings: list["Booking"] = Relationship(
        back_populates="shift",
        sa_relationship_kwargs={
            "cascade": "save-update, merge",
            "passive_deletes": True,
        },
    )
