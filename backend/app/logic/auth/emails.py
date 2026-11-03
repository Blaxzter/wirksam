"""Transactional authentication mail: address verification and password reset.

These two messages deliberately do **not** go through ``NotificationService``.
That service exists for product notifications: it needs a seeded
``NotificationType`` row before it will deliver anything, it writes an in-app
``Notification`` alongside the mail, and it filters every delivery through the
recipient's per-channel preferences — so a user who turned email notifications
off would never receive a password reset. It also merges recipients into one
BCC message built from the *first* recipient's body, which is harmless for an
announcement and catastrophic for a message carrying a one-time token.

So this module owns a thin path of its own to SMTP: render the same card the
notification channel renders, hand the message to aiosmtplib, and never raise.
Both entry points return ``bool`` so the caller can log the outcome; neither
lets a mail failure surface as an HTTP error, because "we could not reach the
mail server" is not something a registering user can act on.

That path is ``send_action_mail``, which the invitation mail to an address
without an account (``logic/invitation_emails.py``) uses too: there is no
account there to notify at all.
"""

from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings
from app.core.logger import get_logger
from app.logic.notifications.channels.email import (
    button_html,
    card_html,
    link_fallback_html,
    paragraphs_html,
    subject_line,
)
from app.logic.notifications.messages import (
    DEFAULT_LANGUAGE,
    get_email_strings,
    get_message,
)

logger = get_logger(__name__)


# ── Public API ────────────────────────────────────────────────────


async def send_verify_email(
    *, email: str, name: str | None, token: str, language: str
) -> bool:
    """Send the "confirm your address" mail; True when SMTP accepted it."""
    return await _send_action_email(
        email=email,
        name=name,
        language=language,
        message_code="auth.verify_email",
        action_path=f"/verify-email?token={token}",
        action_label_key="verify_cta",
        expires_in_hours=settings.EMAIL_VERIFY_TOKEN_EXPIRE_HOURS,
    )


async def send_password_reset_email(
    *, email: str, name: str | None, token: str, language: str
) -> bool:
    """Send the "set a new password" mail; True when SMTP accepted it."""
    return await _send_action_email(
        email=email,
        name=name,
        language=language,
        message_code="auth.reset_password",
        action_path=f"/reset-password?token={token}",
        action_label_key="reset_cta",
        expires_in_hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
    )


# ── Delivery ──────────────────────────────────────────────────────


async def _send_action_email(
    *,
    email: str,
    name: str | None,
    language: str,
    message_code: str,
    action_path: str,
    action_label_key: str,
    expires_in_hours: int,
) -> bool:
    """Render and send one token-bearing mail with a single call to action."""
    # FRONTEND_HOST is the one server-side base URL and never carries a
    # trailing slash; nothing in the codebase normalises one away, so every
    # action_path starts with "/".
    action_url = f"{settings.FRONTEND_HOST}{action_path}"
    try:
        action_label = _chrome(language, action_label_key)
        title, body = get_message(
            message_code,
            language,
            project_name=settings.PROJECT_NAME,
            expires_in=_expiry_phrase(expires_in_hours, language),
        )
        opening = f"{_greeting(name, language)}\n\n{body}"
        text_body = f"{opening}\n\n{action_label}:\n{action_url}"
        footer = _chrome(language, "transactional_footer")
        # The HTML part says the link once, as the button (and the fallback
        # under it), not also as the plain text's "label: link" line.
        html_body = _build_auth_html(
            title=title,
            body=opening,
            action_url=action_url,
            action_label=action_label,
            language=language,
            footer=footer,
        )
    except Exception:
        logger.exception(f"Failed to render the {message_code} email for {email}")
        return False
    return await send_action_mail(
        to=email,
        language=language,
        title=title,
        text_body=text_body,
        action_url=action_url,
        action_label=action_label,
        footer=footer,
        kind=message_code,
        html_body=html_body,
    )


