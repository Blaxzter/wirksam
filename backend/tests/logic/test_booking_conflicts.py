"""Unit tests for the shift-interval arithmetic behind booking.time_conflict."""

import datetime as dt

from app.logic.booking_conflicts import overlaps, shift_interval

DAY = dt.date(2026, 5, 24)


class TestShiftInterval:
    def test_same_day(self):
        assert shift_interval(DAY, dt.time(8), dt.time(12)) == (
            dt.datetime(2026, 5, 24, 8),
            dt.datetime(2026, 5, 24, 12),
        )

    def test_overnight_ends_next_day(self):
        assert shift_interval(DAY, dt.time(22), dt.time(2)) == (
            dt.datetime(2026, 5, 24, 22),
            dt.datetime(2026, 5, 25, 2),
        )

    def test_ending_at_midnight(self):
        assert shift_interval(DAY, dt.time(18), dt.time(0)) == (
            dt.datetime(2026, 5, 24, 18),
            dt.datetime(2026, 5, 25, 0),
        )

    def test_untimed_has_no_interval(self):
        assert shift_interval(DAY, None, None) is None
        assert shift_interval(DAY, dt.time(8), None) is None
        assert shift_interval(DAY, None, dt.time(12)) is None


class TestOverlaps:
    def _iv(self, start: int, end: int) -> tuple[dt.datetime, dt.datetime]:
        base = dt.datetime(2026, 5, 24)
        return base + dt.timedelta(hours=start), base + dt.timedelta(hours=end)

    def test_partial_overlap(self):
        assert overlaps(self._iv(8, 12), self._iv(10, 14))

    def test_contained(self):
        assert overlaps(self._iv(8, 12), self._iv(9, 10))

    def test_back_to_back_does_not_overlap(self):
        assert not overlaps(self._iv(8, 12), self._iv(12, 16))
        assert not overlaps(self._iv(12, 16), self._iv(8, 12))

    def test_disjoint(self):
        assert not overlaps(self._iv(8, 10), self._iv(14, 16))

    def test_overnight_against_next_morning(self):
        night = shift_interval(DAY, dt.time(22), dt.time(2))
        morning = shift_interval(DAY + dt.timedelta(days=1), dt.time(1), dt.time(5))
        assert night is not None and morning is not None
        assert overlaps(night, morning)
