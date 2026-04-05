"""Unit tests for PushSubscription CRUD operations."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.push_subscription import push_subscription as crud_push
from app.models.user import User
from app.schemas.notification import PushSubscriptionCreate


@pytest.mark.asyncio
class TestCRUDPushSubscription:
    """Test suite for PushSubscription CRUD operations."""

    async def test_create_or_update_creates_new(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test creating a new push subscription."""
        sub_in = PushSubscriptionCreate(
            endpoint="https://push.example.com/user1",
            p256dh_key="test-p256dh-key",
            auth_key="test-auth-key",
            user_agent="TestBrowser/1.0",
        )
        sub = await crud_push.create_or_update(
            db_session, user_id=test_user.id, obj_in=sub_in
        )

        assert sub.endpoint == "https://push.example.com/user1"
        assert sub.user_id == test_user.id
        assert sub.p256dh_key == "test-p256dh-key"
        assert sub.auth_key == "test-auth-key"
        assert sub.user_agent == "TestBrowser/1.0"

    async def test_create_or_update_updates_existing(
        self, db_session: AsyncSession, test_user: User, test_admin_user: User
    ):
        """Test that create_or_update updates an existing subscription."""
        sub_in = PushSubscriptionCreate(
            endpoint="https://push.example.com/shared",
            p256dh_key="old-key",
            auth_key="old-auth",
        )
        await crud_push.create_or_update(
            db_session, user_id=test_user.id, obj_in=sub_in
        )

        # Same endpoint, different user
        updated_in = PushSubscriptionCreate(
            endpoint="https://push.example.com/shared",
            p256dh_key="new-key",
            auth_key="new-auth",
        )
        updated = await crud_push.create_or_update(
            db_session, user_id=test_admin_user.id, obj_in=updated_in
        )

        assert updated.user_id == test_admin_user.id
        assert updated.p256dh_key == "new-key"

    async def test_get_by_user(self, db_session: AsyncSession, test_user: User):
        """Test fetching subscriptions for a user."""
        for i in range(2):
            sub_in = PushSubscriptionCreate(
                endpoint=f"https://push.example.com/device{i}",
                p256dh_key=f"key-{i}",
                auth_key=f"auth-{i}",
            )
            await crud_push.create_or_update(
                db_session, user_id=test_user.id, obj_in=sub_in
            )

        subs = await crud_push.get_by_user(db_session, user_id=test_user.id)
        assert len(subs) == 2

    async def test_get_by_endpoint(self, db_session: AsyncSession, test_user: User):
        """Test finding a subscription by endpoint."""
        sub_in = PushSubscriptionCreate(
            endpoint="https://push.example.com/findme",
            p256dh_key="key",
            auth_key="auth",
        )
        created = await crud_push.create_or_update(
            db_session, user_id=test_user.id, obj_in=sub_in
        )

        found = await crud_push.get_by_endpoint(
            db_session, endpoint="https://push.example.com/findme"
        )
        assert found is not None
        assert found.id == created.id

    async def test_get_by_endpoint_not_found(self, db_session: AsyncSession):
        """Test that a missing endpoint returns None."""
        found = await crud_push.get_by_endpoint(
            db_session, endpoint="https://nonexistent.example.com"
        )
        assert found is None

    async def test_remove_by_endpoint(self, db_session: AsyncSession, test_user: User):
        """Test removing a subscription by endpoint."""
        sub_in = PushSubscriptionCreate(
            endpoint="https://push.example.com/removeme",
            p256dh_key="key",
            auth_key="auth",
        )
        await crud_push.create_or_update(
            db_session, user_id=test_user.id, obj_in=sub_in
        )

        removed = await crud_push.remove_by_endpoint(
            db_session, endpoint="https://push.example.com/removeme"
        )
        assert removed is True

        found = await crud_push.get_by_endpoint(
            db_session, endpoint="https://push.example.com/removeme"
        )
        assert found is None

    async def test_remove_by_endpoint_not_found(self, db_session: AsyncSession):
        """Test removing a nonexistent subscription returns False."""
        removed = await crud_push.remove_by_endpoint(
            db_session, endpoint="https://nonexistent.example.com"
        )
        assert removed is False
