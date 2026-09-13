"""Unit tests for the notification delivery channels.

Every transport is replaced by a fake — ``aiosmtplib`` for email, ``pywebpush``
for web push and ``httpx`` for Telegram — so no test in this module ever opens a
network connection. The CRUD lookups the push/Telegram channels perform are
mocked as well, so no database session is required either.
"""

import json
import sys
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from pywebpush import WebPushException  # pyright: ignore[reportMissingTypeStubs]

from app.core.config import settings
from app.crud.push_subscription import push_subscription as crud_push
from app.crud.telegram_binding import telegram_binding as crud_telegram
from app.logic.notifications.channels.base import NotificationChannel
from app.logic.notifications.channels.email import (
    EmailChannel,
    _build_html,  # type: ignore[reportPrivateUsage]
)
from app.logic.notifications.channels.push import PushChannel
from app.logic.notifications.channels.telegram import (
    TelegramChannel,
    _escape_markdown,  # type: ignore[reportPrivateUsage]
)
from app.models.notification import PushSubscription, TelegramBinding
from app.models.user import User
from app.schemas.notification import NotificationData

ENDPOINT_A = "https://fcm.googleapis.com/fcm/send/endpoint-alpha-0000000001"
ENDPOINT_B = "https://updates.push.services.mozilla.com/wpush/v2/endpoint-beta"


# ── Fakes ─────────────────────────────────────────────────────────


class _FakeSession:
    """Stand-in for an ``AsyncSession``; every CRUD call against it is mocked."""

    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class _FakeSessionFactory:
    """Drop-in for ``app.core.db.async_session`` that never opens a connection."""

    def __init__(self) -> None:
        self.session = _FakeSession()
        self.opened = 0

    def __call__(self) -> "_FakeSessionFactory":
        self.opened += 1
        return self

    async def __aenter__(self) -> _FakeSession:
        return self.session

    async def __aexit__(self, *args: object) -> bool:
        return False


class _FakeWebPushResponse:
    """Minimal stand-in for the response attached to a ``WebPushException``."""

    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeTelegramResponse:
    """Minimal stand-in for an ``httpx.Response``."""

    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


