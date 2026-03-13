import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User  # noqa: F401


class NotificationType(Base, table=True):
    """Registry of all notification types, seeded from code on startup."""

    __tablename__ = "notification_types"  # type: ignore[assignment]

    code: str = Field(
        sa_column=sa.Column(sa.String, unique=True, nullable=False, index=True),
        description="Unique code, e.g. 'booking.confirmed'",
    )
    name: str = Field(
        sa_column=sa.Column(sa.String, nullable=False),
        description="Human-readable name",
    )
    description: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
    )
    category: str = Field(
        sa_column=sa.Column(sa.String, nullable=False),
        description="Category: booking, slot, event, admin, user, etc.",
    )
    is_admin_only: bool = Field(
        default=False,
        description="Only visible/configurable by admin users",
    )
    default_channels: list[str] = Field(
        default_factory=lambda: ["email"],
        sa_column=sa.Column(JSONB, nullable=False, server_default='["email"]'),
        description="Default delivery channels, e.g. ['email', 'push']",
    )
    is_active: bool = Field(default=True, description="Whether this type is active")

    subscriptions: list["NotificationSubscription"] = Relationship(
        back_populates="notification_type"
    )


class NotificationSubscription(Base, table=True):
    """User preferences for a notification type with hierarchical scoping."""

    __tablename__ = "notification_subscriptions"  # type: ignore[assignment]
    __table_args__ = (
        sa.UniqueConstraint(
            "user_id",
            "notification_type_id",
            "scope_type",
            "scope_id",
            name="uq_subscription_scope",
        ),
    )

    user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    notification_type_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("notification_types.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    email_enabled: bool = Field(default=True)
    push_enabled: bool = Field(default=True)
    telegram_enabled: bool = Field(default=False)

    scope_type: str = Field(
        default="global",
        sa_column=sa.Column(sa.String, nullable=False, server_default="global"),
        description="Scope level: global, event_group, event, duty_slot",
    )
    scope_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(sa.Uuid, nullable=True),
        description="Entity ID for scoped subscriptions, null for global",
    )
    is_muted: bool = Field(
        default=False,
        description="Explicit opt-out at this scope level",
    )

    notification_type: Optional["NotificationType"] = Relationship(
        back_populates="subscriptions"
    )
    user: Optional["User"] = Relationship()


class Notification(Base, table=True):
    """Actual notification instance delivered to a user."""

    __tablename__ = "notifications"  # type: ignore[assignment]
    __table_args__ = (
        sa.Index(
            "ix_notifications_recipient_read_created",
            "recipient_id",
            "is_read",
            sa.text("created_at DESC"),
        ),
    )

    recipient_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    notification_type_code: str = Field(
        sa_column=sa.Column(sa.String, nullable=False, index=True),
        description="Denormalized type code for fast queries",
    )
    title: str = Field(sa_column=sa.Column(sa.String, nullable=False))
    body: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    data: dict[str, str | int | None] | None = Field(
        default=None,
        sa_column=sa.Column(JSONB, nullable=True),
        description="Arbitrary context data (slot_id, event_id, etc.)",
    )

    is_read: bool = Field(default=False)
    read_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime, nullable=True),
    )

    channels_sent: list[str] = Field(
        default_factory=list,
        sa_column=sa.Column(JSONB, nullable=False, server_default="[]"),
    )
    channels_failed: list[str] = Field(
        default_factory=list,
        sa_column=sa.Column(JSONB, nullable=False, server_default="[]"),
    )

    recipient: Optional["User"] = Relationship()


class PushSubscription(Base, table=True):
    """Web Push subscription endpoint for a user/device."""

    __tablename__ = "push_subscriptions"  # type: ignore[assignment]

    user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    endpoint: str = Field(
        sa_column=sa.Column(sa.Text, unique=True, nullable=False),
        description="Push service URL",
    )
    p256dh_key: str = Field(
        sa_column=sa.Column(sa.Text, nullable=False),
    )
    auth_key: str = Field(
        sa_column=sa.Column(sa.Text, nullable=False),
    )
    user_agent: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String, nullable=True),
    )

    user: Optional["User"] = Relationship()


class TelegramBinding(Base, table=True):
    """Links a user account to a Telegram chat for notifications."""

    __tablename__ = "telegram_bindings"  # type: ignore[assignment]

    user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        )
    )
    telegram_chat_id: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String, nullable=True, unique=True),
    )
    telegram_username: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String, nullable=True),
    )
    is_verified: bool = Field(default=False)
    verification_code: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String, nullable=True),
    )
    verification_expires_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime, nullable=True),
    )

    user: Optional["User"] = Relationship()
