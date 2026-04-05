import datetime as dt
import uuid
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.duty_slot import DutySlot  # noqa: F401
    from app.models.user import User  # noqa: F401


class Booking(Base, table=True):
    __tablename__ = "bookings"  # type: ignore[assignment]
    __table_args__ = (
        sa.UniqueConstraint("duty_slot_id", "user_id", name="uq_booking_slot_user"),
    )

    duty_slot_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("duty_slots.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    status: str = Field(
        default="confirmed", sa_column=sa.Column(sa.String, nullable=False, index=True)
    )
    notes: str | None = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))
    cancellation_reason: str | None = Field(
        default=None, sa_column=sa.Column(sa.Text, nullable=True)
    )

    # Snapshot fields — populated when a slot is admin-deleted so users still see context
    cancelled_slot_title: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    cancelled_slot_date: dt.date | None = Field(
        default=None, sa_column=sa.Column(sa.Date, nullable=True)
    )
    cancelled_slot_start_time: dt.time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    cancelled_slot_end_time: dt.time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    cancelled_event_name: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )

    duty_slot: Optional["DutySlot"] = Relationship(back_populates="bookings")
    user: Optional["User"] = Relationship()
