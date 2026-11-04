"""Unit tests for iCalendar feed generation."""

import datetime as dt
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import settings
from app.logic.calendar_feed import build_calendar


def _make_booking(
    slot_date: dt.date = dt.date(2026, 6, 1),
    start_time: dt.time | None = dt.time(9, 0),
    end_time: dt.time | None = dt.time(12, 0),
    title: str = "Test Shift",
    location: str = "Room A",
    category: str = "General",
    task_name: str = "Test Task",
    notes: str | None = None,
    status: str = "confirmed",
) -> SimpleNamespace:
    """Create a mock booking object with a shift."""
    task = SimpleNamespace(name=task_name)
    shift = SimpleNamespace(
        date=slot_date,
        start_time=start_time,
        end_time=end_time,
        title=title,
        location=location,
        category=category,
        task=task,
    )
    return SimpleNamespace(
        id="booking-001",
        status=status,
        shift=shift,
        notes=notes,
        created_at=dt.datetime(2026, 5, 1, 10, 0, tzinfo=dt.timezone.utc),
        updated_at=dt.datetime(2026, 5, 1, 10, 0, tzinfo=dt.timezone.utc),
    )


class TestBuildCalendar:
    """Test suite for build_calendar function."""

    def test_empty_bookings(self):
        """Test that empty bookings produce a valid calendar."""
        ical_bytes = build_calendar([])

        assert isinstance(ical_bytes, bytes)
        text = ical_bytes.decode("utf-8")
        assert "VCALENDAR" in text
        assert "VEVENT" not in text

    def test_single_booking(self):
        """Test a single confirmed booking."""
        bookings = [_make_booking()]
        ical_bytes = build_calendar(bookings)  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert "VEVENT" in text
        assert "Test Task: Test Shift" in text
        assert "CONFIRMED" in text

    def test_skips_cancelled_bookings(self):
        """Test that cancelled bookings are skipped."""
        bookings = [_make_booking(status="cancelled")]
        ical_bytes = build_calendar(bookings)  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert "VEVENT" not in text

    def test_skips_bookings_without_shift(self):
        """Test that bookings without a shift are skipped."""
        booking = SimpleNamespace(
            id="no-shift",
            status="confirmed",
            shift=None,
            created_at=dt.datetime.now(dt.timezone.utc),
            updated_at=None,
        )
        ical_bytes = build_calendar([booking])  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert "VEVENT" not in text

    def test_all_day_task(self):
        """Test that shifts without times become all-day tasks."""
        bookings = [_make_booking(start_time=None, end_time=None)]
        ical_bytes = build_calendar(bookings)  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert "VEVENT" in text
        # All-day tasks use DATE value type, not DATETIME
        assert "20260601" in text

    def test_shift_without_end_time(self):
        """Test that shifts with only start_time get a 1-hour duration."""
        bookings = [_make_booking(end_time=None)]
        ical_bytes = build_calendar(bookings)  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert "VEVENT" in text

    def test_location_included(self):
        """Test that location is included in the task."""
        bookings = [_make_booking(location="Room B")]
        ical_bytes = build_calendar(bookings)  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert "Room B" in text

    def test_custom_reminder_offsets(self):
        """Test that custom reminder offsets create VALARM components."""
        bookings = [_make_booking()]
        ical_bytes = build_calendar(bookings, reminder_offsets=[15, 60])  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert text.count("BEGIN:VALARM") == 2

    def test_default_reminder_fallback(self):
        """Test that no reminder_offsets falls back to 60-minute alarm."""
        bookings = [_make_booking()]
        ical_bytes = build_calendar(bookings, reminder_offsets=None)  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert "VALARM" in text

    def test_notes_in_description(self):
        """Test that booking notes are included in the description."""
        bookings = [_make_booking(notes="Bring your laptop")]
        ical_bytes = build_calendar(bookings)  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert "Bring your laptop" in text

    def test_multiple_bookings(self):
        """Test multiple bookings produce multiple tasks."""
        bookings = [
            _make_booking(title="Morning Shift"),
            _make_booking(title="Afternoon Shift", start_time=dt.time(14, 0)),
        ]
        ical_bytes = build_calendar(bookings)  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert text.count("BEGIN:VEVENT") == 2


def _in_zone(zone: str, **kwargs: Any) -> SimpleNamespace:
    booking = _make_booking(**kwargs)
    booking.shift.task.event = SimpleNamespace(timezone=zone)
    return booking


class TestTimeZones:
    def test_times_carry_the_events_zone(self) -> None:
        ics = build_calendar([_in_zone("Asia/Tokyo")]).decode()  # type: ignore[list-item]
        assert "DTSTART;TZID=Asia/Tokyo:20260601T090000" in ics
        assert "DTEND;TZID=Asia/Tokyo:20260601T120000" in ics

    def test_the_zone_is_described_ahead_of_the_events(self) -> None:
        ics = build_calendar([_in_zone("Europe/Lisbon")]).decode()  # type: ignore[list-item]
        assert ics.index("BEGIN:VTIMEZONE") < ics.index("BEGIN:VEVENT")
        assert "TZID:Europe/Lisbon" in ics

    def test_only_the_stretch_it_needs(self) -> None:
        """The library's default runs from 1970 to 2038, on every refresh."""
        ics = build_calendar([_in_zone("Europe/Berlin")]).decode()  # type: ignore[list-item]
        assert ics.count("BEGIN:DAYLIGHT") + ics.count("BEGIN:STANDARD") <= 2

    def test_a_task_without_an_event_uses_the_setting(self) -> None:
        ics = build_calendar([_make_booking()]).decode()  # type: ignore[list-item]
        assert f"DTSTART;TZID={settings.EVENT_TIMEZONE}:20260601T090000" in ics

    def test_several_zones_each_get_a_description(self) -> None:
        ics = build_calendar(
            [_in_zone("Asia/Tokyo"), _in_zone("Pacific/Honolulu")]  # type: ignore[list-item]
        ).decode()
        assert ics.count("BEGIN:VTIMEZONE") == 2

    def test_an_all_day_shift_has_no_zone(self) -> None:
        ics = build_calendar(
            [_in_zone("Asia/Tokyo", start_time=None, end_time=None)]  # type: ignore[list-item]
        ).decode()
        assert "TZID" not in ics
        assert "DTSTART;VALUE=DATE:20260601" in ics

    @pytest.mark.parametrize(
        "zone",
        [
            "UTC",
            "Etc/GMT+12",
            "Asia/Kathmandu",
            "Pacific/Apia",
            "Africa/Casablanca",
            "Australia/Lord_Howe",
            "America/St_Johns",
        ],
    )
    def test_an_unusual_zone_does_not_break_the_feed(self, zone: str) -> None:
        assert b"BEGIN:VEVENT" in build_calendar([_in_zone(zone)])  # type: ignore[list-item]


class TestOvernightShifts:
    def test_an_end_before_the_start_is_the_next_morning(self) -> None:
        ics = build_calendar(
            [_in_zone("Asia/Tokyo", start_time=dt.time(22), end_time=dt.time(2))]  # type: ignore[list-item]
        ).decode()
        assert "DTSTART;TZID=Asia/Tokyo:20260601T220000" in ics
        assert "DTEND;TZID=Asia/Tokyo:20260602T020000" in ics

    def test_a_shift_within_its_day_ends_on_it(self) -> None:
        ics = build_calendar([_in_zone("Asia/Tokyo")]).decode()  # type: ignore[list-item]
        assert "DTEND;TZID=Asia/Tokyo:20260601T120000" in ics
