import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.logic.utils.pydantic_jsonb import PydanticJSONB
from app.models.base import Base
from app.schemas.booking_reminder import ReminderOffsetEntry


class User(Base, table=True):
    """Database model for application users.

    ``subject`` is this application's own opaque identity string, minted at
    registration as ``local|<uuid4hex>``. Two other prefixes are behavioural
    rather than cosmetic and must survive any future rework of this column:
    ``demo|`` marks the fake accounts ``/demo-data`` generates, which all three
    notification channels refuse to send to, ``test|`` marks the accounts
    ``POST /testing/reset`` is allowed to delete, and ``sandbox|`` marks the
    guest accounts minted by the "try a test event" button, which are purged
    together with their event when its TTL runs out.

    The ``sandbox|`` prefix and the ``is_sandbox`` column are not redundant: the
    prefix is what the notification channels grep for, the column is what every
    ``WHERE`` clause filters on — a prefix cannot be indexed usefully.
    """

    __tablename__ = "users"  # type: ignore[assignment]

    # Email is the login credential, so it has to be unique — but it is also
    # nullable (demo accounts, rows migrated from Auth0 that never had one) and
    # it is matched case-insensitively, because no one types their address the
    # same way twice. A partial unique index on ``lower(email)`` is the only
    # shape that satisfies all three; a plain ``unique=True`` on the column
    # would be case-sensitive and would index the NULLs for no benefit.
    #
    # It is declared here, and not only in the migration, because ``alembic
    # check`` gates CI: PostgreSQL reflects expression indexes, so an index the
    # database has and this metadata does not would read as drift forever.
    __table_args__ = (
        sa.Index(
            "ix_users_email_lower",
            sa.text("lower(email)"),
            unique=True,
            postgresql_where=sa.text("email IS NOT NULL"),
        ),
    )

    subject: str = Field(
        sa_column=sa.Column(sa.String, unique=True, index=True),
        description=(
            "Opaque local identity, e.g. 'local|<uuid4hex>'; the 'demo|', "
            "'test|' and 'sandbox|' prefixes are behavioural — see the class "
            "docstring"
        ),
    )
    is_sandbox: bool = Field(
        default=False,
        sa_column=sa.Column(
            sa.Boolean, nullable=False, server_default=sa.text("false"), index=True
        ),
        description=(
            "Throwaway guest behind the 'try a test event' button. Never "
            "listed in user search, never sent a notification, and deleted "
            "with its sandbox event."
        ),
    )
    password_hash: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String, nullable=True),
        description=(
            "bcrypt hash of this account's password. NULL means the account has "
            "no password at all — demo and test accounts never get one, and "
            "neither did any account provisioned before local auth existed"
        ),
    )
    email: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String, index=True),
        description="User's email address",
    )
    name: str | None = Field(default=None, description="User's display name")
    nickname: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(50), nullable=True),
        description="Shorter, informal name the user prefers to be called",
    )
    bio: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
        description="Free-text self description shown on the user's profile",
    )
    avatar_etag: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(64), nullable=True),
        description="sha256 of the locally stored avatar; null when no avatar is set",
    )
    email_verified: bool = Field(
        default=False,
        description="Whether the user's email is verified",
    )

    roles: list[str] = Field(
        default_factory=list,
        sa_column=sa.Column(JSONB, nullable=False, server_default="[]"),
        description="List of role identifiers",
    )
    is_active: bool = Field(default=True, description="Whether the user is active")
    # Separate from ``is_active`` on purpose. ``is_active`` is the moderation
    # switch (suspend / reinstate); this is where the account stands in the
    # registration queue that ``REGISTRATION_MODE=approval`` puts in front of
    # signup. Folding the two into one flag is what the old queue did, and it
    # left "suspended" and "not yet approved" indistinguishable to everyone,
    # including the person waiting. Existing and open-mode accounts are
    # "approved", which is also the server default the migration backfills.
    approval_status: str = Field(
        default="approved",
        sa_column=sa.Column(
            sa.String(16), nullable=False, server_default="approved", index=True
        ),
        description="Registration approval: approved, pending or rejected",
    )
    rejection_reason: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String, nullable=True),
        description="Reason for account rejection",
    )

    phone_number: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String, nullable=True),
        description="User's phone number for contact purposes",
    )

    preferred_language: str = Field(
        default="en",
        sa_column=sa.Column(sa.String(5), nullable=False, server_default="en"),
        description="User's preferred language for notifications (e.g., 'en', 'de')",
    )

    time_format: str = Field(
        default="locale",
        sa_column=sa.Column(sa.String(10), nullable=False, server_default="locale"),
        description="Display preference for times: 'locale' | 'h12' | 'h24'",
    )

    theme: str = Field(
        default="default",
        sa_column=sa.Column(sa.String(20), nullable=False, server_default="default"),
        description="Selected color palette: 'default' | 'classic'",
    )

    show_event_switcher_in_nav: bool = Field(
        default=False,
        sa_column=sa.Column(
            sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        description="Show a quick event switcher in the sidebar nav",
    )

    selected_event_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("events.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        description="Event that scopes this user's dashboard experience",
    )

    # Global notification channel kill switches
    notify_email: bool = Field(
        default=True,
        description="Global toggle: allow email notifications",
    )
    notify_push: bool = Field(
        default=True,
        description="Global toggle: allow push notifications",
    )
    notify_telegram: bool = Field(
        default=True,
        description="Global toggle: allow Telegram notifications",
    )

    # Default reminder offsets applied when creating new bookings
    default_reminder_offsets: list[ReminderOffsetEntry] = Field(
        default_factory=lambda: [
            ReminderOffsetEntry(offset_minutes=15, channels=["push"]),
            ReminderOffsetEntry(offset_minutes=1440, channels=["email"]),
        ],
        sa_column=sa.Column(
            PydanticJSONB(ReminderOffsetEntry, is_list=True),
            nullable=False,
            server_default="[]",
        ),
        description="Default reminders, e.g. [{offset_minutes: 60, channels: ['push']}]",
    )

    @property
    def is_admin(self) -> bool:
        """Whether this user is a platform superadmin.

        The only global role left. Anything scoped to a single event is
        answered by ``app.logic.permissions`` from that event's membership,
        never from this list.
        """
        return "admin" in self.roles
