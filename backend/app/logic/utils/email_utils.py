from dataclasses import dataclass
from pathlib import Path

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from jinja2 import Template
from pydantic import NameEmail, SecretStr

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

TEMPLATE_FOLDER = (
    Path(__file__).resolve().parent.parent.parent / "email-templates" / "build"
)

conf = ConnectionConfig(
    MAIL_USERNAME=settings.SMTP_USER or "",
    MAIL_PASSWORD=SecretStr(settings.SMTP_PASSWORD or ""),
    MAIL_FROM=settings.EMAILS_FROM_EMAIL or "noreply@example.com",
    MAIL_FROM_NAME=settings.EMAILS_FROM_NAME or settings.PROJECT_NAME,
    MAIL_PORT=settings.SMTP_PORT,
    MAIL_SERVER=settings.SMTP_HOST or "localhost",
    MAIL_STARTTLS=settings.SMTP_TLS,
    MAIL_SSL_TLS=settings.SMTP_SSL,
    USE_CREDENTIALS=bool(settings.SMTP_USER),
    VALIDATE_CERTS=True,
    TEMPLATE_FOLDER=TEMPLATE_FOLDER,
)

fm = FastMail(conf)


@dataclass
class EmailData:
    html_content: str
    subject: str


async def send_email(
    *,
    email_to: str,
    subject: str = "",
    html_content: str = "",
) -> None:
    assert settings.emails_configured, "no provided configuration for email variables"
    message = MessageSchema(
        subject=subject,
        recipients=[NameEmail(name=email_to, email=email_to)],
        body=html_content,
        subtype=MessageType.html,
    )
    await fm.send_message(message)
    logger.info(f"Email sent to {email_to}")  # noqa: G004


async def send_email_template(
    *,
    email_to: str,
    subject: str,
    template_name: str,
    template_body: dict[str, str],
) -> None:
    assert settings.emails_configured, "no provided configuration for email variables"
    message = MessageSchema(
        subject=subject,
        recipients=[NameEmail(name=email_to, email=email_to)],
        template_body=template_body,
        subtype=MessageType.html,
    )
    await fm.send_message(message, template_name=template_name)
    logger.info(f"Template email sent to {email_to}")  # noqa: G004


def generate_test_email(email_to: str) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - Test email"
    template_str = (TEMPLATE_FOLDER / "test_email.html").read_text()
    html_content = Template(template_str).render(
        project_name=project_name, email=email_to
    )
    return EmailData(html_content=html_content, subject=subject)
