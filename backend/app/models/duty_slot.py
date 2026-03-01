from __future__ import annotations

import uuid
import datetime as dt

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base

if __name__ != "__main__":
    from app.models.booking import Booking  # noqa: F401


class DutySlot(Base, table=True):
    __tablename__ = "duty_slots"

    event_id: uuid.UUID = Field(
        sa_column=sa.Column(sa.Uuid, sa.ForeignKey("events.id"), nullable=False, index=True)
    )
    title: str = Field(sa_column=sa.Column(sa.String, nullable=False, index=True))
    description: str | None = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))
    date: dt.date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    start_time: dt.time | None = Field(default=None, sa_column=sa.Column(sa.Time, nullable=True))
    end_time: dt.time | None = Field(default=None, sa_column=sa.Column(sa.Time, nullable=True))
    location: str | None = Field(default=None, sa_column=sa.Column(sa.String, nullable=True))
    category: str | None = Field(default=None, sa_column=sa.Column(sa.String, nullable=True, index=True))
    max_bookings: int = Field(default=1, sa_column=sa.Column(sa.Integer, nullable=False))

    event: "Event" = Relationship(back_populates="duty_slots")  # type: ignore[name-defined]
    bookings: list["Booking"] = Relationship(
        back_populates="duty_slot",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
