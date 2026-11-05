"""Unit tests for NotificationService."""

import uuid
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.logic.notifications.channels.email import EmailBody
from app.logic.notifications.service import NotificationService
from app.models.notification import NotificationType
from app.models.user import User

SERVICE = "app.logic.notifications.service"


@pytest.mark.asyncio
class TestNotificationService:
    """Test suite for NotificationService."""

    async def _setup_type(
        self, db_session: AsyncSession, code: str = "test.service"
    ) -> NotificationType:
        nt = NotificationType(
            code=code,
            name="Test Service Type",
            description="Desc",
            category="test",
            default_channels=["email"],
            is_active=True,
        )
        db_session.add(nt)
        await db_session.flush()
        await db_session.refresh(nt)
        return nt

    @patch(
        "app.logic.notifications.service.EmailChannel.is_configured",
        return_value=False,
    )
    @patch(
        "app.logic.notifications.service.PushChannel.is_configured",
        return_value=False,
    )
    @patch(
        "app.logic.notifications.service.TelegramChannel.is_configured",
        return_value=False,
    )
    async def test_notify_creates_in_app_notification(
        self,
        mock_tg: AsyncMock,
        mock_push: AsyncMock,
        mock_email: AsyncMock,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that notify creates an in-app notification record."""
        await self._setup_type(db_session, "test.service_notify")
        service = NotificationService(db_session)

        notifications = await service.notify(
            recipient_ids=[test_user.id],
            type_code="test.service_notify",
            title="Test Title",
            body="Test Body",
        )

        assert len(notifications) == 1
        assert notifications[0].title == "Test Title"
        assert notifications[0].body == "Test Body"
        assert notifications[0].recipient_id == test_user.id

    @patch(
        "app.logic.notifications.service.EmailChannel.is_configured",
        return_value=False,
    )
    @patch(
        "app.logic.notifications.service.PushChannel.is_configured",
        return_value=False,
    )
    @patch(
        "app.logic.notifications.service.TelegramChannel.is_configured",
        return_value=False,
    )
    async def test_notify_with_message_factory(
        self,
        mock_tg: AsyncMock,
        mock_push: AsyncMock,
        mock_email: AsyncMock,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that notify uses the message factory for localization."""
        await self._setup_type(db_session, "test.factory")
        service = NotificationService(db_session)

        def factory(lang: str) -> tuple[str, str]:
            if lang == "de":
                return "Deutsch Titel", "Deutsch Body"
            return "English Title", "English Body"

        notifications = await service.notify(
            recipient_ids=[test_user.id],
            type_code="test.factory",
            message_factory=factory,
        )

        assert len(notifications) == 1
        # test_user has preferred_language="en" by default
        assert notifications[0].title == "English Title"

    @patch(
        "app.logic.notifications.service.EmailChannel.is_configured",
        return_value=False,
    )
    @patch(
        "app.logic.notifications.service.PushChannel.is_configured",
        return_value=False,
    )
    @patch(
        "app.logic.notifications.service.TelegramChannel.is_configured",
        return_value=False,
    )
    async def test_notify_skips_nonexistent_user(
        self,
        mock_tg: AsyncMock,
        mock_push: AsyncMock,
        mock_email: AsyncMock,
        db_session: AsyncSession,
    ):
        """Test that notify skips nonexistent recipients."""
        service = NotificationService(db_session)

        notifications = await service.notify(
            recipient_ids=[uuid.uuid4()],
            type_code="test.type",
            title="Test",
            body="Body",
        )

        assert len(notifications) == 0

    @patch(
        "app.logic.notifications.service.EmailChannel.is_configured",
        return_value=False,
    )
    @patch(
        "app.logic.notifications.service.PushChannel.is_configured",
        return_value=False,
    )
    @patch(
        "app.logic.notifications.service.TelegramChannel.is_configured",
        return_value=False,
    )
    async def test_notify_multiple_recipients(
        self,
        mock_tg: AsyncMock,
        mock_push: AsyncMock,
        mock_email: AsyncMock,
        db_session: AsyncSession,
        test_user: User,
        test_admin_user: User,
    ):
        """Test notifying multiple recipients."""
        await self._setup_type(db_session, "test.multi")
        service = NotificationService(db_session)

        notifications = await service.notify(
            recipient_ids=[test_user.id, test_admin_user.id],
            type_code="test.multi",
            title="Multi",
            body="Body",
        )

        assert len(notifications) == 2

    @patch(
        "app.logic.notifications.service.EmailChannel.is_configured",
        return_value=False,
    )
    @patch(
        "app.logic.notifications.service.PushChannel.is_configured",
        return_value=False,
    )
    @patch(
        "app.logic.notifications.service.TelegramChannel.is_configured",
        return_value=False,
    )
    async def test_notify_with_data(
        self,
        mock_tg: AsyncMock,
        mock_push: AsyncMock,
        mock_email: AsyncMock,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that data is stored on the notification."""
        await self._setup_type(db_session, "test.data")
        service = NotificationService(db_session)

        notifications = await service.notify(
            recipient_ids=[test_user.id],
            type_code="test.data",
            title="With Data",
            body="Body",
            data={"slot_id": "abc123"},
        )

        assert len(notifications) == 1
        assert notifications[0].data == {"slot_id": "abc123"}

    @patch(
        "app.logic.notifications.service.EmailChannel.is_configured",
        return_value=False,
    )
    @patch(
        "app.logic.notifications.service.PushChannel.is_configured",
        return_value=False,
    )
    @patch(
        "app.logic.notifications.service.TelegramChannel.is_configured",
        return_value=False,
    )
    async def test_notify_admins(
        self,
        mock_tg: AsyncMock,
        mock_push: AsyncMock,
        mock_email: AsyncMock,
        db_session: AsyncSession,
        test_admin_user: User,
    ):
        """Test notifying all admin users."""
        await self._setup_type(db_session, "test.admin_notif")
        service = NotificationService(db_session)

        notifications = await service.notify_admins(
            type_code="test.admin_notif",
            title="Admin Alert",
            body="Something happened",
        )

        assert len(notifications) >= 1
        # All notifications should be for admin users
        admin_ids = [n.recipient_id for n in notifications]
        assert test_admin_user.id in admin_ids


@pytest.mark.asyncio
class TestOwnEmail:
    """``email_body``: each recipient gets their own mail instead of the BCC one."""

    async def _setup_type(self, db_session: AsyncSession, code: str) -> None:
        db_session.add(
            NotificationType(
                code=code,
                name="Own Mail Type",
                description="Desc",
                category="test",
                default_channels=["email"],
                is_active=True,
            )
        )
        await db_session.flush()

    async def test_sends_one_mail_per_recipient_with_its_own_body(
        self, db_session: AsyncSession, test_user: User, test_admin_user: User
    ) -> None:
        await self._setup_type(db_session, "test.own_mail")
        written: list[User] = []

        def _body(recipient: User) -> EmailBody:
            written.append(recipient)
            return EmailBody(text=f"Hi {recipient.name}", html="<p>hi</p>")

        with (
            patch(f"{SERVICE}.EmailChannel.send", new_callable=AsyncMock) as send,
            patch(
                f"{SERVICE}.EmailChannel.send_batch", new_callable=AsyncMock
            ) as batch,
        ):
            send.return_value = True
            notifications = await NotificationService(db_session).notify(
                recipient_ids=[test_user.id, test_admin_user.id],
                type_code="test.own_mail",
                title="Title",
                body="Body",
                email_body=_body,
            )

        batch.assert_not_awaited()
        assert [user.id for user in written] == [test_user.id, test_admin_user.id]
        sent = {
            call.kwargs["recipient"].id: call.kwargs for call in send.await_args_list
        }
        assert sent[test_user.id]["content"] == EmailBody(
            text=f"Hi {test_user.name}", html="<p>hi</p>"
        )
        assert sent[test_user.id]["title"] == "Title"
        assert all(n.channels_sent == ["email"] for n in notifications)

    async def test_a_failed_send_is_recorded(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        await self._setup_type(db_session, "test.own_mail_fails")

        with patch(
            f"{SERVICE}.EmailChannel.send", new_callable=AsyncMock, return_value=False
        ):
            [notif] = await NotificationService(db_session).notify(
                recipient_ids=[test_user.id],
                type_code="test.own_mail_fails",
                title="Title",
                body="Body",
                email_body=lambda _: EmailBody(text="t", html="h"),
            )

        assert notif.channels_failed == ["email"]
        assert notif.channels_sent == []

    async def test_a_body_that_fails_to_render_falls_back_to_the_plain_mail(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A bug in a renderer costs the details, not the notice."""
        await self._setup_type(db_session, "test.own_mail_broken")

        def _broken(_: User) -> EmailBody:
            raise KeyError("missing string")

        with patch(
            f"{SERVICE}.EmailChannel.send", new_callable=AsyncMock, return_value=True
        ) as send:
            [notif] = await NotificationService(db_session).notify(
                recipient_ids=[test_user.id],
                type_code="test.own_mail_broken",
                title="Title",
                body="Body",
                email_body=_broken,
            )

        send.assert_awaited_once()
        call = send.await_args
        assert call is not None
        assert call.kwargs["content"] is None
        assert call.kwargs["body"] == "Body"
        assert notif.channels_sent == ["email"]


@pytest.mark.asyncio
class TestAReminderAndTheChannelSwitches:
    """A notice with its own channels still obeys the switch on each channel."""

    @pytest.fixture(autouse=True)
    def channels(self) -> Generator[dict[str, AsyncMock]]:
        with (
            patch(f"{SERVICE}.EmailChannel.is_configured", return_value=True),
            patch(f"{SERVICE}.PushChannel.is_configured", return_value=True),
            patch(f"{SERVICE}.TelegramChannel.is_configured", return_value=True),
            patch(
                f"{SERVICE}.EmailChannel.send_batch",
                new_callable=AsyncMock,
                return_value=True,
            ) as email,
            patch(
                f"{SERVICE}.PushChannel.send",
                new_callable=AsyncMock,
                return_value=True,
            ) as push,
            patch(
                f"{SERVICE}.TelegramChannel.send",
                new_callable=AsyncMock,
                return_value=True,
            ) as telegram,
        ):
            yield {"email": email, "push": push, "telegram": telegram}

    async def _remind(self, db_session: AsyncSession, user: User, chosen: list[str]):
        db_session.add(
            NotificationType(
                code="test.own_channels",
                name="Own channels",
                category="test",
                default_channels=[],
                is_user_configurable=False,
            )
        )
        await db_session.flush()
        return await NotificationService(db_session).notify(
            recipient_ids=[user.id],
            type_code="test.own_channels",
            title="Soon",
            body="Your shift starts soon",
            only_channels=chosen,
        )

    async def test_it_uses_the_channels_it_was_given(
        self,
        db_session: AsyncSession,
        test_user: User,
        channels: dict[str, AsyncMock],
    ) -> None:
        [notice] = await self._remind(db_session, test_user, ["email", "push"])

        channels["email"].assert_awaited_once()
        channels["push"].assert_awaited_once()
        channels["telegram"].assert_not_awaited()
        assert set(notice.channels_sent) == {"email", "push"}

    @pytest.mark.parametrize(
        ("switch", "channel"),
        [
            ("notify_email", "email"),
            ("notify_push", "push"),
            ("notify_telegram", "telegram"),
        ],
    )
    async def test_a_channel_switched_off_stays_off(
        self,
        db_session: AsyncSession,
        test_user: User,
        channels: dict[str, AsyncMock],
        switch: str,
        channel: str,
    ) -> None:
        setattr(test_user, switch, False)
        db_session.add(test_user)
        await db_session.flush()

        [notice] = await self._remind(
            db_session, test_user, ["email", "push", "telegram"]
        )

        channels[channel].assert_not_awaited()
        assert channel not in notice.channels_sent
        others = {"email", "push", "telegram"} - {channel}
        for other in others:
            channels[other].assert_awaited_once()

    async def test_with_every_channel_off_it_still_lands_in_the_inbox(
        self,
        db_session: AsyncSession,
        test_user: User,
        channels: dict[str, AsyncMock],
    ) -> None:
        test_user.notify_email = False
        test_user.notify_push = False
        test_user.notify_telegram = False
        db_session.add(test_user)
        await db_session.flush()

        [notice] = await self._remind(db_session, test_user, ["email", "push"])

        assert notice.recipient_id == test_user.id
        assert notice.body == "Your shift starts soon"
        assert notice.channels_sent == []
        for sent in channels.values():
            sent.assert_not_awaited()
