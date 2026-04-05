"""Route tests for Push Notification endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@pytest.mark.asyncio
class TestPushSubscriptionRoutes:
    """Test suite for /notifications/push-subscriptions routes."""

    async def test_register_push_subscription(self, async_client: AsyncClient):
        """Test registering a new push subscription."""
        r = await async_client.post(
            "/api/v1/notifications/push-subscriptions",
            json={
                "endpoint": "https://push.example.com/sub/abc123",
                "p256dh_key": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8p8REfWRs",
                "auth_key": "tBHItJI5svbpC7VjM0r9dg",
                "user_agent": "TestBrowser/1.0",
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["endpoint"] == "https://push.example.com/sub/abc123"
        assert "id" in data

    async def test_list_push_subscriptions(self, async_client: AsyncClient):
        """Test listing push subscriptions after registering one."""
        # Register first
        await async_client.post(
            "/api/v1/notifications/push-subscriptions",
            json={
                "endpoint": "https://push.example.com/sub/list-test",
                "p256dh_key": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0test",
                "auth_key": "listTestKey123",
            },
        )

        r = await async_client.get("/api/v1/notifications/push-subscriptions")

        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_delete_push_subscription(self, async_client: AsyncClient):
        """Test removing a push subscription."""
        # Register first
        r1 = await async_client.post(
            "/api/v1/notifications/push-subscriptions",
            json={
                "endpoint": "https://push.example.com/sub/delete-test",
                "p256dh_key": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0del",
                "auth_key": "deleteKey123",
            },
        )
        sub_id = r1.json()["id"]

        r2 = await async_client.delete(
            f"/api/v1/notifications/push-subscriptions/{sub_id}"
        )
        assert r2.status_code == 204

    async def test_delete_nonexistent_push_subscription(
        self, async_client: AsyncClient
    ):
        """Test deleting a nonexistent push subscription returns 404."""
        fake_id = uuid.uuid4()
        r = await async_client.delete(
            f"/api/v1/notifications/push-subscriptions/{fake_id}"
        )
        assert r.status_code == 404

    async def test_delete_other_users_push_subscription(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
    ):
        """Test that a user cannot delete another user's push subscription."""
        from app.crud.push_subscription import push_subscription as crud_push
        from app.schemas.notification import PushSubscriptionCreate

        sub = await crud_push.create_or_update(
            db_session,
            user_id=test_admin_user.id,
            obj_in=PushSubscriptionCreate(
                endpoint="https://push.example.com/sub/other-user",
                p256dh_key="otherUserKey123",
                auth_key="otherAuth123",
            ),
        )

        r = await async_client.delete(
            f"/api/v1/notifications/push-subscriptions/{sub.id}"
        )
        assert r.status_code == 403

    async def test_vapid_public_key(self, async_client: AsyncClient):
        """Test getting the VAPID public key (may return 503 if not configured)."""
        r = await async_client.get("/api/v1/notifications/vapid-public-key")
        # Either returns the key or 503 if not configured
        assert r.status_code in (200, 503)
