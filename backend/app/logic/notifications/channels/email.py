"""Email notification channel using aiosmtplib."""

import html
from collections.abc import Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from app.core.config import settings
from app.core.logger import get_logger
from app.logic.notifications.channels.base import (
    NotificationChannel,
    is_undeliverable,
)
from app.logic.notifications.messages import get_email_strings
from app.models.user import User
from app.schemas.notification import NotificationData

logger = get_logger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "email-templates" / "build"


@dataclass(frozen=True)
class EmailBody:
    """A notification mail written for one recipient: plain text and HTML.

    Most notices go out as the generic mail (title, body, one button), batched
    per language. A type whose design asks for more, a greeting by name or a
    block of details, renders this per recipient and hands the renderer to
    ``NotificationService.notify(email_body=...)``. The subject stays the
    notification title either way.
    """

    text: str
    html: str


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
        if is_undeliverable(recipient):
            logger.debug(f"Skipping email for placeholder account {recipient.id}")
            return False
        return True

    async def send(
        self,
        *,
        recipient: User,
        title: str,
        body: str,
        data: NotificationData | None = None,
        content: EmailBody | None = None,
    ) -> bool:
        """Send one mail; ``content`` replaces the generic text and HTML."""
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
                content=content,
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
        content: EmailBody | None = None,
    ) -> EmailMessage:
        if content is None:
            content = EmailBody(
                text=body,
                html=_build_html(title=title, body=body, data=data, language=language),
            )
        from_name = settings.EMAILS_FROM_NAME or settings.PROJECT_NAME
        from_email = settings.EMAILS_FROM_EMAIL or "noreply@example.com"

        msg = EmailMessage()
        msg["Subject"] = subject_line(title)
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to
        msg.set_content(content.text)
        msg.add_alternative(content.html, subtype="html")
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


def subject_line(title: str) -> str:
    """A mail's subject: its title, on one line.

    No "[WirkSam]" in front: the approved mail designs leave it out, as the
    sender's name already says who writes. A title can carry names people
    typed, and a line break in a header is refused outright, so whitespace
    runs collapse to one space.
    """
    return " ".join(title.split())


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
        if "token" in data:
            # An invitation: ``/invite/{token}`` works before the person
            # belongs to the event, where the event's page is a 404 to them
            # while the event is private.
            action_link = f"{frontend_url}/invite/{data['token']}"
        elif "task_id" in data:
            action_link = f"{frontend_url}/app/tasks/{data['task_id']}"
        elif "team_id" in data and "event_id" in data:
            # A team request or decision: the Teams page, on that team.
            action_link = (
                f"{frontend_url}/app/teams/{data['event_id']}?team={data['team_id']}"
            )
        elif "user_id" in data and "event_id" in data:
            # A join request or an accepted invitation: the People tab, where
            # the request is decided and the newcomer shows up.
            action_link = (
                f"{frontend_url}/app/event-settings/{data['event_id']}?tab=people"
            )
        elif "event_id" in data:
            # ``/app/events/{id}`` is not a route: the Vue router has
            # ``events`` (the list), ``events/create`` and
            # ``event-settings/:eventId?``, so an id appended to the list path
            # fell through the catch-all to not-found. This is where the in-app
            # notification handler sends the same payload.
            action_link = f"{frontend_url}/app/event-settings/{data['event_id']}"

    action_html = ""
    if action_link:
        action_html = button_html(action_link, email_strings["view_details"])

    # Title and body carry user-supplied text — event and task names, and now a
    # free-text note an event admin types when cloning. ``paragraphs_html``
    # escapes before it turns newlines into line breaks, the one piece of
    # markup this template wants. (``_card`` escapes the title.)
    content = f"{paragraphs_html([body])}{action_html}"
    return _card(title=title, content=content, language=language)


# ── The shared frame ──────────────────────────────────────────────
#
# Every mail the product sends wears this: notifications, the "you're in
# charge" mail, the invitation to an address without an account and the auth
# mails. The colours are the app's light palette, the tokens in
# ``frontend/src/index.css`` written out as hex, because mail clients read
# neither oklch() nor CSS variables. The markup is mail-safe: tables for
# layout, inline styles only, nothing to fetch but the logo.