class _FakeTelegramTransport:
    """Stand-in for ``httpx.AsyncClient`` that records POSTs instead of sending."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        text: str = '{"ok": true}',
        error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.error = error
        self.calls: list[tuple[str, dict[str, str | None]]] = []

    def __call__(self) -> "_FakeTelegramTransport":
        return self

    async def __aenter__(self) -> "_FakeTelegramTransport":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def post(
        self,
        url: str,
        *,
        json: dict[str, str | None],
        timeout: float,
    ) -> _FakeTelegramResponse:
        _ = timeout
        self.calls.append((url, json))
        if self.error is not None:
            raise self.error
        return _FakeTelegramResponse(self.status_code, self.text)


class _StubChannel(NotificationChannel):
    """Minimal concrete channel used to exercise the base-class defaults."""

    name = "stub"

    async def send(
        self,
        *,
        recipient: User,
        title: str,
        body: str,
        data: NotificationData | None = None,
    ) -> bool:
        _ = (recipient, title, body, data)
        return True


# ── Helpers ───────────────────────────────────────────────────────


def _make_user(
    *,
    email: str | None = "recipient@example.test",
    subject: str = "local|channel-test",
    language: str = "en",
) -> User:
    """Build an unpersisted user; channels only read plain attributes off it."""
    return User(
        subject=subject,
        email=email,
        name="Channel Test User",
        roles=[],
        is_active=True,
        preferred_language=language,
    )


def _make_subscription(endpoint: str, user_id: uuid.UUID) -> PushSubscription:
    """Build an unpersisted push subscription row."""
    return PushSubscription(
        user_id=user_id,
        endpoint=endpoint,
        p256dh_key=f"p256dh-for-{endpoint[-5:]}",
        auth_key=f"auth-for-{endpoint[-5:]}",
    )


def _make_binding(
    *,
    user_id: uuid.UUID,
    verified: bool = True,
    chat_id: str | None = "987654321",
) -> TelegramBinding:
    """Build an unpersisted Telegram binding row."""
    return TelegramBinding(
        user_id=user_id,
        telegram_chat_id=chat_id,
        telegram_username="channel_tester",
        is_verified=verified,
    )


@contextmanager
def _email_settings(
    *,
    enabled: bool = True,
    configured: bool = True,
    from_name: str | None = "Wirksam Test Sender",
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
    ):
        yield


@contextmanager
def _push_settings(
    *,
    configured: bool = True,
    claims_email: str | None = "push@example.test",
) -> Generator[None, None, None]:
    """Patch the VAPID settings the push channel reads."""
    with (
        patch.object(
            settings, "VAPID_PRIVATE_KEY", "test-private-key" if configured else None
        ),
        patch.object(
            settings, "VAPID_PUBLIC_KEY", "test-public-key" if configured else None
        ),
        patch.object(settings, "VAPID_CLAIMS_EMAIL", claims_email),
    ):
        yield


@contextmanager
def _telegram_settings(
    *, token: str | None = "12345:test-bot-token"
) -> Generator[None, None, None]:
    """Patch the bot token the Telegram channel reads."""
    with patch.object(settings, "TELEGRAM_BOT_TOKEN", token):
        yield


# ── Base class ────────────────────────────────────────────────────


class TestNotificationChannelBase:
    """Test suite for the shared NotificationChannel base class."""

    def test_is_configured_defaults_to_true(self) -> None:
        """Test that a channel needing no credentials is configured by default."""
        assert _StubChannel().is_configured() is True

    def test_abstract_channel_cannot_be_instantiated(self) -> None:
        """Test that the base class refuses instantiation without a send impl."""
        with pytest.raises(TypeError):
            NotificationChannel()  # pyright: ignore[reportAbstractUsage]


# ── Email ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestEmailChannel:
    """Test suite for EmailChannel.send / send_batch."""

    async def test_is_configured_true(self) -> None:
        """Test that email is configured when enabled and SMTP details exist."""
        with _email_settings():
            assert EmailChannel().is_configured() is True

    async def test_is_configured_false_when_emails_disabled(self) -> None:
        """Test that email is not configured in the local environment."""
        with _email_settings(enabled=False):
            assert EmailChannel().is_configured() is False

    async def test_is_configured_false_without_smtp_host(self) -> None:
        """Test that email is not configured without SMTP_HOST."""
        with _email_settings(configured=False):
            assert EmailChannel().is_configured() is False

    async def test_is_configured_false_without_from_address(self) -> None:
        """Test that email is not configured without EMAILS_FROM_EMAIL."""
        with (
            _email_settings(),
            patch.object(settings, "EMAILS_FROM_EMAIL", None),
        ):
            assert EmailChannel().is_configured() is False

    async def test_send_is_a_noop_when_emails_disabled(self) -> None:
        """Test that a disabled email channel reports success without sending."""
        with (
            _email_settings(enabled=False),
            patch.object(EmailChannel, "_smtp_send", new_callable=AsyncMock) as smtp,
        ):
            result = await EmailChannel().send(
                recipient=_make_user(), title="Title", body="Body"
            )

        assert result is True
        smtp.assert_not_awaited()

    async def test_send_returns_false_when_not_configured(self) -> None:
        """Test that a misconfigured email channel fails without sending."""
        with (
            _email_settings(configured=False),
            patch.object(EmailChannel, "_smtp_send", new_callable=AsyncMock) as smtp,
        ):
            result = await EmailChannel().send(
                recipient=_make_user(), title="Title", body="Body"
            )

        assert result is False
        smtp.assert_not_awaited()

    async def test_send_returns_false_for_recipient_without_email(self) -> None:
        """Test that a recipient without an address is skipped."""
        with (
            _email_settings(),
            patch.object(EmailChannel, "_smtp_send", new_callable=AsyncMock) as smtp,
        ):
            result = await EmailChannel().send(
                recipient=_make_user(email=None), title="Title", body="Body"
            )

        assert result is False
        smtp.assert_not_awaited()

    async def test_send_returns_false_for_demo_user(self) -> None:
        """Test that demo users never receive real email."""
        with (
            _email_settings(),
            patch.object(EmailChannel, "_smtp_send", new_callable=AsyncMock) as smtp,
        ):
            result = await EmailChannel().send(
                recipient=_make_user(subject="demo|abc123"),
                title="Title",
                body="Body",
            )

        assert result is False
        smtp.assert_not_awaited()

    async def test_send_success_builds_expected_message(self) -> None:
        """Test the happy path and the headers handed to the transport."""
        with (
            _email_settings(),
            patch.object(EmailChannel, "_smtp_send", new_callable=AsyncMock) as smtp,
        ):
            result = await EmailChannel().send(
                recipient=_make_user(),
                title="Shift changed",
                body="Line one\nLine two",
                data={"task_id": "task-1"},
            )

        assert result is True
        smtp.assert_awaited_once()
        call = smtp.await_args
        assert call is not None
        msg = call.args[0]
        assert msg["To"] == "recipient@example.test"
        assert msg["Subject"] == "[Wirksam Test] Shift changed"
        assert msg["From"] == "Wirksam Test Sender <sender@example.test>"

    async def test_send_falls_back_to_project_name_as_sender(self) -> None:
        """Test that a missing EMAILS_FROM_NAME falls back to PROJECT_NAME."""
        with (
            _email_settings(from_name=None),
            patch.object(EmailChannel, "_smtp_send", new_callable=AsyncMock) as smtp,
        ):
            result = await EmailChannel().send(
                recipient=_make_user(), title="Title", body="Body"
            )

        assert result is True
        call = smtp.await_args
        assert call is not None
        assert call.args[0]["From"] == "Wirksam Test <sender@example.test>"

    async def test_send_returns_false_when_transport_raises(self) -> None:
        """Test that a transport failure is swallowed and reported as False."""
        with (
            _email_settings(),
            patch.object(
                EmailChannel,
                "_smtp_send",
                new_callable=AsyncMock,
                side_effect=OSError("smtp server unreachable"),
            ) as smtp,
        ):
            result = await EmailChannel().send(
                recipient=_make_user(), title="Title", body="Body"
            )

        assert result is False
        smtp.assert_awaited_once()

    async def test_send_passes_smtp_settings_to_aiosmtplib(self) -> None:
        """Test that _smtp_send forwards the configured SMTP parameters."""
        with (
            _email_settings(),
            patch("aiosmtplib.send", new_callable=AsyncMock) as aiosmtp,
        ):
            result = await EmailChannel().send(
                recipient=_make_user(), title="Title", body="Body"
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

    async def test_send_returns_false_when_aiosmtplib_raises(self) -> None:
        """Test that an exception from the real transport call is contained."""
        with (
            _email_settings(),
            patch(
                "aiosmtplib.send",
                new_callable=AsyncMock,
                side_effect=ConnectionRefusedError("connection refused"),
            ),
        ):
            result = await EmailChannel().send(
                recipient=_make_user(), title="Title", body="Body"
            )

        assert result is False

    async def test_send_batch_is_a_noop_when_emails_disabled(self) -> None:
        """Test that a disabled email channel reports batch success without sending."""
        with (
            _email_settings(enabled=False),
            patch.object(EmailChannel, "_smtp_send", new_callable=AsyncMock) as smtp,
        ):
            result = await EmailChannel().send_batch(
                recipients=[_make_user()], title="Title", body="Body"
            )

        assert result is True
        smtp.assert_not_awaited()

    async def test_send_batch_returns_false_when_not_configured(self) -> None:
        """Test that a misconfigured email channel fails the batch."""
        with (
            _email_settings(configured=False),
            patch.object(EmailChannel, "_smtp_send", new_callable=AsyncMock) as smtp,
        ):
            result = await EmailChannel().send_batch(
                recipients=[_make_user()], title="Title", body="Body"
            )

        assert result is False
        smtp.assert_not_awaited()

    async def test_send_batch_returns_false_without_valid_recipients(self) -> None:
        """Test that a batch of only invalid recipients never reaches the transport."""
        recipients = [
            _make_user(email=None, subject="local|no-email"),
            _make_user(subject="demo|demo-user"),
        ]

        with (
            _email_settings(),
            patch.object(EmailChannel, "_smtp_send", new_callable=AsyncMock) as smtp,
        ):
            result = await EmailChannel().send_batch(
                recipients=recipients, title="Title", body="Body"
            )

        assert result is False
        smtp.assert_not_awaited()

    async def test_send_batch_bccs_every_valid_recipient(self) -> None:
        """Test that valid recipients are grouped into a single Bcc header."""
        recipients = [
            _make_user(email="one@example.test", subject="local|one"),
            _make_user(email="two@example.test", subject="local|two"),
            _make_user(email=None, subject="local|three"),
            _make_user(email="demo@example.test", subject="demo|four"),
        ]

        with (
            _email_settings(),
            patch.object(EmailChannel, "_smtp_send", new_callable=AsyncMock) as smtp,
        ):
            result = await EmailChannel().send_batch(
                recipients=recipients, title="Weekly digest", body="Body", language="de"
            )

        assert result is True
        smtp.assert_awaited_once()
        call = smtp.await_args
        assert call is not None
        msg = call.args[0]
        bcc = str(msg["Bcc"])
        assert "one@example.test" in bcc
        assert "two@example.test" in bcc
        assert "demo@example.test" not in bcc
        # The visible recipient is the sender itself, not one of the members.
        assert msg["To"] == "Wirksam Test Sender <sender@example.test>"

    async def test_send_batch_returns_false_when_transport_raises(self) -> None:
        """Test that a batch transport failure is reported as False."""
        with (
            _email_settings(),
            patch.object(
                EmailChannel,
                "_smtp_send",
                new_callable=AsyncMock,
                side_effect=OSError("smtp server unreachable"),
            ),
        ):
            result = await EmailChannel().send_batch(
                recipients=[_make_user()], title="Title", body="Body"
            )

        assert result is False


class TestEmailHtmlBody:
    """Test suite for the _build_html email template helper."""

    def test_task_data_links_to_task_detail(self) -> None:
        """Test that task_id data renders a link to the task page."""
        with _email_settings():
            html = _build_html(title="T", body="B", data={"task_id": "task-42"})

        assert "https://app.example.test/app/tasks/task-42" in html
        assert "View Details" in html

    def test_event_data_links_to_event_detail(self) -> None:
        """Test that event_id data renders a link to the event page.

        ``/app/events/{id}`` is not a route — the in-app handler and this link
        both have to target ``event-settings``.
        """
        with _email_settings():
            html = _build_html(title="T", body="B", data={"event_id": "event-7"})

        assert "https://app.example.test/app/event-settings/event-7" in html

    def test_task_id_wins_over_event_id(self) -> None:
        """Test that the task link takes precedence when both ids are present."""
        with _email_settings():
            html = _build_html(
                title="T", body="B", data={"task_id": "task-42", "event_id": "event-7"}
            )

        assert "/app/tasks/task-42" in html
        assert "/app/event-settings/event-7" not in html

    def test_no_action_button_without_data(self) -> None:
        """Test that no action button is rendered when there is no data."""
        with _email_settings():
            html = _build_html(title="T", body="B", data=None)

        assert "View Details" not in html
        assert "/app/tasks/" not in html
        assert "/app/event-settings/" not in html

    def test_no_action_button_for_unrelated_data(self) -> None:
        """Test that unrelated data keys do not produce an action button."""
        with _email_settings():
            html = _build_html(title="T", body="B", data={"slot_id": "slot-1"})

        assert "View Details" not in html

    def test_language_is_applied(self) -> None:
        """Test that the language drives both the lang attribute and the strings."""
        with _email_settings():
            html = _build_html(
                title="T", body="B", data={"task_id": "task-1"}, language="de"
            )

        assert '<html lang="de">' in html
        assert "Details anzeigen" in html
        assert "View Details" not in html

    def test_unknown_language_falls_back_to_english_strings(self) -> None:
        """Test that an unsupported language still renders English strings."""
        with _email_settings():
            html = _build_html(
                title="T", body="B", data={"task_id": "task-1"}, language="xx"
            )

        assert '<html lang="xx">' in html
        assert "View Details" in html

    def test_newlines_become_line_breaks(self) -> None:
        """Test that plain-text newlines are converted to <br> in the HTML part."""
        with _email_settings():
            html = _build_html(title="T", body="Line one\nLine two")

        assert "Line one<br>Line two" in html

    def test_body_markup_is_escaped(self) -> None:
        """Test that a body carrying markup cannot rewrite the message.

        The body is not template text: it carries event and task names, and the
        free-text note an event admin types when cloning an event.
        """
        with _email_settings():
            html = _build_html(title="T", body="<b>Ada</b> & <script>alert(1)</script>")

        assert "&lt;b&gt;Ada&lt;/b&gt;" in html
        assert "&amp;" in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert "<b>Ada</b>" not in html
        assert "<script>" not in html

    def test_title_markup_is_escaped(self) -> None:
        """Test that the title is escaped too, not just the body."""
        with _email_settings():
            html = _build_html(title="<img src=x onerror=alert(1)>", body="B")

        assert "&lt;img src=x onerror=alert(1)&gt;" in html
        assert "<img src=x" not in html

    def test_escape_runs_before_newlines_become_breaks(self) -> None:
        """Test the ORDER: escape the text, *then* restore line breaks.

        Replacing newlines first would have ``html.escape`` turn the freshly
        inserted ``<br>`` into ``&lt;br&gt;`` — every multi-line notification
        would render its own markup as visible text, and the two behaviours
        would regress independently of each other.
        """
        with _email_settings():
            html = _build_html(title="T", body="Note: <b>x</b>\nsecond line")

        assert "Note: &lt;b&gt;x&lt;/b&gt;<br>second line" in html
        assert "&lt;br&gt;" not in html

    def test_footer_links_to_notification_settings(self) -> None:
        """Test that the footer links to the notification preferences page."""
        with _email_settings():
            html = _build_html(title="T", body="B")

        assert "https://app.example.test/app/settings/notifications" in html
        assert "https://app.example.test/icon.svg" in html


# ── Push ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPushChannel:
    """Test suite for PushChannel.send."""

    async def test_is_configured_true(self) -> None:
        """Test that push is configured when both VAPID keys are present."""
        with _push_settings():
            assert PushChannel().is_configured() is True

    async def test_is_configured_false_without_keys(self) -> None:
        """Test that push is not configured without VAPID keys."""
        with _push_settings(configured=False):
            assert PushChannel().is_configured() is False

    async def test_is_configured_false_without_private_key(self) -> None:
        """Test that a public key alone is not enough."""
        with _push_settings(), patch.object(settings, "VAPID_PRIVATE_KEY", None):
            assert PushChannel().is_configured() is False

    async def test_send_returns_false_when_not_configured(self) -> None:
        """Test that a misconfigured push channel fails without calling webpush."""
        with (
            _push_settings(configured=False),
            patch("pywebpush.webpush") as webpush,
        ):
            result = await PushChannel().send(
                recipient=_make_user(), title="Title", body="Body"
            )

        assert result is False
        webpush.assert_not_called()

    async def test_send_returns_false_for_demo_user(self) -> None:
        """Test that demo users never receive a push message."""
        with _push_settings(), patch("pywebpush.webpush") as webpush:
            result = await PushChannel().send(
                recipient=_make_user(subject="demo|abc123"),
                title="Title",
                body="Body",
            )

        assert result is False
        webpush.assert_not_called()

    async def test_send_returns_false_without_subscriptions(self) -> None:
        """Test that a user without registered devices fails cleanly."""
        user = _make_user()
        sessions = _FakeSessionFactory()

        with (
            _push_settings(),
            patch("app.core.db.async_session", sessions),
            patch.object(crud_push, "get_by_user", AsyncMock(return_value=[])),
            patch("pywebpush.webpush") as webpush,
        ):
            result = await PushChannel().send(
                recipient=user, title="Title", body="Body"
            )

        assert result is False
        webpush.assert_not_called()
        assert sessions.opened == 1

    async def test_send_success_builds_expected_payload(self) -> None:
        """Test the happy path and the payload handed to pywebpush."""
        user = _make_user()
        subscription = _make_subscription(ENDPOINT_A, user.id)
        get_by_user = AsyncMock(return_value=[subscription])

        with (
            _push_settings(),
            patch("app.core.db.async_session", _FakeSessionFactory()),
            patch.object(crud_push, "get_by_user", get_by_user),
            patch("pywebpush.webpush") as webpush,
        ):
            result = await PushChannel().send(
                recipient=user,
                title="Shift changed",
                body="Be there at 5",
                data={"task_id": "task-1"},
            )

        assert result is True
        get_by_user.assert_awaited_once()
        assert get_by_user.await_args is not None
        assert get_by_user.await_args.kwargs["user_id"] == user.id

        webpush.assert_called_once()
        call = webpush.call_args
        assert call is not None
        assert call.kwargs["subscription_info"] == {
            "endpoint": ENDPOINT_A,
            "keys": {
                "p256dh": subscription.p256dh_key,
                "auth": subscription.auth_key,
            },
        }
        payload = json.loads(call.kwargs["data"])
        assert payload["title"] == "Shift changed"
        assert payload["body"] == "Be there at 5"
        assert payload["data"] == {"task_id": "task-1"}
        assert payload["icon"] == "/favicon.ico"
        assert call.kwargs["vapid_private_key"] == "test-private-key"
        assert call.kwargs["vapid_claims"] == {"sub": "mailto:push@example.test"}

    async def test_send_without_data_uses_empty_payload_data(self) -> None:
        """Test that a missing data dict becomes an empty object in the payload."""
        user = _make_user()

        with (
            _push_settings(claims_email=None),
            patch("app.core.db.async_session", _FakeSessionFactory()),
            patch.object(
                crud_push,
                "get_by_user",
                AsyncMock(return_value=[_make_subscription(ENDPOINT_A, user.id)]),
            ),
            patch("pywebpush.webpush") as webpush,
        ):
            result = await PushChannel().send(
                recipient=user, title="Title", body="Body"
            )

        assert result is True
        call = webpush.call_args
        assert call is not None
        assert json.loads(call.kwargs["data"])["data"] == {}
        assert call.kwargs["vapid_claims"] == {"sub": "mailto:noreply@example.com"}

    async def test_send_delivers_to_every_subscription(self) -> None:
        """Test that each registered device gets its own webpush call."""
        user = _make_user()
        subscriptions = [
            _make_subscription(ENDPOINT_A, user.id),
            _make_subscription(ENDPOINT_B, user.id),
        ]

        with (
            _push_settings(),
            patch("app.core.db.async_session", _FakeSessionFactory()),
            patch.object(
                crud_push, "get_by_user", AsyncMock(return_value=subscriptions)
            ),
            patch("pywebpush.webpush") as webpush,
        ):
            result = await PushChannel().send(
                recipient=user, title="Title", body="Body"
            )

        assert result is True
        assert webpush.call_count == 2

    async def test_send_removes_stale_subscription_on_410(self) -> None:
        """Test that a 410 response removes the endpoint and reports failure."""
        user = _make_user()
        sessions = _FakeSessionFactory()
        remove = AsyncMock(return_value=True)
        gone = WebPushException("gone", response=_FakeWebPushResponse(410, "Gone"))

        with (
            _push_settings(),
            patch("app.core.db.async_session", sessions),
            patch.object(
                crud_push,
                "get_by_user",
                AsyncMock(return_value=[_make_subscription(ENDPOINT_A, user.id)]),
            ),
            patch.object(crud_push, "remove_by_endpoint", remove),
            patch("pywebpush.webpush", side_effect=gone),
        ):
            result = await PushChannel().send(
                recipient=user, title="Title", body="Body"
            )

        assert result is False
        remove.assert_awaited_once()
        assert remove.await_args is not None
        assert remove.await_args.kwargs["endpoint"] == ENDPOINT_A
        assert sessions.session.commits == 1

    async def test_send_keeps_subscription_on_non_410_error(self) -> None:
        """Test that a transient push error does not delete the subscription."""
        user = _make_user()
        sessions = _FakeSessionFactory()
        remove = AsyncMock(return_value=True)
        failure = WebPushException(
            "boom", response=_FakeWebPushResponse(500, "Internal Server Error")
        )

        with (
            _push_settings(),
            patch("app.core.db.async_session", sessions),
            patch.object(
                crud_push,
                "get_by_user",
                AsyncMock(return_value=[_make_subscription(ENDPOINT_A, user.id)]),
            ),
            patch.object(crud_push, "remove_by_endpoint", remove),
            patch("pywebpush.webpush", side_effect=failure),
        ):
            result = await PushChannel().send(
                recipient=user, title="Title", body="Body"
            )

        assert result is False
        remove.assert_not_awaited()
        assert sessions.session.commits == 0

    async def test_send_handles_webpush_exception_without_response(self) -> None:
        """Test that a response-less WebPushException is treated as a soft failure."""
        user = _make_user()
        remove = AsyncMock(return_value=True)

        with (
            _push_settings(),
            patch("app.core.db.async_session", _FakeSessionFactory()),
            patch.object(
                crud_push,
                "get_by_user",
                AsyncMock(return_value=[_make_subscription(ENDPOINT_A, user.id)]),
            ),
            patch.object(crud_push, "remove_by_endpoint", remove),
            patch("pywebpush.webpush", side_effect=WebPushException("no response")),
        ):
            result = await PushChannel().send(
                recipient=user, title="Title", body="Body"
            )

        assert result is False
        remove.assert_not_awaited()

    async def test_send_succeeds_partially_and_prunes_stale_endpoint(self) -> None:
        """Test that one live device is enough for success while a stale one is pruned."""
        user = _make_user()
        remove = AsyncMock(return_value=True)
        gone = WebPushException("gone", response=_FakeWebPushResponse(410, "Gone"))

        with (
            _push_settings(),
            patch("app.core.db.async_session", _FakeSessionFactory()),
            patch.object(
                crud_push,
                "get_by_user",
                AsyncMock(
                    return_value=[
                        _make_subscription(ENDPOINT_A, user.id),
                        _make_subscription(ENDPOINT_B, user.id),
                    ]
                ),
            ),
            patch.object(crud_push, "remove_by_endpoint", remove),
            patch("pywebpush.webpush", side_effect=[gone, None]),
        ):
            result = await PushChannel().send(
                recipient=user, title="Title", body="Body"
            )

        assert result is True
        remove.assert_awaited_once()
        assert remove.await_args is not None
        assert remove.await_args.kwargs["endpoint"] == ENDPOINT_A

    async def test_send_returns_false_when_pywebpush_is_missing(self) -> None:
        """Test that a missing pywebpush dependency disables push instead of raising."""
        with (
            _push_settings(),
            patch.dict(sys.modules, {"pywebpush": None}),
        ):
            result = await PushChannel().send(
                recipient=_make_user(), title="Title", body="Body"
            )

        assert result is False

    async def test_send_returns_false_on_unexpected_error(self) -> None:
        """Test that an unexpected lookup failure is contained."""
        with (
            _push_settings(),
            patch("app.core.db.async_session", _FakeSessionFactory()),
            patch.object(
                crud_push,
                "get_by_user",
                AsyncMock(side_effect=RuntimeError("database unavailable")),
            ),
            patch("pywebpush.webpush") as webpush,
        ):
            result = await PushChannel().send(
                recipient=_make_user(), title="Title", body="Body"
            )

        assert result is False
        webpush.assert_not_called()


# ── Telegram ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestTelegramChannel:
    """Test suite for TelegramChannel.send."""

    async def test_is_configured_true(self) -> None:
        """Test that Telegram is configured when a bot token is set."""
        with _telegram_settings():
            assert TelegramChannel().is_configured() is True

    async def test_is_configured_false_without_token(self) -> None:
        """Test that Telegram is not configured without a bot token."""
        with _telegram_settings(token=None):
            assert TelegramChannel().is_configured() is False

    async def test_send_returns_false_when_not_configured(self) -> None:
        """Test that a missing bot token fails without touching the API."""
        transport = _FakeTelegramTransport()

        with (
            _telegram_settings(token=None),
            patch("httpx.AsyncClient", transport),
        ):
            result = await TelegramChannel().send(
                recipient=_make_user(), title="Title", body="Body"
            )

        assert result is False
        assert transport.calls == []

    async def test_send_returns_false_for_demo_user(self) -> None:
        """Test that demo users never trigger a Telegram message."""
        transport = _FakeTelegramTransport()

        with _telegram_settings(), patch("httpx.AsyncClient", transport):
            result = await TelegramChannel().send(
                recipient=_make_user(subject="demo|abc123"),
                title="Title",
                body="Body",
            )

        assert result is False
        assert transport.calls == []

    async def test_send_returns_false_without_binding(self) -> None:
        """Test that a user without a Telegram binding fails cleanly."""
        transport = _FakeTelegramTransport()

        with (
            _telegram_settings(),
            patch("app.core.db.async_session", _FakeSessionFactory()),
            patch.object(crud_telegram, "get_by_user", AsyncMock(return_value=None)),
            patch("httpx.AsyncClient", transport),
        ):
            result = await TelegramChannel().send(
                recipient=_make_user(), title="Title", body="Body"
            )

        assert result is False
        assert transport.calls == []

    async def test_send_returns_false_for_unverified_binding(self) -> None:
        """Test that an unverified binding is not used."""
        user = _make_user()
        transport = _FakeTelegramTransport()

        with (
            _telegram_settings(),
            patch("app.core.db.async_session", _FakeSessionFactory()),
            patch.object(
                crud_telegram,
                "get_by_user",
                AsyncMock(return_value=_make_binding(user_id=user.id, verified=False)),
            ),
            patch("httpx.AsyncClient", transport),
        ):
            result = await TelegramChannel().send(
                recipient=user, title="Title", body="Body"
            )

        assert result is False
        assert transport.calls == []

    async def test_send_returns_false_for_binding_without_chat_id(self) -> None:
        """Test that a verified binding without a chat id is not used."""
        user = _make_user()
        transport = _FakeTelegramTransport()

        with (
            _telegram_settings(),
            patch("app.core.db.async_session", _FakeSessionFactory()),
            patch.object(
                crud_telegram,
                "get_by_user",
                AsyncMock(return_value=_make_binding(user_id=user.id, chat_id=None)),
            ),
            patch("httpx.AsyncClient", transport),
        ):
            result = await TelegramChannel().send(
                recipient=user, title="Title", body="Body"
            )

        assert result is False
        assert transport.calls == []

    async def test_send_success_posts_markdown_message(self) -> None:
        """Test the happy path and the JSON body posted to the Bot API."""
        user = _make_user()
        transport = _FakeTelegramTransport()

        with (
            _telegram_settings(),
            patch("app.core.db.async_session", _FakeSessionFactory()),
            patch.object(
                crud_telegram,
                "get_by_user",
                AsyncMock(return_value=_make_binding(user_id=user.id)),
            ),
            patch("httpx.AsyncClient", transport),
        ):
            result = await TelegramChannel().send(
                recipient=user, title="Shift changed", body="Be there at 5.30"
            )

        assert result is True
        assert len(transport.calls) == 1
        url, payload = transport.calls[0]
        assert url == "https://api.telegram.org/bot12345:test-bot-token/sendMessage"
        assert payload["chat_id"] == "987654321"
        assert payload["parse_mode"] == "MarkdownV2"
        assert payload["text"] == "*Shift changed*\n\nBe there at 5\\.30"

    async def test_send_returns_false_on_api_error_status(self) -> None:
        """Test that a non-200 response from the Bot API is a failure."""
        user = _make_user()
        transport = _FakeTelegramTransport(
            status_code=403, text='{"description": "bot was blocked by the user"}'
        )

        with (
            _telegram_settings(),
            patch("app.core.db.async_session", _FakeSessionFactory()),
            patch.object(
                crud_telegram,
                "get_by_user",
                AsyncMock(return_value=_make_binding(user_id=user.id)),
            ),
            patch("httpx.AsyncClient", transport),
        ):
            result = await TelegramChannel().send(
                recipient=user, title="Title", body="Body"
            )

        assert result is False
        assert len(transport.calls) == 1

    async def test_send_returns_false_when_transport_raises(self) -> None:
        """Test that a network failure is swallowed and reported as False."""
        user = _make_user()
        transport = _FakeTelegramTransport(
            error=ConnectionError("telegram unreachable")
        )

        with (
            _telegram_settings(),
            patch("app.core.db.async_session", _FakeSessionFactory()),
            patch.object(
                crud_telegram,
                "get_by_user",
                AsyncMock(return_value=_make_binding(user_id=user.id)),
            ),
            patch("httpx.AsyncClient", transport),
        ):
            result = await TelegramChannel().send(
                recipient=user, title="Title", body="Body"
            )

        assert result is False

    async def test_send_returns_false_on_unexpected_error(self) -> None:
        """Test that an unexpected binding lookup failure is contained."""
        transport = _FakeTelegramTransport()

        with (
            _telegram_settings(),
            patch("app.core.db.async_session", _FakeSessionFactory()),
            patch.object(
                crud_telegram,
                "get_by_user",
                AsyncMock(side_effect=RuntimeError("database unavailable")),
            ),
            patch("httpx.AsyncClient", transport),
        ):
            result = await TelegramChannel().send(
                recipient=_make_user(), title="Title", body="Body"
            )

        assert result is False
        assert transport.calls == []


class TestEscapeMarkdown:
    """Test suite for the _escape_markdown MarkdownV2 helper."""

    @pytest.mark.parametrize("char", list(r"_*[]()~`>#+-=|{}.!"))
    def test_every_special_char_is_escaped(self, char: str) -> None:
        """Test that each MarkdownV2 special character gets a backslash."""
        assert _escape_markdown(char) == f"\\{char}"

    def test_plain_text_is_unchanged(self) -> None:
        """Test that text without special characters passes through untouched."""
        assert _escape_markdown("Shift 12 changed") == "Shift 12 changed"

    def test_empty_string(self) -> None:
        """Test that the empty string is handled."""
        assert _escape_markdown("") == ""

    def test_mixed_text(self) -> None:
        """Test escaping inside a realistic sentence."""
        assert (
            _escape_markdown("Shift (Kitchen) moved to 5.30!")
            == "Shift \\(Kitchen\\) moved to 5\\.30\\!"
        )
