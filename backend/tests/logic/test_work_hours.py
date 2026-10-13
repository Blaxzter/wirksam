"""Unit tests for the shift-length rules behind worked hours."""

import datetime as dt

from app.logic.work_hours import shift_ends_at, shift_minutes


class TestShiftMinutes:
    def test_daytime_shift(self):
        assert shift_minutes(dt.time(8, 0), dt.time(12, 30)) == 270

    def test_shift_past_midnight_wraps(self):
        """22:00–02:00 is four hours, not minus twenty."""
        assert shift_minutes(dt.time(22, 0), dt.time(2, 0)) == 240

    def test_equal_start_and_end_is_a_full_day(self):
        assert shift_minutes(dt.time(6, 0), dt.time(6, 0)) == 24 * 60

    def test_missing_times_count_as_zero(self):
        assert shift_minutes(None, dt.time(12, 0)) == 0
        assert shift_minutes(dt.time(8, 0), None) == 0
        assert shift_minutes(None, None) == 0


class TestShiftEndsAt:
    def test_same_day(self):
        assert shift_ends_at(
            dt.date(2026, 6, 1), dt.time(8, 0), dt.time(12, 0)
        ) == dt.datetime(2026, 6, 1, 12, 0)

    def test_overnight_ends_next_day(self):
        assert shift_ends_at(
            dt.date(2026, 6, 1), dt.time(22, 0), dt.time(2, 0)
        ) == dt.datetime(2026, 6, 2, 2, 0)

    def test_no_end_time_means_end_of_day(self):
        assert shift_ends_at(dt.date(2026, 6, 1), dt.time(8, 0), None) == (
            dt.datetime(2026, 6, 2, 0, 0)
        )
