"""Route tests for Reporting endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.event import Event
from app.models.user import User


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
        assert "task_fill_rates" in data

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
        assert "total_tasks" in overview
        assert "total_shifts" in overview
        assert "total_shift_capacity" in overview
        assert "filled_shifts" in overview
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


@pytest.mark.asyncio
class TestReportingEventAdminRole:
    """Event-admin scoped access to /reporting/ endpoints."""

    async def test_reporting_overview_accessible_as_event_admin(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_event_admin: None,
    ):
        """Running an event is what unlocks reporting for it."""
        r = await async_client.get("/api/v1/reporting/overview")

        assert r.status_code == 200
        data = r.json()
        assert "overview" in data
        assert "task_fill_rates" in data

    async def test_reporting_export_accessible_as_event_admin(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_event_admin: None,
    ):
        """Test that an event admin can access the CSV export."""
        r = await async_client.get("/api/v1/reporting/export")

        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]

    async def test_reporting_blocked_for_plain_member(
        self,
        async_client: AsyncClient,
        test_event: Event,
    ):
        """Belonging to an event is not enough — you have to run one."""
        r = await async_client.get("/api/v1/reporting/overview")

        assert r.status_code == 403

    async def test_reporting_export_blocked_for_plain_member(
        self,
        async_client: AsyncClient,
        test_event: Event,
    ):
        """Same rule for the CSV export."""
        r = await async_client.get("/api/v1/reporting/export")

        assert r.status_code == 403

    async def test_event_admin_sees_only_their_events_tasks(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event_admin_user: User,
        test_event: Event,
        as_event_admin: None,
    ):
        """Stats cover the events the caller runs, and nothing outside them."""
        from datetime import date

        from app.models.event import Event as EventModel
        from app.models.task import Task as TaskModel

        mine = TaskModel(
            name="Task In My Event",
            start_date=date(2026, 6, 11),
            end_date=date(2026, 6, 11),
            status="published",
            created_by_id=test_event_admin_user.id,
            event_id=test_event.id,
        )
        # An event this user has nothing to do with.
        elsewhere = EventModel(
            name="Someone Else's Event",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
            status="published",
            visibility="private",
        )
        db_session.add_all([mine, elsewhere])
        await db_session.flush()
        db_session.add(
            TaskModel(
                name="Task Elsewhere",
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 1),
                status="published",
                event_id=elsewhere.id,
            )
        )
        await db_session.flush()

        r = await async_client.get("/api/v1/reporting/overview")

        assert r.status_code == 200
        overview = r.json()["overview"]
        assert overview["total_tasks"] >= 1

        fill_rates = r.json().get("task_fill_rates", [])
        names = [t["task_name"] for t in fill_rates]
        assert "Task Elsewhere" not in names
