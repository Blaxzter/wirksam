"""Route tests for Notification Preferences endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationSubscription, NotificationType
from app.models.user import User


@pytest.mark.asyncio
class TestNotificationPreferencesRoutes:
    """Test suite for /notifications/preferences routes."""

    async def _create_notif_type(
        self, db_session: AsyncSession, code: str = "test.pref"
    ) -> NotificationType:
        nt = NotificationType(
            code=code,
            name=f"Test {code}",
            description="Desc",
            category="test",
            default_channels=["email"],
            is_active=True,
        )
        db_session.add(nt)
        await db_session.flush()
        await db_session.refresh(nt)
        return nt

    async def test_list_preferences_empty(self, async_client: AsyncClient):
        """Test listing preferences when none are set."""
        r = await async_client.get("/api/v1/notifications/preferences")

        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_create_preference(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """Test creating a notification preference."""
        nt = await self._create_notif_type(db_session, "test.create_pref")

        r = await async_client.post(
            "/api/v1/notifications/preferences",
            json={
                "notification_type_id": str(nt.id),
                "email_enabled": True,
                "push_enabled": False,
                "telegram_enabled": False,
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["email_enabled"] is True
        assert data["push_enabled"] is False

    async def test_get_channel_settings(self, async_client: AsyncClient):
        """Test getting global channel settings."""
        r = await async_client.get("/api/v1/notifications/channel-settings")

        assert r.status_code == 200
        data = r.json()
        assert "notify_email" in data
        assert "notify_push" in data
        assert "notify_telegram" in data

    async def test_update_channel_settings(self, async_client: AsyncClient):
        """Test updating global channel settings."""
        r = await async_client.patch(
            "/api/v1/notifications/channel-settings",
            json={"notify_email": False},
        )

        assert r.status_code == 200
        assert r.json()["notify_email"] is False

    async def test_update_preference(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test updating a notification preference."""
        nt = await self._create_notif_type(db_session, "test.update_pref")
        sub = NotificationSubscription(
            user_id=test_user.id,
            notification_type_id=nt.id,
            email_enabled=True,
            push_enabled=True,
        )
        db_session.add(sub)
        await db_session.flush()
        await db_session.refresh(sub)

        r = await async_client.patch(
            f"/api/v1/notifications/preferences/{sub.id}",
            json={"email_enabled": False},
        )

        assert r.status_code == 200
        assert r.json()["email_enabled"] is False

    async def test_delete_preference(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test deleting a notification preference."""
        nt = await self._create_notif_type(db_session, "test.delete_pref")
        sub = NotificationSubscription(
            user_id=test_user.id,
            notification_type_id=nt.id,
        )
        db_session.add(sub)
        await db_session.flush()
        await db_session.refresh(sub)

        r = await async_client.delete(f"/api/v1/notifications/preferences/{sub.id}")

        assert r.status_code == 204

    async def test_delete_preference_not_found(self, async_client: AsyncClient):
        """Test deleting a nonexistent preference returns 404."""
        import uuid

        fake_id = uuid.uuid4()
        r = await async_client.delete(f"/api/v1/notifications/preferences/{fake_id}")
        assert r.status_code == 404
