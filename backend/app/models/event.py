from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base

if __name__ != "__main__":
    from app.models.duty_slot import DutySlot  # noqa: F401


class Event(Base, table=True):
    __tablename__ = "events"

    name: str = Field(sa_column=sa.Column(sa.String, nullable=False, index=True))
    description: str | None = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))
    start_date: date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    end_date: date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    status: str = Field(default="draft", sa_column=sa.Column(sa.String, nullable=False, index=True))
    created_by_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(sa.Uuid, sa.ForeignKey("users.id"), nullable=True, index=True),
    )

    duty_slots: list["DutySlot"] = Relationship(
        back_populates="event",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
