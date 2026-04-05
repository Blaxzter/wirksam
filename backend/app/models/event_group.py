import uuid
from datetime import date
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user_availability import UserAvailability


class EventGroup(Base, table=True):
    __tablename__ = "event_groups"  # type: ignore[assignment]

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

    events: list["Event"] = Relationship(back_populates="event_group")
    availabilities: list["UserAvailability"] = Relationship(
        back_populates="event_group",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
