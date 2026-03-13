"""Telegram Bot notification channel."""

import httpx

from app.core.config import settings
from app.core.logger import get_logger
from app.logic.notifications.channels.base import NotificationChannel
from app.models.user import User
from app.schemas.notification import NotificationData

logger = get_logger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramChannel(NotificationChannel):
    name = "telegram"

    def is_configured(self) -> bool:
        return bool(settings.TELEGRAM_BOT_TOKEN)

    async def send(
        self,
        *,
        recipient: User,
        title: str,
        body: str,
        data: NotificationData | None = None,
    ) -> bool:
        if not self.is_configured():
            logger.warning("Telegram channel not configured (missing bot token), skipping")
            return False

        try:
            from app.core.db import async_session
            from app.crud.telegram_binding import telegram_binding as crud_telegram

            async with async_session() as db:
                binding = await crud_telegram.get_by_user(db, user_id=recipient.id)

            if not binding or not binding.is_verified or not binding.telegram_chat_id:
                logger.debug(f"No verified Telegram binding for user {recipient.id}")
                return False

            # Format message in Markdown
            message = f"*{_escape_markdown(title)}*\n\n{_escape_markdown(body)}"

            url = f"{TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json={
                        "chat_id": binding.telegram_chat_id,
                        "text": message,
                        "parse_mode": "MarkdownV2",
                    },
                    timeout=10.0,
                )

            if response.status_code == 200:
                logger.info(f"Telegram message sent to chat {binding.telegram_chat_id}")
                return True
            else:
                logger.warning(
                    f"Telegram API error {response.status_code}: {response.text}"
                )
                return False

        except Exception:
            logger.exception("Failed to send Telegram notification")
            return False


def _escape_markdown(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special_chars = r"_*[]()~`>#+-=|{}.!"
    escaped = ""
    for char in text:
        if char in special_chars:
            escaped += f"\\{char}"
        else:
            escaped += char
    return escaped
