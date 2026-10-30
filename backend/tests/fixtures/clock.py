"""Pinning the event wall clock (``app.logic.clock.wall_clock_now``)."""

import datetime as dt
from collections.abc import Callable

import pytest

#: Before every fixture shift: ``tests/fixtures/shifts.py`` dates its shift
#: 2026-05-24 and the fixture events lie in June 2026, all of which is in the
#: past by now. Booking and cancelling refuse a shift that has ended
#: (``booking.shift_over``), so the modules that book through the API run
#: with the clock here.
BEFORE_FIXTURE_SHIFTS = dt.datetime(2026, 5, 1, 8, 0)


def set_wall_clock(monkeypatch: pytest.MonkeyPatch, now: dt.datetime) -> None:
    """Make ``clock.wall_clock_now()`` answer ``now`` for the rest of the test."""
    monkeypatch.setattr("app.logic.clock.wall_clock_now", lambda: now)


@pytest.fixture
def clock_before_fixture_shifts(monkeypatch: pytest.MonkeyPatch) -> dt.datetime:
    """The event wall clock at 2026-05-01 08:00, before every fixture shift.

    Apply it to a module with
    ``pytestmark = pytest.mark.usefixtures("clock_before_fixture_shifts")``.
    A test about ended shifts sets its own time with :func:`set_wall_clock`
    (or the ``wall_clock`` fixture), which overrides this one.
    """
    set_wall_clock(monkeypatch, BEFORE_FIXTURE_SHIFTS)
    return BEFORE_FIXTURE_SHIFTS


@pytest.fixture
def wall_clock(monkeypatch: pytest.MonkeyPatch) -> Callable[[dt.datetime], None]:
    """Set the event wall clock: ``wall_clock(dt.datetime(2026, 6, 11, 10, 0))``."""

    def _set(now: dt.datetime) -> None:
        set_wall_clock(monkeypatch, now)

    return _set
