"""Core notification dispatch service."""

import uuid
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.logger import get_logger
from app.core.sse import sse_manager
from app.crud.notification import notification as crud_notification
from app.crud.notification_subscription import (
    notification_subscription as crud_subscription,
)
from app.logic.notifications.channels.base import NotificationChannel
from app.logic.notifications.channels.email import EmailChannel
from app.logic.notifications.channels.push import PushChannel
from app.logic.notifications.channels.telegram import TelegramChannel
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationData

logger = get_logger(__name__)

# Type alias for a factory that returns (title, body) given a language code
MessageFactory = Callable[[str], tuple[str, str]]


class NotificationService:
    """Dispatches notifications to users through configured channels."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.channels: dict[str, NotificationChannel] = {
            "email": EmailChannel(),
            "push": PushChannel(),
            "telegram": TelegramChannel(),
        }

    async def notify(
        self,
        *,
        recipient_ids: list[uuid.UUID],
        type_code: str,
        title: str = "",
        body: str = "",
        message_factory: MessageFactory | None = None,
        data: NotificationData | None = None,
        scope_chain: list[tuple[str, uuid.UUID]] | None = None,
        force_channels: list[str] | None = None,
    ) -> list[Notification]:
        """Send a notification to one or more recipients.

        For each recipient:
        1. Resolve which channels are enabled (via hierarchical subscription)
        2. Resolve localized title/body via message_factory (or use static strings)
        3. Create in-app Notification record
        4. Dispatch to each enabled channel (emails batched by language via BCC)
        5. Record delivery status
        """
        notifications: list[Notification] = []

        # Collect email recipients by language for batch sending
        pending_emails: dict[str, list[tuple[User, Notification, str, str]]] = {}

        for recipient_id in recipient_ids:
            # Load recipient user
            result = await self.db.execute(
                select(User).where(col(User.id) == recipient_id)
            )
            recipient = result.scalar_one_or_none()
            if not recipient:
                logger.warning(f"Recipient {recipient_id} not found, skipping")
                continue

            # Resolve localized title/body
            if message_factory:
                resolved_title, resolved_body = message_factory(
                    recipient.preferred_language
                )
            else:
                resolved_title, resolved_body = title, body

            # Resolve channels — use force_channels if provided, else subscription-based
            if force_channels is not None:
                channel_config = {ch: (ch in force_channels) for ch in self.channels}
            else:
                channel_config = await crud_subscription.resolve_channels(
                    self.db,
                    user_id=recipient_id,
                    type_code=type_code,
                    scope_chain=scope_chain,
                )

            if channel_config is None:
                logger.debug(f"Notification {type_code} muted for user {recipient_id}")
                continue

            # Create in-app notification record
            notif = await crud_notification.create_notification(
                self.db,
                recipient_id=recipient_id,
                notification_type_code=type_code,
                title=resolved_title,
                body=resolved_body,
                data=data,
            )

            # Dispatch to non-email channels immediately; defer email for batching
            channels_sent: list[str] = []
            channels_failed: list[str] = []

            for channel_name, enabled in channel_config.items():
                if not enabled:
                    continue

                if channel_name == "email":
                    lang = recipient.preferred_language
                    pending_emails.setdefault(lang, []).append(
                        (recipient, notif, resolved_title, resolved_body)
                    )
                    continue

                channel = self.channels.get(channel_name)
                if not channel or not channel.is_configured():
                    continue

                try:
                    success = await channel.send(
                        recipient=recipient,
                        title=resolved_title,
                        body=resolved_body,
                        data=data,
                    )
                    if success:
                        channels_sent.append(channel_name)
                    else:
                        channels_failed.append(channel_name)
                except Exception:
                    logger.exception(
                        f"Channel {channel_name} failed for user {recipient_id}"
                    )
                    channels_failed.append(channel_name)

            # Update delivery status (email status added after batch send)
            notif.channels_sent = channels_sent
            notif.channels_failed = channels_failed
            self.db.add(notif)
            await self.db.flush()

            notifications.append(notif)

            # Push updated unread count to any open SSE connections
            new_count = await crud_notification.get_unread_count(
                self.db, user_id=recipient_id
            )
            await sse_manager.broadcast(
                recipient_id, "unread_count", {"unread_count": new_count}
            )

        # Batch-send emails grouped by language via BCC
        email_channel = self.channels.get("email")
        if isinstance(email_channel, EmailChannel) and pending_emails:
            for lang, entries in pending_emails.items():
                recipients_for_lang = [user for user, _, _, _ in entries]
                batch_title = entries[0][2]
                batch_body = entries[0][3]
                success = await email_channel.send_batch(
                    recipients=recipients_for_lang,
                    title=batch_title,
                    body=batch_body,
                    data=data,
                    language=lang,
                )
                for _, notif, _, _ in entries:
                    if success:
                        notif.channels_sent = [*notif.channels_sent, "email"]
                    else:
                        notif.channels_failed = [*notif.channels_failed, "email"]
                    self.db.add(notif)
            await self.db.flush()

        return notifications

    async def notify_admins(
        self,
        *,
        type_code: str,
        title: str = "",
        body: str = "",
        message_factory: MessageFactory | None = None,
        data: NotificationData | None = None,
    ) -> list[Notification]:
        """Send a notification to all active admin users."""
        from sqlalchemy.dialects.postgresql import JSONB

        result = await self.db.execute(
            select(User).where(
                col(User.is_active) == True,  # noqa: E712
                User.roles.cast(JSONB).contains(["admin"]),  # type: ignore[union-attr]
            )
        )
        admins = result.scalars().all()
        admin_ids = [a.id for a in admins]

        if not admin_ids:
            logger.warning("No admin users found for admin notification")
            return []

        return await self.notify(
            recipient_ids=admin_ids,
            type_code=type_code,
            title=title,
            body=body,
            message_factory=message_factory,
            data=data,
        )
