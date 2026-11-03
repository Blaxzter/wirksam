"""Unit tests for the transactional authentication emails.

The SMTP transport is replaced by an ``AsyncMock`` in every test, so nothing
here opens a socket, and the settings that decide whether mail is sent at all
are driven through their real inputs rather than by patching the computed
properties those inputs feed.

Two behaviours are load-bearing enough to have a test of their own: that a
verification mail is still sent when ``ENVIRONMENT=local`` (the notification
channel deliberately goes quiet there, which would make registration
impossible to complete against mailcatcher), and that neither mail carries the
notification-preferences footer.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from email.message import EmailMessage
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.logic.auth.emails import (
    _build_auth_html,  # type: ignore[reportPrivateUsage]
    _chrome,  # type: ignore[reportPrivateUsage]
    send_password_reset_email,
    send_verify_email,
)

TRANSPORT = "app.logic.auth.emails._smtp_send"


# ── Helpers ───────────────────────────────────────────────────────


@contextmanager
def _email_settings(
    *,
    enabled: bool = True,
    configured: bool = True,
    from_name: str | None = "Wirksam Test Sender",
    verify_hours: int = 48,
    reset_hours: int = 1,
) -> Generator[None, None, None]:
    """Drive ``emails_enabled``/``emails_configured`` through their real inputs."""
    with (
        patch.object(settings, "PROJECT_NAME", "Wirksam Test"),
        patch.object(settings, "ENVIRONMENT", "production" if enabled else "local"),
        patch.object(
            settings, "SMTP_HOST", "smtp.example.test" if configured else None
        ),
        patch.object(settings, "SMTP_PORT", 2525),
        patch.object(settings, "SMTP_USER", "smtp-user"),
        patch.object(settings, "SMTP_PASSWORD", "smtp-password"),
        patch.object(settings, "SMTP_TLS", True),
        patch.object(settings, "SMTP_SSL", False),
        patch.object(
            settings,
            "EMAILS_FROM_EMAIL",
            "sender@example.test" if configured else None,
        ),
        patch.object(settings, "EMAILS_FROM_NAME", from_name),
        patch.object(settings, "FRONTEND_HOST", "https://app.example.test"),
        patch.object(settings, "EMAIL_VERIFY_TOKEN_EXPIRE_HOURS", verify_hours),
        patch.object(settings, "EMAIL_RESET_TOKEN_EXPIRE_HOURS", reset_hours),
    ):
        yield


def _sent_message(smtp: AsyncMock) -> EmailMessage:
    """Return the single message handed to the mocked transport."""
    smtp.assert_awaited_once()
    call = smtp.await_args
    assert call is not None
    # ``isinstance`` would narrow to EmailMessage[Unknown, Unknown] — the class
    # is generic over its header types — which basedpyright rejects as a
    # partially unknown return type, so name the type instead.
    return cast(EmailMessage, call.args[0])


def _part(message: EmailMessage, subtype: str) -> str:
    """Return the decoded text of the ``plain`` or ``html`` alternative."""
    part = message.get_body(preferencelist=(subtype,))
    assert part is not None
    content = part.get_content()
    assert isinstance(content, str)
    return content


# ── Verification mail ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestSendVerifyEmail:
    """Test suite for send_verify_email."""

    async def test_carries_the_absolute_verification_link(self) -> None:
        """Test that both alternatives contain the tokenised frontend link."""
        with (
            _email_settings(),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
        ):
            result = await send_verify_email(
                email="new@example.test",
                name="Ada",
                token="verify-token-123",
                language="en",
            )

        assert result is True
        message = _sent_message(smtp)
        link = "https://app.example.test/verify-email?token=verify-token-123"
        assert link in _part(message, "plain")
        # In the HTML part only as the button and the fallback link (its href
        # and its text), not again as the plain text's "Confirm email:" line.
        html = _part(message, "html")
        assert html.count(link) == 3
        assert "Confirm email:" not in html

    async def test_is_still_sent_in_the_local_environment(self) -> None:
        """Test that ENVIRONMENT=local does not suppress the mail."""
        # EmailChannel treats `emails_enabled` (ENVIRONMENT != "local") as a
        # kill switch and reports success without sending. Auth mail must not:
        # local development and the e2e stack both run ENVIRONMENT=local and
        # both point SMTP at mailcatcher, so honouring that flag here would
        # make it impossible to finish a registration anywhere but production.
        with (
            _email_settings(enabled=False),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
        ):
            result = await send_verify_email(
                email="new@example.test", name="Ada", token="tok", language="en"
            )

        assert result is True
        smtp.assert_awaited_once()

    async def test_headers_name_the_recipient_and_the_sender(self) -> None:
        """Test the Subject, From and To headers of the built message."""
        with (
            _email_settings(),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
        ):
            await send_verify_email(
                email="new@example.test", name="Ada", token="tok", language="en"
            )

        message = _sent_message(smtp)
        assert message["To"] == "new@example.test"
        assert message["Subject"] == "[Wirksam Test] Confirm your email address"
        assert message["From"] == "Wirksam Test Sender <sender@example.test>"

    async def test_greets_the_recipient_by_name(self) -> None:
        """Test that a known display name opens the message."""
        with (
            _email_settings(),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
        ):
            await send_verify_email(
                email="new@example.test", name="Ada", token="tok", language="en"
            )

        assert "Hi Ada," in _part(_sent_message(smtp), "plain")

    async def test_falls_back_to_a_nameless_greeting(self) -> None:
        """Test that a missing name yields a greeting without a dangling comma."""
        with (
            _email_settings(),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
        ):
            await send_verify_email(
                email="new@example.test", name=None, token="tok", language="en"
            )

        text = _part(_sent_message(smtp), "plain")
        assert text.startswith("Hi,")
        assert "Hi ," not in text

    async def test_display_name_is_escaped_in_the_html_part(self) -> None:
        """Test that a name containing markup cannot rewrite the message."""
        with (
            _email_settings(),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
        ):
            await send_verify_email(
                email="new@example.test",
                name="<b>Ada</b>",
                token="tok",
                language="en",
            )

        html = _part(_sent_message(smtp), "html")
        assert "&lt;b&gt;Ada&lt;/b&gt;" in html
        assert "<b>Ada</b>" not in html

    async def test_pluralises_the_expiry_window(self) -> None:
        """Test that a 48-hour lifetime is rendered in the plural."""
        with (
            _email_settings(verify_hours=48),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
        ):
            await send_verify_email(
                email="new@example.test", name="Ada", token="tok", language="en"
            )

        assert "expires in 48 hours" in _part(_sent_message(smtp), "plain")

    async def test_german_recipient_gets_german_copy(self) -> None:
        """Test that the language selects both the body and the button label."""
        with (
            _email_settings(),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
        ):
            await send_verify_email(
                email="neu@example.test", name="Ada", token="tok", language="de"
            )

        message = _sent_message(smtp)
        assert message["Subject"] == "[Wirksam Test] Bestätige deine E-Mail-Adresse"
        html = _part(message, "html")
        assert "Hallo Ada," in html
        assert "E-Mail bestätigen" in html
        assert "48 Stunden" in html
        assert "Confirm email" not in html

    async def test_unconfigured_smtp_logs_the_link_and_reports_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that a missing SMTP host leaves the link in the log instead."""
        with (
            _email_settings(configured=False),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
            caplog.at_level(logging.WARNING, logger="app.logic.auth.emails"),
        ):
            result = await send_verify_email(
                email="new@example.test",
                name="Ada",
                token="verify-token-123",
                language="en",
            )

        assert result is False
        smtp.assert_not_awaited()
        assert any(
            "https://app.example.test/verify-email?token=verify-token-123"
            in record.message
            for record in caplog.records
        )

    async def test_transport_failure_is_contained(self) -> None:
        """Test that an unreachable mail server is reported, never raised."""
        with (
            _email_settings(),
            patch(
                TRANSPORT,
                new_callable=AsyncMock,
                side_effect=OSError("smtp server unreachable"),
            ) as smtp,
        ):
            result = await send_verify_email(
                email="new@example.test", name="Ada", token="tok", language="en"
            )

        assert result is False
        smtp.assert_awaited_once()

    async def test_forwards_the_configured_smtp_parameters(self) -> None:
        """Test that the real transport is called with the SMTP settings."""
        with (
            _email_settings(),
            patch("aiosmtplib.send", new_callable=AsyncMock) as aiosmtp,
        ):
            result = await send_verify_email(
                email="new@example.test", name="Ada", token="tok", language="en"
            )

        assert result is True
        aiosmtp.assert_awaited_once()
        call = aiosmtp.await_args
        assert call is not None
        assert call.kwargs["hostname"] == "smtp.example.test"
        assert call.kwargs["port"] == 2525
        assert call.kwargs["username"] == "smtp-user"
        assert call.kwargs["password"] == "smtp-password"
        assert call.kwargs["start_tls"] is True
        assert call.kwargs["use_tls"] is False

    async def test_sender_name_falls_back_to_the_project_name(self) -> None:
        """Test that a missing EMAILS_FROM_NAME falls back to PROJECT_NAME."""
        with (
            _email_settings(from_name=None),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
        ):
            await send_verify_email(
                email="new@example.test", name="Ada", token="tok", language="en"
            )

        assert _sent_message(smtp)["From"] == "Wirksam Test <sender@example.test>"


