"""Core notification dispatch service."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.logger import get_logger
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
        title: str,
        body: str,
        data: NotificationData | None = None,
        scope_chain: list[tuple[str, uuid.UUID]] | None = None,
    ) -> list[Notification]:
        """Send a notification to one or more recipients.

        For each recipient:
        1. Resolve which channels are enabled (via hierarchical subscription)
        2. Create in-app Notification record
        3. Dispatch to each enabled channel
        4. Record delivery status
        """
        notifications: list[Notification] = []

        for recipient_id in recipient_ids:
            # Load recipient user
            result = await self.db.execute(
                select(User).where(col(User.id) == recipient_id)
            )
            recipient = result.scalar_one_or_none()
            if not recipient:
                logger.warning(f"Recipient {recipient_id} not found, skipping")
                continue

            # Resolve channels
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
                title=title,
                body=body,
                data=data,
            )

            # Dispatch to channels
            channels_sent: list[str] = []
            channels_failed: list[str] = []

            for channel_name, enabled in channel_config.items():
                if not enabled:
                    continue

                channel = self.channels.get(channel_name)
                if not channel or not channel.is_configured():
                    continue

                try:
                    success = await channel.send(
                        recipient=recipient,
                        title=title,
                        body=body,
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

            # Update delivery status
            notif.channels_sent = channels_sent
            notif.channels_failed = channels_failed
            self.db.add(notif)
            await self.db.flush()

            notifications.append(notif)

        return notifications

    async def notify_admins(
        self,
        *,
        type_code: str,
        title: str,
        body: str,
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
            data=data,
        )