#: ``--background``: around the card, and the footer band.
_BACKGROUND = "#f3ece0"
#: ``--foreground``
_FOREGROUND = "#2b2521"
#: ``--card``
_CARD = "#f8f3e9"
#: ``--border``
_BORDER = "#ddd3c2"
#: ``--primary``: the header, the button and links.
_PRIMARY = "#2d522f"
#: ``--primary-foreground``
_PRIMARY_FOREGROUND = "#f8f3e9"
#: ``--muted``: the block of facts.
_MUTED = "#eae0d1"
#: ``--muted-foreground``: labels, notes, the footer.
_MUTED_FOREGROUND = "#554f48"
#: ``--accent``: the inviter's round badge.
_ACCENT = "#f4d7c8"
#: ``--hero-speck`` at its 20 %: the sun on the header, as on the dashboard.
_SPECK = "rgba(227, 163, 64, 0.2)"
_SPECK_EDGE = "rgba(227, 163, 64, 0)"

#: Tailwind's ``font-sans``, the app's type.
_FONT = (
    "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif"
)
#: Body copy.
_TEXT = f"font-size: 15px; line-height: 1.55; color: {_FOREGROUND};"
#: Small print under the button.
_SMALL = f"font-size: 13px; line-height: 1.5; color: {_MUTED_FOREGROUND};"


def paragraphs_html(paragraphs: Sequence[str], *, first_margin: int = 14) -> str:
    """Body paragraphs, the first ``first_margin`` px under the heading and
    the rest 8 px apart. Escapes each, then makes a newline a line break."""
    return "".join(
        f"""
                    <p style="{_TEXT} margin: {first_margin if i == 0 else 8}px 0 0;">{_lines(text)}</p>"""
        for i, text in enumerate(paragraphs)
    )


def _lines(text: str) -> str:
    """``text`` escaped, its newlines as ``<br>``: in that order, or the
    escape would turn the breaks into visible ``&lt;br&gt;``."""
    return html.escape(text).replace("\n", "<br>")


def build_details_html(
    *,
    title: str,
    language: str,
    paragraphs: Sequence[str],
    details: Sequence[tuple[str, str]],
    list_heading: str,
    items: Sequence[str],
    action_url: str,
    action_label: str,
    note: str,
) -> str:
    """A notification mail with more to say than one paragraph.

    Top to bottom: the opening lines (a greeting, who did what), a block of
    label/value facts, a short list under a heading, one button and a small
    closing note: the layout of the "you're in charge" design. Every argument
    is plain text and escaped here; an empty ``details``, ``items`` or ``note``
    leaves its part out.
    """
    list_html = ""
    if items:
        entries = "".join(
            f"""
                        <li style="margin: 0 0 2px;">{html.escape(item)}</li>"""
            for item in items
        )
        list_html = f"""
                    <p style="{_TEXT} margin: 20px 0 6px; font-weight: 700;">{html.escape(list_heading)}</p>
                    <ul style="{_TEXT} margin: 0; padding-left: 20px;">{entries}
                    </ul>"""

    content = (
        paragraphs_html(paragraphs)
        + details_table_html(details)
        + list_html
        + button_html(action_url, action_label)
        + (small_print_html(note) if note else "")
    )
    return _card(title=title, content=content, language=language)


def details_table_html(
    details: Sequence[tuple[str, str]], *, label_width: int = 150
) -> str:
    """A block of label/value facts; empty for no details. Escapes both.

    A table, not the design's grid: mail clients keep a table's columns.
    ``label_width`` is the column the design gives the labels; on a narrow
    phone it gives way, down to the longest label, which never wraps.
    """
    if not details:
        return ""
    rows = "".join(
        f"""
                                <tr>
                                    <td style="width: {label_width}px; padding: 4px 16px 4px 0; white-space: nowrap; color: {_MUTED_FOREGROUND}; vertical-align: top;">{html.escape(label)}</td>
                                    <td style="padding: 4px 0; font-weight: 600; color: {_FOREGROUND}; vertical-align: top;">{html.escape(value)}</td>
                                </tr>"""
        for label, value in details
    )
    return f"""
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                           style="margin: 20px 0 0; border-collapse: separate; background-color: {_MUTED}; border-radius: 14px;">
                        <tr>
                            <td style="padding: 12px 18px;">
                                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                                       style="font-size: 14px; line-height: 1.5;">{rows}
                                </table>
                            </td>
                        </tr>
                    </table>"""


