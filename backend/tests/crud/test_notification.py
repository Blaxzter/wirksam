"""Unit tests for Notification CRUD operations."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.notification import notification as crud_notification
from app.models.user import User


@pytest.mark.asyncio
class TestCRUDNotification:
    """Test suite for Notification CRUD operations."""

    async def test_create_notification(self, db_session: AsyncSession, test_user: User):
        """Test creating a notification."""
        notif = await crud_notification.create_notification(
            db_session,
            recipient_id=test_user.id,
            notification_type_code="booking.confirmed",
            title="Booking Confirmed",
            body="Your booking has been confirmed.",
        )

        assert notif.recipient_id == test_user.id
        assert notif.notification_type_code == "booking.confirmed"
        assert notif.title == "Booking Confirmed"
        assert notif.is_read is False
        assert notif.read_at is None
        assert notif.id is not None

    async def test_create_notification_with_data(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test creating a notification with arbitrary data."""
        notif = await crud_notification.create_notification(
            db_session,
            recipient_id=test_user.id,
            notification_type_code="slot.time_changed",
            title="Slot Changed",
            body="The slot time changed.",
            data={"slot_id": "abc123"},
            channels_sent=["email"],
            channels_failed=["push"],
        )

        assert notif.data == {"slot_id": "abc123"}
        assert notif.channels_sent == ["email"]
        assert notif.channels_failed == ["push"]

    async def test_get_multi_by_recipient(
        self, db_session: AsyncSession, test_user: User, test_admin_user: User
    ):
        """Test fetching notifications for a specific user."""
        for i in range(3):
            await crud_notification.create_notification(
                db_session,
                recipient_id=test_user.id,
                notification_type_code="test.type",
                title=f"Notif {i}",
                body=f"Body {i}",
            )
        # One for admin to verify filtering
        await crud_notification.create_notification(
            db_session,
            recipient_id=test_admin_user.id,
            notification_type_code="test.type",
            title="Admin notif",
            body="Admin body",
        )

        user_notifs = await crud_notification.get_multi_by_recipient(
            db_session, user_id=test_user.id
        )
        assert len(user_notifs) == 3
        assert all(n.recipient_id == test_user.id for n in user_notifs)

    async def test_get_multi_by_recipient_unread_only(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test fetching only unread notifications."""
        n1 = await crud_notification.create_notification(
            db_session,
            recipient_id=test_user.id,
            notification_type_code="test.type",
            title="Unread",
            body="Body",
        )
        await crud_notification.create_notification(
            db_session,
            recipient_id=test_user.id,
            notification_type_code="test.type",
            title="Also unread",
            body="Body",
        )
        # Mark one as read
        await crud_notification.mark_as_read(
            db_session, notification_id=n1.id, user_id=test_user.id
        )

        unread = await crud_notification.get_multi_by_recipient(
            db_session, user_id=test_user.id, unread_only=True
        )
        assert len(unread) == 1
        assert unread[0].title == "Also unread"

    async def test_count_by_recipient(self, db_session: AsyncSession, test_user: User):
        """Test counting notifications for a user."""
        for i in range(2):
            await crud_notification.create_notification(
                db_session,
                recipient_id=test_user.id,
                notification_type_code="test.type",
                title=f"N {i}",
                body="B",
            )

        total = await crud_notification.count_by_recipient(
            db_session, user_id=test_user.id
        )
        assert total == 2

    async def test_get_unread_count(self, db_session: AsyncSession, test_user: User):
        """Test counting unread notifications."""
        n1 = await crud_notification.create_notification(
            db_session,
            recipient_id=test_user.id,
            notification_type_code="test.type",
            title="Read me",
            body="B",
        )
        await crud_notification.create_notification(
            db_session,
            recipient_id=test_user.id,
            notification_type_code="test.type",
            title="Unread",
            body="B",
        )
        await crud_notification.mark_as_read(
            db_session, notification_id=n1.id, user_id=test_user.id
        )

        count = await crud_notification.get_unread_count(
            db_session, user_id=test_user.id
        )
        assert count == 1

    async def test_mark_as_read(self, db_session: AsyncSession, test_user: User):
        """Test marking a notification as read."""
        notif = await crud_notification.create_notification(
            db_session,
            recipient_id=test_user.id,
            notification_type_code="test.type",
            title="Mark me",
            body="B",
        )
        assert notif.is_read is False

        updated = await crud_notification.mark_as_read(
            db_session, notification_id=notif.id, user_id=test_user.id
        )

        assert updated is not None
        assert updated.is_read is True
        assert updated.read_at is not None

    async def test_mark_as_read_already_read(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test marking an already-read notification as read is a no-op."""
        notif = await crud_notification.create_notification(
            db_session,
            recipient_id=test_user.id,
            notification_type_code="test.type",
            title="Already read",
            body="B",
        )
        await crud_notification.mark_as_read(
            db_session, notification_id=notif.id, user_id=test_user.id
        )

        # Mark again — should still return the notification
        result = await crud_notification.mark_as_read(
            db_session, notification_id=notif.id, user_id=test_user.id
        )
        assert result is not None
        assert result.is_read is True

    async def test_mark_as_read_wrong_user(
        self, db_session: AsyncSession, test_user: User, test_admin_user: User
    ):
        """Test that marking another user's notification returns None."""
        notif = await crud_notification.create_notification(
            db_session,
            recipient_id=test_user.id,
            notification_type_code="test.type",
            title="Private",
            body="B",
        )

        result = await crud_notification.mark_as_read(
            db_session, notification_id=notif.id, user_id=test_admin_user.id
        )
        assert result is None

    async def test_mark_all_as_read(self, db_session: AsyncSession, test_user: User):
        """Test marking all notifications as read for a user."""
        for i in range(3):
            await crud_notification.create_notification(
                db_session,
                recipient_id=test_user.id,
                notification_type_code="test.type",
                title=f"N {i}",
                body="B",
            )

        count = await crud_notification.mark_all_as_read(
            db_session, user_id=test_user.id
        )
        assert count == 3

        unread = await crud_notification.get_unread_count(
            db_session, user_id=test_user.id
        )
        assert unread == 0
