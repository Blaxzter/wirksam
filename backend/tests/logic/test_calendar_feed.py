"""Unit tests for iCalendar feed generation."""

import datetime as dt
from types import SimpleNamespace

from app.logic.calendar_feed import build_calendar


def _make_booking(
    slot_date: dt.date = dt.date(2026, 6, 1),
    start_time: dt.time | None = dt.time(9, 0),
    end_time: dt.time | None = dt.time(12, 0),
    title: str = "Test Slot",
    location: str = "Room A",
    category: str = "General",
    event_name: str = "Test Event",
    notes: str | None = None,
    status: str = "confirmed",
) -> SimpleNamespace:
    """Create a mock booking object with a duty_slot."""
    event = SimpleNamespace(name=event_name)
    slot = SimpleNamespace(
        date=slot_date,
        start_time=start_time,
        end_time=end_time,
        title=title,
        location=location,
        category=category,
        event=event,
    )
    return SimpleNamespace(
        id="booking-001",
        status=status,
        duty_slot=slot,
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
        assert "Test Event: Test Slot" in text
        assert "CONFIRMED" in text

    def test_skips_cancelled_bookings(self):
        """Test that cancelled bookings are skipped."""
        bookings = [_make_booking(status="cancelled")]
        ical_bytes = build_calendar(bookings)  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert "VEVENT" not in text

    def test_skips_bookings_without_slot(self):
        """Test that bookings without a slot are skipped."""
        booking = SimpleNamespace(
            id="no-slot",
            status="confirmed",
            duty_slot=None,
            created_at=dt.datetime.now(dt.timezone.utc),
            updated_at=None,
        )
        ical_bytes = build_calendar([booking])  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert "VEVENT" not in text

    def test_all_day_event(self):
        """Test that slots without times become all-day events."""
        bookings = [_make_booking(start_time=None, end_time=None)]
        ical_bytes = build_calendar(bookings)  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert "VEVENT" in text
        # All-day events use DATE value type, not DATETIME
        assert "20260601" in text

    def test_slot_without_end_time(self):
        """Test that slots with only start_time get a 1-hour duration."""
        bookings = [_make_booking(end_time=None)]
        ical_bytes = build_calendar(bookings)  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert "VEVENT" in text

    def test_location_included(self):
        """Test that location is included in the event."""
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
        """Test multiple bookings produce multiple events."""
        bookings = [
            _make_booking(title="Morning Shift"),
            _make_booking(title="Afternoon Shift", start_time=dt.time(14, 0)),
        ]
        ical_bytes = build_calendar(bookings)  # type: ignore[reportArgumentType]

        text = ical_bytes.decode("utf-8")
        assert text.count("BEGIN:VEVENT") == 2