async def send_action_mail(
    *,
    to: str,
    language: str,
    title: str,
    text_body: str,
    action_url: str,
    action_label: str,
    footer: str,
    kind: str,
    html_body: str | None = None,
    from_name: str | None = None,
) -> bool:
    """Send one transactional mail with a single call to action; never raise.

    Shared by the auth mails here and the invitation mail to an address
    without an account (``logic/invitation_emails.py``): mail that must reach
    someone whatever their notification settings say, or who has no account
    to have settings. ``text_body`` is the plain-text part. The HTML part is
    the transactional card around it, closing with ``footer``, unless the
    caller wrote its own (``html_body``). ``from_name`` replaces the sender's
    display name (the address stays ours). ``kind`` names the mail in the log.

    True when SMTP accepted it. Without SMTP the link is logged instead.
    """
    # Gate on emails_configured alone — deliberately *not* on
    # settings.emails_enabled. That flag is `ENVIRONMENT != "local"`, and both
    # local development and the e2e compose stack run ENVIRONMENT=local.
    # Honouring it here would mean the mailcatcher container on port 1025 never
    # receives a verification mail and nobody could finish a registration
    # outside production, while the code kept reporting success.
    if not settings.emails_configured:
        # There is no way to complete the flow from the UI without the mail, so
        # put the link where whoever is running the stack will find it. In
        # every deployed environment SMTP *is* configured and this branch never
        # runs, which is what keeps one-time tokens out of production logs.
        logger.warning(
            f"SMTP is not configured (SMTP_HOST/EMAILS_FROM_EMAIL); the "
            f"{kind} mail for {to} was not sent. "
            f"Continue the flow with this link: {action_url}"
        )
        return False

    try:
        message = _build_message(
            to=to,
            title=title,
            text_body=text_body,
            html_body=html_body
            or _build_auth_html(
                title=title,
                body=text_body,
                action_url=action_url,
                action_label=action_label,
                language=language,
                footer=footer,
            ),
            from_name=from_name,
        )
        await _smtp_send(message)
        logger.info(f"Sent {kind} email to {to}")
        return True

    except Exception:
        logger.exception(f"Failed to send {kind} email to {to}")
        return False


def _build_message(
    *,
    to: str,
    title: str,
    text_body: str,
    html_body: str,
    from_name: str | None = None,
) -> EmailMessage:
    """Assemble the multipart message, headers included."""
    sender = from_name or settings.EMAILS_FROM_NAME or settings.PROJECT_NAME
    from_email = settings.EMAILS_FROM_EMAIL or "noreply@example.com"

    msg = EmailMessage()
    msg["Subject"] = subject_line(title)
    # formataddr quotes a display name with a comma or an "@" in it, which a
    # name a person typed (``from_name``) may well have.
    msg["From"] = formataddr((sender, from_email))
    msg["To"] = to
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    return msg


async def _smtp_send(msg: EmailMessage) -> None:
    """Hand the message to aiosmtplib, imported lazily as the channel does."""
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


# ── Localised fragments ───────────────────────────────────────────


def _chrome(language: str, key: str) -> str:
    """Return one shared email-chrome string, falling back to English per key.

    ``get_email_strings`` falls back to English only when a locale file has no
    "email" block at all — not when a single key inside one is missing. The
    pre-commit hook only covers ``frontend/src/locales``; the backend files are
    checked by ``tests/logic/test_notification_locales.py``. Should a key in
    en.json still be missing from de.json, it would raise ``KeyError`` here,
    which the caller swallows as "sending failed": the reset mail would simply
    never arrive for German users. Degrade to the English wording instead.
    """
    strings = get_email_strings(language)
    if key in strings:
        return strings[key]
    return get_email_strings(DEFAULT_LANGUAGE).get(key, "")


def _greeting(name: str | None, language: str) -> str:
    """Return the salutation line, personalised when a name is known."""
    if name:
        return _chrome(language, "greeting").format(name=name)
    return _chrome(language, "greeting_no_name")


def _expiry_phrase(hours: int, language: str) -> str:
    """Render a token lifetime as prose: "1 hour", "48 Stunden".

    The locale files carry no plural machinery, and the two lifetimes sit on
    either side of the boundary — a reset link lives one hour, a verification
    link 48 — so the form is chosen here. Without it every password-reset mail
    would read "expires in 1 hours".
    """
    key = "expiry_hour" if hours == 1 else "expiry_hours"
    return _chrome(language, key).format(hours=hours)


# ── HTML shell ────────────────────────────────────────────────────


def _build_auth_html(
    *,
    title: str,
    body: str,
    action_url: str,
    action_label: str,
    language: str,
    footer: str | None = None,
) -> str:
    """Render the transactional card: the shared frame, no preferences link.

    The frame is the one every mail wears (``card_html`` in the notification
    e-mail channel), but not the notification body inside it: that renderer
    derives its call to action from a notification payload (a task or an
    event id) and always closes with "you received this because of your
    notification settings" above a link to the preferences page. Neither is
    true of a security mail, and sending a logged-out recipient to a settings
    page in the middle of a password reset is worse than useless.

    ``body`` is plain text: a blank line starts a paragraph, a single newline
    breaks the line. It carries a display name the account holder chose, so
    everything is escaped. ``footer`` is plain text too; it defaults to the
    auth mails' "it was requested for this address".
    """
    paragraphs = [part for part in body.split("\n\n") if part.strip()]
    content = (
        paragraphs_html(paragraphs)
        + button_html(action_url, action_label)
        # Mail clients that strip the button still have to leave a way to
        # reach the link, so it is written out once more.
        + link_fallback_html(action_url, _chrome(language, "action_url_fallback"))
    )
    return card_html(
        title=title,
        content=content,
        language=language,
        footer_text=(
            footer if footer is not None else _chrome(language, "transactional_footer")
        ),
    )
