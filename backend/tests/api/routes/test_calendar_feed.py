"""Route tests for Calendar Feed endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.calendar_feed import crud_calendar_feed
from app.models.user import User


@pytest.mark.asyncio
class TestCalendarFeedRoutes:
    """Test suite for /calendar/ routes."""

    async def test_get_feed_settings_none(self, async_client: AsyncClient):
        """Test getting feed settings when no feed exists."""
        r = await async_client.get("/api/v1/calendar/feed-settings")

        assert r.status_code == 200
        assert r.json() is None

    async def test_enable_feed(self, async_client: AsyncClient):
        """Test enabling the calendar feed."""
        r = await async_client.post("/api/v1/calendar/feed-settings")

        assert r.status_code == 200
        data = r.json()
        assert data["is_enabled"] is True
        assert "feed_url" in data

    async def test_get_feed_settings_after_enable(self, async_client: AsyncClient):
        """Test getting feed settings after enabling."""
        await async_client.post("/api/v1/calendar/feed-settings")

        r = await async_client.get("/api/v1/calendar/feed-settings")

        assert r.status_code == 200
        data = r.json()
        assert data is not None
        assert data["is_enabled"] is True

    async def test_regenerate_feed(self, async_client: AsyncClient):
        """Test regenerating the feed token."""
        # Enable first
        r1 = await async_client.post("/api/v1/calendar/feed-settings")
        old_url = r1.json()["feed_url"]

        # Regenerate
        r2 = await async_client.post("/api/v1/calendar/feed-settings/regenerate")

        assert r2.status_code == 200
        assert r2.json()["feed_url"] != old_url

    async def test_regenerate_feed_without_enable(self, async_client: AsyncClient):
        """Test regenerating without enabling first returns 404."""
        r = await async_client.post("/api/v1/calendar/feed-settings/regenerate")
        assert r.status_code == 404

    async def test_disable_feed(self, async_client: AsyncClient):
        """Test disabling the calendar feed."""
        await async_client.post("/api/v1/calendar/feed-settings")

        r = await async_client.delete("/api/v1/calendar/feed-settings")
        assert r.status_code == 204

    async def test_disable_feed_idempotent(self, async_client: AsyncClient):
        """Test disabling when no feed exists is a no-op."""
        r = await async_client.delete("/api/v1/calendar/feed-settings")
        assert r.status_code == 204

    async def test_public_feed_endpoint(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test the public .ics feed endpoint with a valid token."""
        feed = await crud_calendar_feed.create_for_user(
            db_session, user_id=test_user.id
        )

        r = await async_client.get(f"/api/v1/calendar/feed/{feed.token}.ics")

        assert r.status_code == 200
        assert "text/calendar" in r.headers["content-type"]

    async def test_public_feed_invalid_token(self, async_client: AsyncClient):
        """Test the public .ics feed with an invalid token."""
        r = await async_client.get("/api/v1/calendar/feed/invalid-token.ics")
        assert r.status_code == 404
