import datetime
import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.event_group import EventGroup


class UserAvailability(Base, table=True):
    __tablename__ = "user_availabilities"  # type: ignore[assignment]
    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "event_group_id", name="uq_availability_user_group"
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
    event_group_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("event_groups.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    availability_type: str = Field(
        sa_column=sa.Column(sa.String, nullable=False, index=True)
    )
    notes: str | None = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))
    default_start_time: datetime.time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    default_end_time: datetime.time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )

    event_group: "EventGroup" = Relationship(back_populates="availabilities")
    available_dates: list["UserAvailabilityDate"] = Relationship(
        back_populates="availability",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class UserAvailabilityDate(Base, table=True):
    __tablename__ = "user_availability_dates"  # type: ignore[assignment]

    availability_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("user_availabilities.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    slot_date: datetime.date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    start_time: datetime.time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    end_time: datetime.time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )

    availability: "UserAvailability" = Relationship(back_populates="available_dates")
