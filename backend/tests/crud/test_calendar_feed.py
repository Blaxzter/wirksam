"""Unit tests for CalendarFeed CRUD operations."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.calendar_feed import crud_calendar_feed
from app.models.user import User


@pytest.mark.asyncio
class TestCRUDCalendarFeed:
    """Test suite for CalendarFeed CRUD operations."""

    async def test_create_for_user(self, db_session: AsyncSession, test_user: User):
        """Test creating a calendar feed token for a user."""
        feed = await crud_calendar_feed.create_for_user(
            db_session, user_id=test_user.id
        )

        assert feed.user_id == test_user.id
        assert feed.token is not None
        assert len(feed.token) > 0
        assert feed.is_enabled is True
        assert feed.last_accessed_at is None

    async def test_get_by_user(self, db_session: AsyncSession, test_user: User):
        """Test getting a feed token by user ID."""
        created = await crud_calendar_feed.create_for_user(
            db_session, user_id=test_user.id
        )

        found = await crud_calendar_feed.get_by_user(db_session, user_id=test_user.id)

        assert found is not None
        assert found.id == created.id

    async def test_get_by_user_not_found(
        self, db_session: AsyncSession, test_admin_user: User
    ):
        """Test that get_by_user returns None for a user without a feed."""
        found = await crud_calendar_feed.get_by_user(
            db_session, user_id=test_admin_user.id
        )
        assert found is None

    async def test_get_by_token(self, db_session: AsyncSession, test_user: User):
        """Test getting a feed by its token."""
        created = await crud_calendar_feed.create_for_user(
            db_session, user_id=test_user.id
        )

        found = await crud_calendar_feed.get_by_token(db_session, token=created.token)

        assert found is not None
        assert found.id == created.id

    async def test_get_by_token_disabled_returns_none(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test that a disabled feed token is not returned."""
        created = await crud_calendar_feed.create_for_user(
            db_session, user_id=test_user.id
        )
        await crud_calendar_feed.set_enabled(db_session, db_obj=created, enabled=False)

        found = await crud_calendar_feed.get_by_token(db_session, token=created.token)
        assert found is None

    async def test_regenerate_token(self, db_session: AsyncSession, test_user: User):
        """Test regenerating a feed token."""
        created = await crud_calendar_feed.create_for_user(
            db_session, user_id=test_user.id
        )
        old_token = created.token

        regenerated = await crud_calendar_feed.regenerate_token(
            db_session, db_obj=created
        )

        assert regenerated.token != old_token
        assert regenerated.is_enabled is True

    async def test_set_enabled(self, db_session: AsyncSession, test_user: User):
        """Test enabling and disabling a feed."""
        feed = await crud_calendar_feed.create_for_user(
            db_session, user_id=test_user.id
        )
        assert feed.is_enabled is True

        disabled = await crud_calendar_feed.set_enabled(
            db_session, db_obj=feed, enabled=False
        )
        assert disabled.is_enabled is False

        re_enabled = await crud_calendar_feed.set_enabled(
            db_session, db_obj=disabled, enabled=True
        )
        assert re_enabled.is_enabled is True

    async def test_update_last_accessed(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test updating the last accessed timestamp."""
        feed = await crud_calendar_feed.create_for_user(
            db_session, user_id=test_user.id
        )
        assert feed.last_accessed_at is None

        await crud_calendar_feed.update_last_accessed(db_session, db_obj=feed)

        refreshed = await crud_calendar_feed.get_by_user(
            db_session, user_id=test_user.id
        )
        assert refreshed is not None
        assert refreshed.last_accessed_at is not None