# ── Password-reset mail ───────────────────────────────────────────


@pytest.mark.asyncio
class TestSendPasswordResetEmail:
    """Test suite for send_password_reset_email."""

    async def test_carries_the_absolute_reset_link(self) -> None:
        """Test that both alternatives contain the tokenised frontend link."""
        with (
            _email_settings(),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
        ):
            result = await send_password_reset_email(
                email="user@example.test",
                name="Ada",
                token="reset-token-456",
                language="en",
            )

        assert result is True
        message = _sent_message(smtp)
        link = "https://app.example.test/reset-password?token=reset-token-456"
        assert link in _part(message, "plain")
        assert link in _part(message, "html")
        assert message["Subject"] == "[Wirksam Test] Reset your password"

    async def test_single_hour_expiry_is_not_pluralised(self) -> None:
        """Test that the one-hour default reads as "1 hour", not "1 hours"."""
        with (
            _email_settings(reset_hours=1),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
        ):
            await send_password_reset_email(
                email="user@example.test", name="Ada", token="tok", language="en"
            )

        text = _part(_sent_message(smtp), "plain")
        assert "expires in 1 hour." in text
        assert "1 hours" not in text

    async def test_german_copy_uses_the_singular_hour(self) -> None:
        """Test that the German mail is localised down to the plural form."""
        with (
            _email_settings(reset_hours=1),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
        ):
            await send_password_reset_email(
                email="user@example.test", name="Ada", token="tok", language="de"
            )

        html = _part(_sent_message(smtp), "html")
        assert "Neues Passwort setzen" in html
        assert "1 Stunde gültig" in html

    async def test_never_offers_notification_preferences(self) -> None:
        """Test that a security mail does not link to the preferences page."""
        # Routed through NotificationService this mail would end in "you
        # received this because of your notification settings" plus a link to a
        # page a logged-out recipient cannot reach — and could be suppressed
        # by the very preference that footer advertises.
        with (
            _email_settings(),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
        ):
            await send_password_reset_email(
                email="user@example.test", name="Ada", token="tok", language="en"
            )

        html = _part(_sent_message(smtp), "html")
        assert "/app/settings/notifications" not in html
        assert "Manage preferences" not in html
        assert "notification settings" not in html

    async def test_unconfigured_smtp_logs_the_link_and_reports_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that a missing SMTP host leaves the link in the log instead."""
        with (
            _email_settings(configured=False),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
            caplog.at_level(logging.WARNING, logger="app.logic.auth.emails"),
        ):
            result = await send_password_reset_email(
                email="user@example.test",
                name="Ada",
                token="reset-token-456",
                language="en",
            )

        assert result is False
        smtp.assert_not_awaited()
        assert any(
            "https://app.example.test/reset-password?token=reset-token-456"
            in record.message
            for record in caplog.records
        )

    async def test_transport_failure_is_contained(self) -> None:
        """Test that a failing mail server never breaks the calling flow."""
        with (
            _email_settings(),
            patch(
                TRANSPORT,
                new_callable=AsyncMock,
                side_effect=ConnectionRefusedError("connection refused"),
            ),
        ):
            result = await send_password_reset_email(
                email="user@example.test", name="Ada", token="tok", language="en"
            )

        assert result is False


# ── HTML shell ────────────────────────────────────────────────────


class TestAuthEmailHtml:
    """Test suite for the _build_auth_html template helper."""

    def test_renders_the_action_button_and_a_copyable_link(self) -> None:
        """Test that the link appears both as a button and as visible text."""
        with _email_settings():
            html = _build_auth_html(
                title="T",
                body="B",
                action_url="https://app.example.test/verify-email?token=abc",
                action_label="Confirm email",
                language="en",
            )

        # Three times: the button's href, the fallback link's href, and the
        # fallback link's visible text.
        assert html.count("https://app.example.test/verify-email?token=abc") == 3
        assert "Confirm email" in html
        assert "If the button does not work" in html

    def test_carries_the_brand_header(self) -> None:
        """Test that the card keeps the shared logo and project name.

        The logo is the PNG app icon: Gmail and Outlook show no SVG.
        """
        with _email_settings():
            html = _build_auth_html(
                title="T",
                body="B",
                action_url="https://app.example.test/verify-email?token=abc",
                action_label="Confirm email",
                language="en",
            )

        assert "https://app.example.test/icons/icon-192.png" in html
        assert "icon.svg" not in html
        assert "Wirksam Test" in html

    def test_a_blank_line_starts_a_paragraph(self) -> None:
        """Test that the greeting and the message are paragraphs of their own."""
        with _email_settings():
            html = _build_auth_html(
                title="T",
                body="Hi Ada,\n\nPlease confirm.",
                action_url="https://app.example.test/verify-email?token=abc",
                action_label="Confirm email",
                language="en",
            )

        assert ">Hi Ada,</p>" in html
        assert ">Please confirm.</p>" in html

    def test_newlines_become_line_breaks(self) -> None:
        """Test that plain-text newlines survive into the HTML alternative."""
        with _email_settings():
            html = _build_auth_html(
                title="T",
                body="Line one\nLine two",
                action_url="https://app.example.test/verify-email?token=abc",
                action_label="Confirm email",
                language="en",
            )

        assert "Line one<br>Line two" in html

    def test_unknown_language_falls_back_to_english_chrome(self) -> None:
        """Test that an unsupported language still renders English strings."""
        with _email_settings():
            html = _build_auth_html(
                title="T",
                body="B",
                action_url="https://app.example.test/verify-email?token=abc",
                action_label="Confirm email",
                language="xx",
            )

        assert '<html lang="xx">' in html
        assert "If the button does not work" in html


class TestEmailChrome:
    """Test suite for the per-key locale fallback."""

    def test_returns_the_localised_string(self) -> None:
        """Test that a key present in the locale is used as-is."""
        assert _chrome("de", "reset_cta") == "Neues Passwort setzen"

    def test_missing_key_degrades_instead_of_raising(self) -> None:
        """Test that locale drift cannot turn into a silently unsent email."""
        # Nothing checks the backend locale files for en/de parity, so a key
        # added to en.json alone must not raise inside the send path.
        assert _chrome("de", "no_such_chrome_key") == ""
