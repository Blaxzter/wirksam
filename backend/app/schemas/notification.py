import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

ScopeType = Literal["global", "event_group", "event", "duty_slot"]

# Values in notification data are always stringified UUIDs, ints, or None.
NotificationData = dict[str, str | int | None]


# ── NotificationType ──────────────────────────────────────────────


class NotificationTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    category: str
    is_admin_only: bool
    default_channels: list[str]
    is_active: bool


# ── NotificationSubscription (preferences) ────────────────────────


class NotificationSubscriptionCreate(BaseModel):
    notification_type_id: uuid.UUID
    email_enabled: bool = True
    push_enabled: bool = True
    telegram_enabled: bool = False
    scope_type: ScopeType = "global"
    scope_id: uuid.UUID | None = None
    is_muted: bool = False


class NotificationSubscriptionUpdate(BaseModel):
    email_enabled: bool | None = None
    push_enabled: bool | None = None
    telegram_enabled: bool | None = None
    is_muted: bool | None = None


class NotificationSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    notification_type_id: uuid.UUID
    email_enabled: bool
    push_enabled: bool
    telegram_enabled: bool
    scope_type: str
    scope_id: uuid.UUID | None = None
    is_muted: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class NotificationPreferencesBulkUpdate(BaseModel):
    """Full matrix of preferences sent from the frontend."""

    preferences: list[NotificationSubscriptionCreate]


# ── Notification ──────────────────────────────────────────────────


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    recipient_id: uuid.UUID
    notification_type_code: str
    title: str
    body: str
    data: NotificationData | None = None
    is_read: bool
    read_at: dt.datetime | None = None
    channels_sent: list[str]
    channels_failed: list[str]
    created_at: dt.datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationRead]
    total: int
    unread_count: int
    skip: int
    limit: int


class UnreadCountResponse(BaseModel):
    unread_count: int


# ── PushSubscription ──────────────────────────────────────────────


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    p256dh_key: str
    auth_key: str
    user_agent: str | None = None


class PushSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    endpoint: str
    user_agent: str | None = None
    created_at: dt.datetime


# ── TelegramBinding ───────────────────────────────────────────────


class TelegramBindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    telegram_chat_id: str | None = None
    telegram_username: str | None = None
    is_verified: bool
    created_at: dt.datetime


class TelegramBindRequest(BaseModel):
    """Response when initiating a Telegram binding."""

    pass


class TelegramBindResponse(BaseModel):
    verification_code: str
    bot_username: str | None = None
    expires_at: dt.datetime


class TelegramVerifyRequest(BaseModel):
    verification_code: str
    telegram_chat_id: str
    telegram_username: str | None = None


class TelegramLoginData(BaseModel):
    """Auth data returned by the Telegram Login Widget."""

    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


class TelegramConfigResponse(BaseModel):
    bot_username: str | None = None
    is_configured: bool


# ── Global channel settings (user-level kill switches) ───────────


class GlobalChannelSettingsRead(BaseModel):
    notify_email: bool
    notify_push: bool
    notify_telegram: bool


class GlobalChannelSettingsUpdate(BaseModel):
    notify_email: bool | None = None
    notify_push: bool | None = None
    notify_telegram: bool | None = None


# ── Telegram Webhook (incoming bot update) ───────────────────────


class TelegramChat(BaseModel):
    id: int
    username: str | None = None


class TelegramMessage(BaseModel):
    text: str | None = None
    chat: TelegramChat | None = None


class TelegramWebhookUpdate(BaseModel):
    """Subset of the Telegram Bot API Update object we actually use."""

    message: TelegramMessage | None = None
