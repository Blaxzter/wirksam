import datetime as dt
import uuid

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import Base


class WorkLog(Base, table=True):
    """Hours an event admin credits to a volunteer by hand.

    Shift hours are derived from bookings and never stored; this table only
    holds what no shift accounts for — set-up the day before, an errand, a
    shift someone covered without booking it.
    """

    __tablename__ = "work_logs"  # type: ignore[assignment]
    __table_args__ = (sa.Index("ix_work_logs_event_id_user_id", "event_id", "user_id"),)

    event_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    date: dt.date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    minutes: int = Field(sa_column=sa.Column(sa.Integer, nullable=False))
    description: str = Field(sa_column=sa.Column(sa.Text, nullable=False))

    # Deliberately no foreign key. CASCADE would delete a volunteer's hours
    # along with the admin who entered them, and SET NULL on a user FK in a
    # table that also points at events breaks user deletion (see CLAUDE.md in
    # this directory). The name is snapshotted so the entry still says who
    # made it after that account is gone.
    created_by_id: uuid.UUID | None = Field(
        default=None, sa_column=sa.Column(sa.Uuid, nullable=True)
    )
    created_by_name: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
