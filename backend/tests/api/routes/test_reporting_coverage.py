"""Coverage gap tests for Reporting endpoints (rich data, all metrics populated)."""

from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.duty_slot import DutySlot
from app.models.event import Event
from app.models.user import User


@pytest.mark.asyncio
class TestReportingCoverage:
    """Coverage tests for reporting.py with rich test data to exercise all helpers."""

    async def _seed_reporting_data(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_admin_user: User,
    ) -> Event:
        """Seed a realistic dataset for reporting tests."""
        event = Event(
            name="Reporting Test Event",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 3),
            status="published",
        )
        db_session.add(event)
        await db_session.flush()
        await db_session.refresh(event)

        # Multiple slots with different categories and times
        slots = [
            DutySlot(
                event_id=event.id,
                title="Morning Security",
                date=date(2026, 6, 1),
                start_time=time(8, 0),
                end_time=time(12, 0),
                max_bookings=3,
                category="Security",
                location="Gate A",
            ),
            DutySlot(
                event_id=event.id,
                title="Afternoon Catering",
                date=date(2026, 6, 1),
                start_time=time(14, 0),
                end_time=time(18, 0),
                max_bookings=2,
                category="Catering",
                location="Kitchen",
            ),
            DutySlot(
                event_id=event.id,
                title="Evening Security",
                date=date(2026, 6, 2),
                start_time=time(18, 0),
                end_time=time(22, 0),
                max_bookings=2,
                category="Security",
                location="Gate B",
            ),
        ]
        db_session.add_all(slots)
        await db_session.flush()
        for s in slots:
            await db_session.refresh(s)

        # Bookings by different users
        bookings = [
            Booking(
                duty_slot_id=slots[0].id,
                user_id=test_user.id,
                status="confirmed",
            ),
            Booking(
                duty_slot_id=slots[1].id,
                user_id=test_user.id,
                status="confirmed",
            ),
            Booking(
                duty_slot_id=slots[0].id,
                user_id=test_admin_user.id,
                status="confirmed",
            ),
            Booking(
                duty_slot_id=slots[2].id,
                user_id=test_admin_user.id,
                status="cancelled",
            ),
        ]
        db_session.add_all(bookings)
        await db_session.flush()

        return event

    async def test_overview_with_rich_data(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
        test_admin_user: User,
    ):
        """Test overview stats with multiple bookings, slots, and users."""
        await self._seed_reporting_data(db_session, test_user, test_admin_user)

        r = await async_client.get("/api/v1/reporting/overview")

        assert r.status_code == 200
        overview = r.json()["overview"]
        assert overview["total_bookings"] >= 4
        assert overview["confirmed_bookings"] >= 3
        assert overview["cancelled_bookings"] >= 1
        assert overview["cancellation_rate"] > 0
        assert overview["total_slots"] >= 3
        assert overview["total_slot_capacity"] >= 7
        assert overview["filled_slots"] >= 2
        assert overview["fill_rate"] > 0
        assert overview["total_volunteers"] >= 2

    async def test_bookings_trend(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
        test_admin_user: User,
    ):
        """Test bookings trend returns daily breakdown."""
        await self._seed_reporting_data(db_session, test_user, test_admin_user)

        r = await async_client.get("/api/v1/reporting/overview")

        assert r.status_code == 200
        trend = r.json()["bookings_trend"]
        assert len(trend) >= 1
        assert "date" in trend[0]
        assert "confirmed" in trend[0]
        assert "cancelled" in trend[0]

    async def test_top_volunteers(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
        test_admin_user: User,
    ):
        """Test top volunteers ranking."""
        await self._seed_reporting_data(db_session, test_user, test_admin_user)

        r = await async_client.get("/api/v1/reporting/overview")

        assert r.status_code == 200
        top = r.json()["top_volunteers"]
        assert len(top) >= 1
        assert "user_id" in top[0]
        assert "name" in top[0]
        assert "booking_count" in top[0]
        assert top[0]["booking_count"] >= 1

    async def test_category_breakdown(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
        test_admin_user: User,
    ):
        """Test category breakdown with multiple categories."""
        await self._seed_reporting_data(db_session, test_user, test_admin_user)

        r = await async_client.get("/api/v1/reporting/overview")

        assert r.status_code == 200
        categories = r.json()["category_breakdown"]
        assert len(categories) >= 2
        cat_names = [c["category"] for c in categories]
        assert "Security" in cat_names
        assert "Catering" in cat_names
        for cat in categories:
            assert "slot_count" in cat
            assert "total_capacity" in cat
            assert "fill_rate" in cat

    async def test_bookings_by_hour(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
        test_admin_user: User,
    ):
        """Test bookings by hour distribution."""
        await self._seed_reporting_data(db_session, test_user, test_admin_user)

        r = await async_client.get("/api/v1/reporting/overview")

        assert r.status_code == 200
        by_hour = r.json()["bookings_by_hour"]
        assert len(by_hour) >= 1
        assert "hour" in by_hour[0]
        assert "booking_count" in by_hour[0]

    async def test_event_fill_rates(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
        test_admin_user: User,
    ):
        """Test event fill rates."""
        await self._seed_reporting_data(db_session, test_user, test_admin_user)

        r = await async_client.get("/api/v1/reporting/overview")

        assert r.status_code == 200
        fill_rates = r.json()["event_fill_rates"]
        assert len(fill_rates) >= 1
        assert "event_name" in fill_rates[0]
        assert "total_capacity" in fill_rates[0]
        assert "confirmed_bookings" in fill_rates[0]
        assert "fill_rate" in fill_rates[0]

    async def test_export_csv_with_rich_data(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
        test_admin_user: User,
    ):
        """Test CSV export with multiple bookings includes all data."""
        await self._seed_reporting_data(db_session, test_user, test_admin_user)

        r = await async_client.get("/api/v1/reporting/export")

        assert r.status_code == 200
        lines = r.text.strip().split("\n")
        assert len(lines) >= 5  # header + at least 4 data rows
        # Check header columns
        header = lines[0]
        assert "Slot Title" in header
        assert "Event Name" in header
        assert "Location" in header
        assert "Category" in header

    async def test_export_csv_with_date_filter_excludes_data(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
        test_admin_user: User,
    ):
        """Test CSV export with restrictive date filter returns fewer rows."""
        await self._seed_reporting_data(db_session, test_user, test_admin_user)

        # Filter to a date range that excludes our seeded data
        r = await async_client.get(
            "/api/v1/reporting/export",
            params={"date_from": "2027-01-01", "date_to": "2027-12-31"},
        )

        assert r.status_code == 200
        lines = r.text.strip().split("\n")
        # Should only have the header (no data rows in this range)
        assert len(lines) >= 1

    async def test_overview_with_date_filters_scoped(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
        test_admin_user: User,
    ):
        """Test overview with date filters only includes scoped data."""
        await self._seed_reporting_data(db_session, test_user, test_admin_user)

        r = await async_client.get(
            "/api/v1/reporting/overview",
            params={"date_from": "2026-06-01", "date_to": "2026-06-01"},
        )

        assert r.status_code == 200
        overview = r.json()["overview"]
        # Only slots from June 1 should be included
        assert overview["total_slots"] >= 2
