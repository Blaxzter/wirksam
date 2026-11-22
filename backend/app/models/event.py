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

#: The colours an event can wear (``events.primary_color`` and
#: ``events.secondary_color``): a preset, tuned in ``frontend/src/index.css``
#: to stay readable in light and dark mode, or an own colour as ``#rrggbb``,
#: which the frontend (``src/lib/custom-colour.ts``) lightens or darkens as far
#: as readability needs. ``app.schemas.event`` spells out the same names. The
#: primary colour is also text on the page, so no preset too light to read on
#: cream (no yellow) and no green (the app's own already is); the secondary one
#: is only ever a fill under dark text, so it can be either.
EVENT_PRIMARY_COLORS = ("red", "orange", "teal", "blue", "violet", "pink", "slate")
EVENT_SECONDARY_COLORS = (
    "red",
    "orange",
    "yellow",
    "green",
    "teal",
    "blue",
    "violet",
    "pink",
    "slate",
)
#: The tone of the surfaces (``events.base_color``): the background, cards and
#: menu, which are WirkSam's cream without one. ``primary`` takes the main
#: colour's hue, ``neutral`` drops the tint. Only the hue changes, never how
#: light a surface is, so text on it reads as well as on the cream.
EVENT_BASE_COLORS = ("neutral", "primary", "blue", "teal", "green", "rose", "violet")


#: An own colour: six lower-case hex digits (the schema lower-cases it).
HEX_COLOUR_PATTERN = "^#[0-9a-f]{6}$"


def _one_of(column: str, names: tuple[str, ...]) -> str:
    """One of the presets, or an own colour."""
    presets = ", ".join(f"'{c}'" for c in names)
    return f"{column} IN ({presets}) OR {column} ~ '{HEX_COLOUR_PATTERN}'"


class Event(Base, table=True):
    __tablename__ = "events"  # type: ignore[assignment]
    __table_args__ = (
        sa.CheckConstraint(
            "voucher_manual_redeem IN ('on_shift', 'in_charge')",
            name="ck_events_voucher_manual_redeem",
        ),
        sa.CheckConstraint(
            _one_of("primary_color", EVENT_PRIMARY_COLORS),
            name="ck_events_primary_color",
        ),
        sa.CheckConstraint(
            _one_of("secondary_color", EVENT_SECONDARY_COLORS),
            name="ck_events_secondary_color",
        ),
        sa.CheckConstraint(
            _one_of("base_color", EVENT_BASE_COLORS),
            name="ck_events_base_color",
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
    managers_share_lists: bool = Field(
        default=True,
        sa_column=sa.Column(sa.Boolean, nullable=False, server_default=sa.text("true")),
        description=(
            "People in charge may create, edit, resume and rotate shared lists "
            "of their own tasks, which opens those tasks to people without an "
            "account. Off: only the event admins may; people in charge can "
            "still pause and end their lists."
        ),
    )
    primary_color: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(16), nullable=True),
        description=(
            "One of EVENT_PRIMARY_COLORS or #rrggbb: the app's buttons, links, "
            "active navigation and hero panels while the event is open. NULL "
            "keeps the app's own green."
        ),
    )
    secondary_color: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(16), nullable=True),
        description=(
            "One of EVENT_SECONDARY_COLORS or #rrggbb: the secondary buttons, "
            "hover and selected surfaces and the highlight chips. NULL keeps "
            "the app's own amber."
        ),
    )
    base_color: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(16), nullable=True),
        description=(
            "One of EVENT_BASE_COLORS or #rrggbb (its hue only): the tone of "
            "the background, cards and menu. NULL keeps the app's own cream."
        ),
    )
    logo_etag: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(64), nullable=True),
        description=(
            "sha256 of the event's logo (``event_logos``); NULL when it has "
            "none. Clients append it to the logo URL to bust caches."
        ),
    )
    logo_width: int | None = Field(
        default=None,
        sa_column=sa.Column(sa.Integer, nullable=True),
        description="Pixel size of the stored logo; NULL without one.",
    )
    logo_height: int | None = Field(
        default=None,
        sa_column=sa.Column(sa.Integer, nullable=True),
        description="Pixel size of the stored logo; NULL without one.",
    )
    logo_dark_etag: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(64), nullable=True),
        description=(
            "sha256 of the logo for dark mode (``event_logos``, variant "
            "``dark``); NULL when dark mode shows the light one."
        ),
    )
    logo_dark_width: int | None = Field(
        default=None,
        sa_column=sa.Column(sa.Integer, nullable=True),
        description="Pixel size of the stored dark-mode logo; NULL without one.",
    )
    logo_dark_height: int | None = Field(
        default=None,
        sa_column=sa.Column(sa.Integer, nullable=True),
        description="Pixel size of the stored dark-mode logo; NULL without one.",
    )
    logo_dark_tile: bool = Field(
        default=True,
        sa_column=sa.Column(sa.Boolean, nullable=False, server_default=sa.true()),
        description=(
            "Whether dark mode puts the logo on a white tile. On by default: "
            "most logos are drawn for a light page and would vanish on a dark one."
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