def heading_html(text: str, *, margin_top: int = 0) -> str:
    """The mail's one heading, as the design sets it. Escapes ``text``."""
    return f"""
                    <h1 style="margin: {margin_top}px 0 0; font-size: 24px; line-height: 1.25; font-weight: 700; color: {_FOREGROUND};">{html.escape(text)}</h1>"""


def button_html(url: str, label: str) -> str:
    """The one call to action, centred, 26 px under what is above it.

    A table cell carries the colour too, so it stays a button in clients that
    drop padding on links (Outlook). Escapes both.
    """
    return f"""
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                        <tr>
                            <td align="center" style="padding-top: 26px;">
                                <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                                    <tr>
                                        <td align="center" bgcolor="{_PRIMARY}" style="border-radius: 12px; background-color: {_PRIMARY};">
                                            <a href="{html.escape(url)}"
                                               style="display: inline-block; padding: 14px 28px; border-radius: 12px; background-color: {_PRIMARY};
                                                      color: {_PRIMARY_FOREGROUND}; font-family: {_FONT}; font-size: 15px; font-weight: 700;
                                                      line-height: 1.2; text-decoration: none;">{html.escape(label)}</a>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>"""


def link_fallback_html(url: str, intro: str) -> str:
    """The button's link written out, for clients that strip the button.

    Kept beside every button that carries a token (auth mails, the
    invitation), which a reader must be able to reach. Escapes both.
    """
    safe_url = html.escape(url)
    return f"""
                    <p style="margin: 16px 0 0; font-size: 12px; line-height: 1.5; color: {_MUTED_FOREGROUND};">
                        {html.escape(intro)}<br />
                        <a href="{safe_url}" style="color: {_PRIMARY}; word-break: break-all;">{safe_url}</a>
                    </p>"""


def text_link_html(url: str, label: str) -> str:
    """A link inside a sentence, bold in the primary green. Escapes both."""
    return (
        f'<a href="{html.escape(url)}" style="color: {_PRIMARY}; font-weight: 700;">'
        f"{html.escape(label)}</a>"
    )


def avatar_row_html(*, initials: str, name: str, subline: str) -> str:
    """Who a mail comes from: a round badge, the name, a line under it.

    The invitation opens with it. Escapes all three.
    """
    return f"""
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                        <tr>
                            <td width="44" height="44" align="center" valign="middle"
                                style="width: 44px; height: 44px; border-radius: 22px; background-color: {_ACCENT};
                                       font-size: 15px; font-weight: 700; color: {_FOREGROUND};">{html.escape(initials)}</td>
                            <td style="padding-left: 12px; font-size: 14px; line-height: 1.45; color: {_MUTED_FOREGROUND};">
                                <strong style="color: {_FOREGROUND};">{html.escape(name)}</strong><br />{html.escape(subline)}
                            </td>
                        </tr>
                    </table>"""


def small_print_html(text: str, *, margin_top: int = 22) -> str:
    """A note under the button ("Doesn't suit you? …"). Escapes ``text``."""
    return f"""
                    <p style="{_SMALL} margin: {margin_top}px 0 0;">{html.escape(text)}</p>"""


def quiet_html(inner: str, *, margin_top: int = 18, center: bool = False) -> str:
    """A 14 px paragraph in the quieter colour, around HTML already escaped."""
    align = " text-align: center;" if center else ""
    return f"""
                    <p style="margin: {margin_top}px 0 0; font-size: 14px; line-height: 1.55; color: {_MUTED_FOREGROUND};{align}">{inner}</p>"""


