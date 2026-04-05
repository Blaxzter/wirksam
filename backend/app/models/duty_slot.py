import datetime as dt
import uuid
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.slot_batch import SlotBatch

if __name__ != "__main__":
    from app.models.booking import Booking  # noqa: F401


class DutySlot(Base, table=True):
    __tablename__ = "duty_slots"  # type: ignore[assignment]

    event_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    batch_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("slot_batches.id", ondelete="CASCADE"),
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
    category: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True, index=True)
    )
    max_bookings: int = Field(
        default=1, sa_column=sa.Column(sa.Integer, nullable=False)
    )

    event: "Event" = Relationship(back_populates="duty_slots")
    batch: Optional["SlotBatch"] = Relationship(back_populates="duty_slots")
    bookings: list["Booking"] = Relationship(
        back_populates="duty_slot",
        sa_relationship_kwargs={
            "cascade": "save-update, merge",
            "passive_deletes": True,
        },
    )
