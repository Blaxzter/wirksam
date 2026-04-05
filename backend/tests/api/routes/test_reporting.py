"""Route tests for Reporting endpoints."""

import pytest
from httpx import AsyncClient

from app.models.booking import Booking


@pytest.mark.asyncio
class TestReportingRoutes:
    """Test suite for /reporting/ routes (admin only)."""

    async def test_reporting_overview(self, async_client: AsyncClient, as_admin: None):
        """Test the reporting overview endpoint."""
        r = await async_client.get("/api/v1/reporting/overview")

        assert r.status_code == 200
        data = r.json()
        assert "overview" in data
        assert "bookings_trend" in data
        assert "top_volunteers" in data
        assert "category_breakdown" in data
        assert "bookings_by_hour" in data
        assert "event_fill_rates" in data

    async def test_reporting_overview_stats_structure(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test that the overview stats have the expected fields."""
        r = await async_client.get("/api/v1/reporting/overview")

        assert r.status_code == 200
        overview = r.json()["overview"]
        assert "total_bookings" in overview
        assert "confirmed_bookings" in overview
        assert "cancelled_bookings" in overview
        assert "cancellation_rate" in overview
        assert "total_events" in overview
        assert "total_slots" in overview
        assert "total_slot_capacity" in overview
        assert "filled_slots" in overview
        assert "fill_rate" in overview
        assert "active_volunteers" in overview
        assert "total_volunteers" in overview

    async def test_reporting_overview_with_booking_data(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_booking: Booking,
    ):
        """Test that reporting overview includes booking data."""
        r = await async_client.get("/api/v1/reporting/overview")

        assert r.status_code == 200
        overview = r.json()["overview"]
        assert overview["total_bookings"] >= 1
        assert overview["confirmed_bookings"] >= 1

    async def test_reporting_overview_with_date_filter(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test the reporting overview with date filters."""
        r = await async_client.get(
            "/api/v1/reporting/overview",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )

        assert r.status_code == 200
        data = r.json()
        assert "overview" in data

    async def test_reporting_export_csv(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test the CSV export endpoint."""
        r = await async_client.get("/api/v1/reporting/export")

        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "bookings-report.csv" in r.headers.get("content-disposition", "")

    async def test_reporting_export_csv_has_header_row(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test that the CSV export has the expected header row."""
        r = await async_client.get("/api/v1/reporting/export")

        assert r.status_code == 200
        lines = r.text.strip().split("\n")
        assert len(lines) >= 1  # at least header
        header = lines[0]
        assert "Booking ID" in header
        assert "Status" in header
        assert "Volunteer Name" in header

    async def test_reporting_export_csv_with_data(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_booking: Booking,
    ):
        """Test that the CSV export includes booking data."""
        r = await async_client.get("/api/v1/reporting/export")

        assert r.status_code == 200
        lines = r.text.strip().split("\n")
        assert len(lines) >= 2  # header + at least one data row

    async def test_reporting_export_with_date_filter(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test CSV export with date filters."""
        r = await async_client.get(
            "/api/v1/reporting/export",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )

        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