def card_html(
    *,
    title: str,
    content: str,
    language: str,
    footer_text: str,
    show_title: bool = True,
) -> str:
    """The shared mail frame, for a mail that is not a notification.

    Same header and card as every notification, but the footer says
    ``footer_text`` (plain, escaped here) instead of pointing at notification
    settings the recipient may not have. ``show_title`` False leaves the
    heading to ``content``, for a layout that puts something above it.
    """
    footer = f"""
                                <p style="margin: 0; font-size: 12px; line-height: 1.5; color: {_MUTED_FOREGROUND};">{html.escape(footer_text)}</p>"""
    return _card(
        title=title,
        content=content,
        language=language,
        footer_html=footer,
        show_title=show_title,
    )


def _card(
    *,
    title: str,
    content: str,
    language: str,
    footer_html: str | None = None,
    show_title: bool = True,
) -> str:
    """The frame every mail shares around ``content``.

    The green header with the app's mark and name, the title as the heading,
    and the footer that links to the notification settings (or
    ``footer_html``, for ``card_html``). ``title`` is escaped here;
    ``content`` and ``footer_html`` are HTML their builder has already
    escaped.
    """
    frontend_url = settings.FRONTEND_HOST
    email_strings = get_email_strings(language)
    # A PNG, not the app's SVG logo: Gmail and Outlook show no SVG in a mail.
    # Its alt is empty because the name stands right beside it.
    logo_url = f"{frontend_url}/icons/icon-192.png"
    preferences_url = f"{frontend_url}/app/settings/notifications"
    heading = heading_html(title) if show_title else ""
    if footer_html is None:
        footer_html = f"""
                                <p style="margin: 0; font-size: 12px; line-height: 1.5; color: {_MUTED_FOREGROUND};">
                                    {email_strings["footer_text"]}<br />
                                    <a href="{preferences_url}" style="color: {_PRIMARY}; text-decoration: underline;">{email_strings["manage_preferences"]}</a>
                                </p>"""

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="color-scheme" content="light" />
    <meta name="supported-color-schemes" content="light" />
    <title>{html.escape(title)}</title>
</head>
<body style="margin: 0; padding: 0; background-color: {_BACKGROUND}; color: {_FOREGROUND}; font-family: {_FONT};">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{_BACKGROUND}"
           style="background-color: {_BACKGROUND};">
        <tr>
            <td align="center" style="padding: 32px 12px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                       style="max-width: 560px; border-collapse: separate; background-color: {_CARD};
                              border: 1px solid {_BORDER}; border-radius: 18px; font-family: {_FONT};">
                    <!-- Header: the app's mark on a cream tile and its name. The
                         sun is the dashboard hero's; a client without CSS
                         gradients keeps the plain green. -->
                    <tr>
                        <td bgcolor="{_PRIMARY}"
                            style="padding: 20px 28px; border-radius: 17px 17px 0 0; background-color: {_PRIMARY};
                                   background-image: radial-gradient(circle at right 30px top 20px, {_SPECK} 0, {_SPECK} 60px, {_SPECK_EDGE} 61px);">
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td width="30" height="30" align="center" valign="middle"
                                        style="width: 30px; height: 30px; border-radius: 8px; background-color: {_PRIMARY_FOREGROUND}; line-height: 0;">
                                        <img src="{logo_url}" width="22" height="22" alt=""
                                             style="display: inline-block; width: 22px; height: 22px; border: 0;" />
                                    </td>
                                    <td style="padding-left: 10px; font-size: 17px; font-weight: 700; line-height: 1.2; color: {_PRIMARY_FOREGROUND};">{html.escape(settings.PROJECT_NAME)}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <!-- Body -->
                    <tr>
                        <td style="padding: 28px; {_TEXT}">{heading}{content}
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td align="center" bgcolor="{_BACKGROUND}"
                            style="padding: 16px 28px; border-top: 1px solid {_BORDER}; border-radius: 0 0 17px 17px;
                                   background-color: {_BACKGROUND}; text-align: center;">{footer_html}
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
