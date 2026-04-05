"""Unit tests for NotificationSubscription CRUD operations."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.notification_subscription import (
    notification_subscription as crud_subscription,
)
from app.models.notification import NotificationSubscription, NotificationType
from app.models.user import User
from app.schemas.notification import NotificationSubscriptionCreate


@pytest.mark.asyncio
class TestCRUDNotificationSubscription:
    """Test suite for NotificationSubscription CRUD operations."""

    async def _create_notif_type(
        self, db_session: AsyncSession, code: str = "test.sub"
    ) -> NotificationType:
        nt = NotificationType(
            code=code,
            name=f"Test {code}",
            description="Desc",
            category="test",
            default_channels=["email", "push"],
            is_active=True,
        )
        db_session.add(nt)
        await db_session.flush()
        await db_session.refresh(nt)
        return nt

    async def test_get_user_preferences_empty(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test getting preferences when none are set."""
        prefs = await crud_subscription.get_user_preferences(
            db_session, user_id=test_user.id
        )
        assert len(prefs) == 0

    async def test_bulk_upsert_creates_new(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test bulk upsert creates new subscriptions."""
        nt = await self._create_notif_type(db_session, "test.bulk_new")

        prefs = [
            NotificationSubscriptionCreate(
                notification_type_id=nt.id,
                email_enabled=True,
                push_enabled=False,
            )
        ]
        results = await crud_subscription.bulk_upsert(
            db_session, user_id=test_user.id, preferences=prefs
        )

        assert len(results) == 1
        assert results[0].email_enabled is True
        assert results[0].push_enabled is False
        assert results[0].user_id == test_user.id

    async def test_bulk_upsert_updates_existing(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test bulk upsert updates existing subscriptions."""
        nt = await self._create_notif_type(db_session, "test.bulk_update")

        # Create initial
        await crud_subscription.bulk_upsert(
            db_session,
            user_id=test_user.id,
            preferences=[
                NotificationSubscriptionCreate(
                    notification_type_id=nt.id,
                    email_enabled=True,
                    push_enabled=True,
                )
            ],
        )

        # Update
        results = await crud_subscription.bulk_upsert(
            db_session,
            user_id=test_user.id,
            preferences=[
                NotificationSubscriptionCreate(
                    notification_type_id=nt.id,
                    email_enabled=False,
                    push_enabled=False,
                )
            ],
        )

        assert len(results) == 1
        assert results[0].email_enabled is False
        assert results[0].push_enabled is False

    async def test_get_user_preferences(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test getting user preferences after creating some."""
        nt1 = await self._create_notif_type(db_session, "test.pref1")
        nt2 = await self._create_notif_type(db_session, "test.pref2")

        await crud_subscription.bulk_upsert(
            db_session,
            user_id=test_user.id,
            preferences=[
                NotificationSubscriptionCreate(notification_type_id=nt1.id),
                NotificationSubscriptionCreate(notification_type_id=nt2.id),
            ],
        )

        prefs = await crud_subscription.get_user_preferences(
            db_session, user_id=test_user.id
        )
        assert len(prefs) == 2

    async def test_resolve_channels_with_subscription(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test resolving channels when user has a subscription."""
        nt = await self._create_notif_type(db_session, "test.resolve")

        sub = NotificationSubscription(
            user_id=test_user.id,
            notification_type_id=nt.id,
            email_enabled=True,
            push_enabled=False,
            telegram_enabled=True,
        )
        db_session.add(sub)
        await db_session.flush()

        channels = await crud_subscription.resolve_channels(
            db_session, user_id=test_user.id, type_code="test.resolve"
        )

        assert channels is not None
        assert channels["email"] is True
        assert channels["push"] is False
        assert channels["telegram"] is True

    async def test_resolve_channels_no_subscription_uses_defaults(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test resolving channels falls back to type defaults."""
        await self._create_notif_type(db_session, "test.nosubdefault")

        channels = await crud_subscription.resolve_channels(
            db_session, user_id=test_user.id, type_code="test.nosubdefault"
        )

        assert channels is not None
        assert channels["email"] is True  # default_channels includes email
        assert channels["push"] is True  # default_channels includes push
        assert channels["telegram"] is False  # not in defaults

    async def test_resolve_channels_muted_returns_none(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that muted subscriptions return None."""
        nt = await self._create_notif_type(db_session, "test.muted")

        sub = NotificationSubscription(
            user_id=test_user.id,
            notification_type_id=nt.id,
            is_muted=True,
        )
        db_session.add(sub)
        await db_session.flush()

        channels = await crud_subscription.resolve_channels(
            db_session, user_id=test_user.id, type_code="test.muted"
        )

        assert channels is None

    async def test_resolve_channels_unknown_type_returns_none(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test resolving channels for unknown type returns None."""
        channels = await crud_subscription.resolve_channels(
            db_session, user_id=test_user.id, type_code="nonexistent.type"
        )
        assert channels is None

    async def test_resolve_channels_respects_user_kill_switch(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that user-level channel kill switches are respected."""
        _nt = await self._create_notif_type(db_session, "test.killswitch")

        # Disable email at user level
        test_user.notify_email = False
        db_session.add(test_user)
        await db_session.flush()

        channels = await crud_subscription.resolve_channels(
            db_session, user_id=test_user.id, type_code="test.killswitch"
        )

        assert channels is not None
        assert channels["email"] is False  # killed at user level

    async def test_bulk_upsert_with_scope(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test bulk upsert with scoped subscriptions."""
        import uuid

        nt = await self._create_notif_type(db_session, "test.scoped")
        scope_id = uuid.uuid4()

        prefs = [
            NotificationSubscriptionCreate(
                notification_type_id=nt.id,
                scope_type="event_group",
                scope_id=scope_id,
                email_enabled=False,
            )
        ]
        results = await crud_subscription.bulk_upsert(
            db_session, user_id=test_user.id, preferences=prefs
        )

        assert len(results) == 1
        assert results[0].scope_type == "event_group"
        assert results[0].scope_id == scope_id
