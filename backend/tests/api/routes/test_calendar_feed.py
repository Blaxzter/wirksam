"""Route tests for Calendar Feed endpoints."""

import datetime as dt

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.calendar_feed import crud_calendar_feed
from app.models.booking import Booking
from app.models.event import Event
from app.models.shift import Shift
from app.models.task import Task
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


@pytest.mark.asyncio
class TestFeedTimeZones:
    """The route has to load each booking's event, or every entry is in the setting."""

    async def _book(
        self, db: AsyncSession, user: User, event: Event | None, zone_note: str
    ) -> None:
        task = Task(
            name=f"Task {zone_note}",
            start_date=dt.date(2030, 7, 1),
            end_date=dt.date(2030, 7, 31),
            status="published",
            created_by_id=user.id,
            event_id=event.id if event else None,
        )
        db.add(task)
        await db.flush()
        shift = Shift(
            task_id=task.id,
            title=f"Shift {zone_note}",
            date=dt.date(2030, 7, 10),
            start_time=dt.time(22, 0),
            end_time=dt.time(2, 0),
            max_bookings=1,
        )
        db.add(shift)
        await db.flush()
        db.add(Booking(shift_id=shift.id, user_id=user.id, status="confirmed"))
        await db.flush()

    async def _feed(self, client: AsyncClient, db: AsyncSession, user: User) -> str:
        token = await crud_calendar_feed.create_for_user(db, user_id=user.id)
        r = await client.get(f"/api/v1/calendar/feed/{token.token}.ics")
        assert r.status_code == 200, r.text
        return r.text.replace("\r\n", "\n")

    async def test_each_entry_carries_its_events_zone(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        test_event.timezone = "Asia/Tokyo"
        db_session.add(test_event)
        await self._book(db_session, test_user, test_event, "in Tokyo")

        ics = await self._feed(async_client, db_session, test_user)

        assert "DTSTART;TZID=Asia/Tokyo:20300710T220000" in ics
        assert "TZID:Asia/Tokyo" in ics

    async def test_an_overnight_shift_ends_the_next_morning(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        test_event.timezone = "Asia/Tokyo"
        db_session.add(test_event)
        await self._book(db_session, test_user, test_event, "overnight")

        ics = await self._feed(async_client, db_session, test_user)

        assert "DTEND;TZID=Asia/Tokyo:20300711T020000" in ics

    async def test_a_task_without_an_event_uses_the_setting(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        await self._book(db_session, test_user, None, "without an event")

        ics = await self._feed(async_client, db_session, test_user)

        assert f"DTSTART;TZID={settings.EVENT_TIMEZONE}:20300710T220000" in ics
