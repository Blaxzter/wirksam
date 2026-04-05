"""Unit tests for NotificationService."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.logic.notifications.service import NotificationService
from app.models.notification import NotificationType
from app.models.user import User


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
