from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base


class Booking(Base, table=True):
    __tablename__ = "bookings"
    __table_args__ = (
        sa.UniqueConstraint("duty_slot_id", "user_id", name="uq_booking_slot_user"),
    )

    duty_slot_id: uuid.UUID = Field(
        sa_column=sa.Column(sa.Uuid, sa.ForeignKey("duty_slots.id"), nullable=False, index=True)
    )
    user_id: uuid.UUID = Field(
        sa_column=sa.Column(sa.Uuid, sa.ForeignKey("users.id"), nullable=False, index=True)
    )
    status: str = Field(default="confirmed", sa_column=sa.Column(sa.String, nullable=False, index=True))
    notes: str | None = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))

    duty_slot: "DutySlot" = Relationship(back_populates="bookings")  # type: ignore[name-defined]
