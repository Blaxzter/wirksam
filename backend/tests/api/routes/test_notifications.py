"""Route tests for Notification endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.notification import notification as crud_notification
from app.models.notification import Notification
from app.models.user import User


@pytest.mark.asyncio
class TestNotificationRoutes:
    """Test suite for /notifications/ routes."""

    async def _create_notification(
        self,
        db_session: AsyncSession,
        user_id: uuid.UUID,
        title: str = "Test Notification",
    ) -> Notification:
        return await crud_notification.create_notification(
            db_session,
            recipient_id=user_id,
            notification_type_code="test.type",
            title=title,
            body="Test body",
        )

    async def test_list_notifications(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test listing notifications."""
        await self._create_notification(db_session, test_user.id)
        await self._create_notification(db_session, test_user.id, "Second")

        r = await async_client.get("/api/v1/notifications/")

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 2
        assert "items" in data
        assert "unread_count" in data

    async def test_list_notifications_unread_only(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test listing only unread notifications."""
        n1 = await self._create_notification(db_session, test_user.id, "Read me")
        await self._create_notification(db_session, test_user.id, "Unread")
        await crud_notification.mark_as_read(
            db_session, notification_id=n1.id, user_id=test_user.id
        )

        r = await async_client.get(
            "/api/v1/notifications/", params={"unread_only": True}
        )

        assert r.status_code == 200
        assert r.json()["total"] == 1

    async def test_get_unread_count(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting the unread notification count."""
        await self._create_notification(db_session, test_user.id)

        r = await async_client.get("/api/v1/notifications/unread-count")

        assert r.status_code == 200
        assert r.json()["unread_count"] >= 1

    async def test_mark_notification_read(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test marking a notification as read."""
        notif = await self._create_notification(db_session, test_user.id)

        r = await async_client.patch(f"/api/v1/notifications/{notif.id}/read")

        assert r.status_code == 200
        assert r.json()["is_read"] is True
        assert r.json()["read_at"] is not None

    async def test_mark_notification_read_not_found(self, async_client: AsyncClient):
        """Test marking a nonexistent notification returns 404."""
        fake_id = uuid.uuid4()
        r = await async_client.patch(f"/api/v1/notifications/{fake_id}/read")
        assert r.status_code == 404

    async def test_mark_all_read(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test marking all notifications as read."""
        for i in range(3):
            await self._create_notification(db_session, test_user.id, f"N{i}")

        r = await async_client.post("/api/v1/notifications/mark-all-read")

        assert r.status_code == 200
        assert r.json()["marked_count"] == 3

    async def test_dismiss_notification(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test deleting a notification."""
        notif = await self._create_notification(db_session, test_user.id)

        r = await async_client.delete(f"/api/v1/notifications/{notif.id}")
        assert r.status_code == 204

    async def test_dismiss_notification_not_found(self, async_client: AsyncClient):
        """Test deleting a nonexistent notification returns 404."""
        fake_id = uuid.uuid4()
        r = await async_client.delete(f"/api/v1/notifications/{fake_id}")
        assert r.status_code == 404

    async def test_dismiss_other_users_notification(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
    ):
        """Test that a user cannot dismiss another user's notification."""
        notif = await self._create_notification(db_session, test_admin_user.id)

        r = await async_client.delete(f"/api/v1/notifications/{notif.id}")
        assert r.status_code == 403
