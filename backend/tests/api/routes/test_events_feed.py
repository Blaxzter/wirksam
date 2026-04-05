"""Route tests for Event Feed endpoints."""

import pytest
from httpx import AsyncClient

from app.models.booking import Booking
from app.models.duty_slot import DutySlot
from app.models.event import Event


@pytest.mark.asyncio
class TestEventFeedRoutes:
    """Test suite for /events/feed routes."""

    async def test_event_feed_list_view(
        self, async_client: AsyncClient, test_event: Event, test_duty_slot: DutySlot
    ):
        """Test the event feed in list view mode."""
        r = await async_client.get("/api/v1/events/feed", params={"view": "list"})

        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert "skip" in data
        assert "limit" in data

    async def test_event_feed_cards_view(
        self, async_client: AsyncClient, test_event: Event
    ):
        """Test the event feed in cards view mode."""
        r = await async_client.get("/api/v1/events/feed", params={"view": "cards"})

        assert r.status_code == 200
        data = r.json()
        assert "items" in data

    async def test_event_feed_calendar_view(
        self, async_client: AsyncClient, test_event: Event
    ):
        """Test the event feed in calendar view mode."""
        r = await async_client.get(
            "/api/v1/events/feed",
            params={
                "view": "calendar",
                "date_from": "2026-05-01",
                "date_to": "2026-05-31",
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert "items" in data

    async def test_event_feed_with_search(
        self, async_client: AsyncClient, test_event: Event
    ):
        """Test the event feed with a search query."""
        r = await async_client.get(
            "/api/v1/events/feed",
            params={"search": test_event.name[:5]},
        )

        assert r.status_code == 200

    async def test_event_feed_my_bookings_filter(
        self, async_client: AsyncClient, test_booking: Booking
    ):
        """Test the my_bookings filter in event feed."""
        r = await async_client.get("/api/v1/events/feed", params={"my_bookings": True})

        assert r.status_code == 200

    async def test_event_feed_pagination(self, async_client: AsyncClient):
        """Test event feed pagination parameters."""
        r = await async_client.get(
            "/api/v1/events/feed",
            params={"skip": 0, "limit": 5},
        )

        assert r.status_code == 200
        data = r.json()
        assert data["skip"] == 0
        assert data["limit"] == 5

    async def test_event_feed_empty(self, async_client: AsyncClient):
        """Test event feed when no events match."""
        r = await async_client.get(
            "/api/v1/events/feed",
            params={"search": "zzz_nonexistent_zzz"},
        )

        assert r.status_code == 200
        assert r.json()["total"] == 0
        assert r.json()["items"] == []

    async def test_event_feed_focus_mode_first_available(
        self, async_client: AsyncClient, test_event: Event, test_duty_slot: DutySlot
    ):
        """Test the event feed with first_available focus mode."""
        r = await async_client.get(
            "/api/v1/events/feed",
            params={"view": "list", "focus_mode": "first_available"},
        )

        assert r.status_code == 200

    async def test_event_active_dates(
        self, async_client: AsyncClient, test_event: Event, test_duty_slot: DutySlot
    ):
        """Test the active dates endpoint."""
        r = await async_client.get(
            "/api/v1/events/active-dates",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )

        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_event_slot_window(
        self, async_client: AsyncClient, test_event: Event, test_duty_slot: DutySlot
    ):
        """Test the slot window endpoint for a specific event."""
        r = await async_client.get(
            f"/api/v1/events/{test_event.id}/slot-window",
            params={"start_date": "2026-05-01", "days": 7},
        )

        assert r.status_code == 200
        data = r.json()
        assert "slots" in data
        assert "start_date" in data
        assert "days" in data
