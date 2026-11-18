import datetime as dt
import uuid
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.shift import Shift  # noqa: F401
    from app.models.user import User  # noqa: F401


class Booking(Base, table=True):
    __tablename__ = "bookings"  # type: ignore[assignment]
    __table_args__ = (
        sa.UniqueConstraint("shift_id", "user_id", name="uq_booking_shift_user"),
        sa.Index("ix_bookings_shift_id_status", "shift_id", "status"),
    )

    shift_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("shifts.id", ondelete="SET NULL"),
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

    # Snapshot fields — populated when a shift is admin-deleted so users still see context
    cancelled_shift_title: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    cancelled_shift_date: dt.date | None = Field(
        default=None, sa_column=sa.Column(sa.Date, nullable=True)
    )
    cancelled_shift_start_time: dt.time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    cancelled_shift_end_time: dt.time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    cancelled_task_name: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )

    # The shared list this booking was signed up through (None: booked in the
    # app). No foreign key, like voucher_earnings.booking_id: SET NULL next to
    # user_id CASCADE is the trap in app/models/CLAUDE.md (a user delete
    # cascades to their events, their lists, and these rows at once), and a
    # list only ever goes together with its event. A dangling id joins nothing.
    shared_list_id: uuid.UUID | None = Field(
        default=None, sa_column=sa.Column(sa.Uuid, nullable=True, index=True)
    )
    # List guests only: this sign-up's own person. Whether its form said the
    # first name appears on shared lists that show first names, and the name
    # and phone the chain stored when it signed up. A guest account pools
    # sign-ups of several people (a family sharing an address), so these never
    # come from the guest user. Member bookings: false, NULL, NULL; their
    # person is the user. Cleared by logic/shared_lists/erase.anonymise.
    show_first_name: bool = Field(
        default=False,
        sa_column=sa.Column(
            sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
    )
    guest_name: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    guest_phone: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )

    shift: Optional["Shift"] = Relationship(back_populates="bookings")
    user: Optional["User"] = Relationship()
