"""Email notification channel using fastapi-mail."""

from pathlib import Path

from app.core.config import settings
from app.core.logger import get_logger
from app.logic.notifications.channels.base import NotificationChannel
from app.schemas.notification import NotificationData
from app.models.user import User

logger = get_logger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "email-templates" / "build"


class EmailChannel(NotificationChannel):
    name = "email"

    def is_configured(self) -> bool:
        return settings.emails_enabled

    async def send(
        self,
        *,
        recipient: User,
        title: str,
        body: str,
        data: NotificationData | None = None,
    ) -> bool:
        if not self.is_configured():
            logger.warning("Email channel not configured, skipping")
            return False

        if not recipient.email:
            logger.warning(f"No email for user {recipient.id}, skipping email notification")
            return False

        try:
            from fastapi_mail import (
                ConnectionConfig,
                FastMail,
                MessageSchema,
                MessageType,
            )

            conf = ConnectionConfig(
                MAIL_USERNAME=settings.SMTP_USER or "",
                MAIL_PASSWORD=settings.SMTP_PASSWORD or "",  # type: ignore[arg-type]
                MAIL_FROM=settings.EMAILS_FROM_EMAIL or "noreply@example.com",
                MAIL_FROM_NAME=settings.EMAILS_FROM_NAME or settings.PROJECT_NAME,
                MAIL_PORT=settings.SMTP_PORT,
                MAIL_SERVER=settings.SMTP_HOST or "localhost",
                MAIL_STARTTLS=settings.SMTP_TLS,
                MAIL_SSL_TLS=settings.SMTP_SSL,
                USE_CREDENTIALS=bool(settings.SMTP_USER),
            )

            # Build HTML body
            html_body = _build_html(title=title, body=body, data=data)

            message = MessageSchema(
                subject=f"[{settings.PROJECT_NAME}] {title}",
                recipients=[recipient.email],  # type: ignore[arg-type]
                body=html_body,
                subtype=MessageType.html,
            )

            fm = FastMail(conf)
            await fm.send_message(message)
            logger.info(f"Email sent to {recipient.email}: {title}")
            return True

        except Exception:
            logger.exception(f"Failed to send email to {recipient.email}")
            return False


def _build_html(*, title: str, body: str, data: NotificationData | None = None) -> str:
    """Build a simple HTML email body."""
    frontend_url = settings.FRONTEND_HOST

    # Build action link if we have relevant data
    action_link = ""
    if data:
        if "booking_id" in data:
            action_link = f'{frontend_url}/app/my-bookings'
        elif "event_id" in data:
            action_link = f'{frontend_url}/app/events/{data["event_id"]}'
        elif "event_group_id" in data:
            action_link = f'{frontend_url}/app/event-groups/{data["event_group_id"]}'

    action_html = ""
    if action_link:
        action_html = f"""
        <p style="margin-top: 20px;">
            <a href="{action_link}"
               style="background-color: #3b82f6; color: white; padding: 10px 20px;
                      text-decoration: none; border-radius: 6px; display: inline-block;">
                View Details
            </a>
        </p>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                 max-width: 600px; margin: 0 auto; padding: 20px; color: #1f2937;">
        <div style="border-bottom: 2px solid #3b82f6; padding-bottom: 16px; margin-bottom: 24px;">
            <h2 style="margin: 0; color: #1f2937;">{settings.PROJECT_NAME}</h2>
        </div>
        <h3 style="color: #1f2937;">{title}</h3>
        <p style="color: #4b5563; line-height: 1.6;">{body}</p>
        {action_html}
        <hr style="border: none; border-top: 1px solid #e5e7eb; margin-top: 32px;">
        <p style="font-size: 12px; color: #9ca3af;">
            This is an automated notification from {settings.PROJECT_NAME}.
            You can manage your notification preferences in the app settings.
        </p>
    </body>
    </html>
    """
