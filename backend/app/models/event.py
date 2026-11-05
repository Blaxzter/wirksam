import uuid
from datetime import date, datetime, time
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.core.config import settings
from app.logic import clock
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.user_availability import UserAvailability


class Event(Base, table=True):
    __tablename__ = "events"  # type: ignore[assignment]
    __table_args__ = (
        sa.CheckConstraint(
            "voucher_manual_redeem IN ('on_shift', 'in_charge')",
            name="ck_events_voucher_manual_redeem",
        ),
    )

    name: str = Field(sa_column=sa.Column(sa.String, nullable=False, index=True))
    description: str | None = Field(
        default=None, sa_column=sa.Column(sa.Text, nullable=True)
    )
    start_date: date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    end_date: date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    default_start_time: time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    default_end_time: time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    status: str = Field(
        default="draft", sa_column=sa.Column(sa.String, nullable=False, index=True)
    )
    visibility: str = Field(
        default="private",
        sa_column=sa.Column(
            sa.String(16), nullable=False, server_default="private", index=True
        ),
        description=(
            "'public' — listed in Discover, anyone may request to join. "
            "'private' — invitation only, invisible to non-members."
        ),
    )
    is_featured: bool = Field(
        default=False,
        sa_column=sa.Column(
            sa.Boolean, nullable=False, server_default=sa.text("false"), index=True
        ),
        description="Superadmin-curated: surfaced on the home screen",
    )
    is_sandbox: bool = Field(
        default=False,
        sa_column=sa.Column(
            sa.Boolean, nullable=False, server_default=sa.text("false"), index=True
        ),
        description=(
            "Throwaway event behind the 'try a test event' button. It belongs to "
            "one guest account, is hidden from every listing including the "
            "superadmin's, and is hard-deleted once sandbox_expires_at passes."
        ),
    )
    sandbox_expires_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime, nullable=True, index=True),
        description=(
            "Naive UTC deadline after which the sweep purges this event and its "
            "guest. NULL on every real event — the column is meaningless there."
        ),
    )
    timezone: str = Field(
        default_factory=lambda: settings.EVENT_TIMEZONE,
        sa_column=sa.Column(sa.String(64), nullable=False),
        description=(
            "IANA name of the zone the event's shift times are read in. Shift "
            "times carry no zone: changing this leaves a 10:00 shift at 10:00 "
            "and moves the moment it happens (app/logic/clock.py)."
        ),
    )
    # Voucher rules for every task in the event (app/logic/permissions.py:
    # may_redeem_manually and voucher_shifts_locked).
    voucher_manual_redeem: str = Field(
        default="on_shift",
        sa_column=sa.Column(sa.String(16), nullable=False, server_default="on_shift"),
        description=(
            "Who may redeem vouchers without a code, by picking the person: "
            "'on_shift' - also whoever is on a running shift at that point; "
            "'in_charge' - only the event admins and the point's people in charge."
        ),
    )
    managers_edit_voucher_shifts: bool = Field(
        default=False,
        sa_column=sa.Column(
            sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        description=(
            "People in charge of a task that earns vouchers may add, move, "
            "resize and delete its shifts. Off: only the event admins may, "
            "since every extra shift earns vouchers."
        ),
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

    tasks: list["Task"] = Relationship(back_populates="event")
    availabilities: list["UserAvailability"] = Relationship(
        back_populates="event",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    @property
    def is_expired(self) -> bool:
        """Whether the event's last day is over, on the event's own clock."""
        return self.end_date < clock.wall_clock_now(self.timezone).date()
