"""Email notification channel using aiosmtplib."""

from email.message import EmailMessage
from pathlib import Path

from app.core.config import settings
from app.core.logger import get_logger
from app.logic.notifications.channels.base import NotificationChannel
from app.logic.notifications.messages import get_email_strings
from app.models.user import User
from app.schemas.notification import NotificationData

logger = get_logger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "email-templates" / "build"


class EmailChannel(NotificationChannel):
    name = "email"

    def is_configured(self) -> bool:
        return settings.emails_enabled and settings.emails_configured

    def _is_valid_recipient(self, recipient: User) -> bool:
        if not recipient.email:
            logger.warning(
                f"No email for user {recipient.id}, skipping email notification"
            )
            return False
        if recipient.auth0_sub.startswith("demo|"):
            logger.debug(f"Skipping email for demo user {recipient.id}")
            return False
        return True

    async def send(
        self,
        *,
        recipient: User,
        title: str,
        body: str,
        data: NotificationData | None = None,
    ) -> bool:
        if not settings.emails_enabled:
            logger.debug("Email disabled in local environment, skipping")
            return True
        if not settings.emails_configured:
            logger.warning(
                "SMTP not configured (missing SMTP_HOST or EMAILS_FROM_EMAIL)"
            )
            return False

        if not self._is_valid_recipient(recipient):
            return False

        try:
            msg = self._build_message(
                title=title,
                body=body,
                data=data,
                language=recipient.preferred_language,
                to=recipient.email,
            )
            await self._smtp_send(msg)
            logger.info(f"Email sent to {recipient.email}: {title}")
            return True

        except Exception:
            logger.exception(f"Failed to send email to {recipient.email}")
            return False

    async def send_batch(
        self,
        *,
        recipients: list[User],
        title: str,
        body: str,
        data: NotificationData | None = None,
        language: str = "en",
    ) -> bool:
        """Send a single email to multiple recipients via BCC, grouped by language."""
        if not settings.emails_enabled:
            logger.debug("Email disabled in local environment, skipping batch")
            return True
        if not settings.emails_configured:
            logger.warning(
                "SMTP not configured (missing SMTP_HOST or EMAILS_FROM_EMAIL)"
            )
            return False

        valid = [r for r in recipients if self._is_valid_recipient(r)]
        if not valid:
            return False

        try:
            from_email = settings.EMAILS_FROM_EMAIL or "noreply@example.com"
            from_name = settings.EMAILS_FROM_NAME or settings.PROJECT_NAME
            msg = self._build_message(
                title=title,
                body=body,
                data=data,
                language=language,
                to=f"{from_name} <{from_email}>",
            )
            msg["Bcc"] = ", ".join(r.email for r in valid if r.email)
            await self._smtp_send(msg)
            emails = [r.email for r in valid]
            logger.info(
                f"Batch email sent to {len(emails)} recipients ({language}): {title}"
            )
            return True

        except Exception:
            logger.exception(
                f"Failed to send batch email to {len(valid)} recipients ({language})"
            )
            return False

    def _build_message(
        self,
        *,
        title: str,
        body: str,
        data: NotificationData | None,
        language: str,
        to: str | None,
    ) -> EmailMessage:
        html_body = _build_html(title=title, body=body, data=data, language=language)
        from_name = settings.EMAILS_FROM_NAME or settings.PROJECT_NAME
        from_email = settings.EMAILS_FROM_EMAIL or "noreply@example.com"

        msg = EmailMessage()
        msg["Subject"] = f"[{settings.PROJECT_NAME}] {title}"
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to
        msg.set_content(body)
        msg.add_alternative(html_body, subtype="html")
        return msg

    async def _smtp_send(self, msg: EmailMessage) -> None:
        import aiosmtplib

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST or "localhost",
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,  # type: ignore[arg-type]
            start_tls=settings.SMTP_TLS,
            use_tls=settings.SMTP_SSL,
        )


def _build_html(
    *,
    title: str,
    body: str,
    data: NotificationData | None = None,
    language: str = "en",
) -> str:
    """Build a simple HTML email body with localized template strings."""
    frontend_url = settings.FRONTEND_HOST
    email_strings = get_email_strings(language)

    # Build action link if we have relevant data
    action_link = ""
    if data:
        if "event_id" in data:
            action_link = f"{frontend_url}/app/events/{data['event_id']}"
        elif "event_group_id" in data:
            action_link = f"{frontend_url}/app/event-groups/{data['event_group_id']}"

    action_html = ""
    if action_link:
        action_html = f"""
        <div style="text-align: center;">
            <a href="{action_link}"
               style="background-color: #1f2937; color: #ffffff; padding: 12px 28px;
                      text-decoration: none; border-radius: 8px; display: inline-block;
                      font-size: 14px; font-weight: 600;">
                {email_strings["view_details"]}
            </a>
        </div>
        """

    logo_url = f"{frontend_url}/icon.svg"
    preferences_url = f"{frontend_url}/app/settings/notifications"

    return f"""
    <!DOCTYPE html>
    <html lang="{language}">
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                 margin: 0; padding: 0; background-color: #f3f4f6; color: #1f2937;">
        <div style="max-width: 560px; margin: 0 auto; padding: 40px 20px;">
            <!-- Card -->
            <div style="background-color: #ffffff; border-radius: 12px; overflow: hidden;
                        box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                <!-- Header -->
                <div style="background-color: #1f2937; padding: 24px; text-align: center;">
                    <img src="{logo_url}" alt="{settings.PROJECT_NAME}"
                         style="height: 40px; width: 40px; margin-bottom: 8px;" />
                    <div style="color: #ffffff; font-size: 18px; font-weight: 600;">
                        {settings.PROJECT_NAME}
                    </div>
                </div>
                <!-- Body -->
                <div style="padding: 32px 24px;">
                    <h2 style="margin: 0 0 12px; font-size: 20px; color: #1f2937;">{title}</h2>
                    <p style="margin: 0 0 24px; color: #4b5563; font-size: 15px; line-height: 1.6;">
                        {body.replace(chr(10), "<br>")}
                    </p>
                    {action_html}
                </div>
                <!-- Footer -->
                <div style="border-top: 1px solid #e5e7eb; padding: 16px 24px;
                            background-color: #f9fafb; text-align: center;">
                    <p style="margin: 0; font-size: 12px; color: #9ca3af; line-height: 1.5;">
                        {email_strings["footer_text"]}
                        <br />
                        <a href="{preferences_url}"
                           style="color: #6b7280; text-decoration: underline;">
                            {email_strings["manage_preferences"]}
                        </a>
                    </p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
