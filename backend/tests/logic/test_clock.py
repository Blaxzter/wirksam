"""The two clocks (``app.logic.clock``) and the zone setting behind one of them."""

import datetime as dt

import pytest

from app.core.config import parse_timezone, settings
from app.logic import clock


def test_utc_now_is_naive_utc() -> None:
    now = clock.utc_now()
    assert now.tzinfo is None
    expected = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    assert abs(now - expected) < dt.timedelta(seconds=5)


def test_wall_clock_now_honours_event_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Twelve hours apart on the two sides of the date line, whatever the date."""
    monkeypatch.setattr(settings, "EVENT_TIMEZONE", "Etc/GMT+12")
    west = clock.wall_clock_now()
    monkeypatch.setattr(settings, "EVENT_TIMEZONE", "Etc/GMT-12")
    east = clock.wall_clock_now()
    assert west.tzinfo is None and east.tzinfo is None
    assert abs((east - west) - dt.timedelta(hours=24)) < dt.timedelta(seconds=5)


@pytest.mark.parametrize(
    ("wall_clock", "utc"),
    [
        # Berlin in winter is one hour ahead of UTC, in summer two.
        (dt.datetime(2026, 1, 15, 10, 0), dt.datetime(2026, 1, 15, 9, 0)),
        (dt.datetime(2026, 7, 15, 10, 0), dt.datetime(2026, 7, 15, 8, 0)),
        # Just after midnight is still the day before in UTC.
        (dt.datetime(2026, 1, 15, 0, 30), dt.datetime(2026, 1, 14, 23, 30)),
    ],
)
def test_wall_clock_to_utc(
    monkeypatch: pytest.MonkeyPatch, wall_clock: dt.datetime, utc: dt.datetime
) -> None:
    monkeypatch.setattr(settings, "EVENT_TIMEZONE", "Europe/Berlin")
    assert clock.wall_clock_to_utc(wall_clock) == utc


def test_the_default_zone_is_berlin() -> None:
    assert settings.EVENT_TIMEZONE == "Europe/Berlin"


def test_an_unknown_zone_refuses_to_boot() -> None:
    assert parse_timezone("Europe/Berlin") == "Europe/Berlin"
    for bad in ("Mars/Olympus_Mons", "", "../etc/passwd"):
        with pytest.raises(ValueError, match="EVENT_TIMEZONE"):
            parse_timezone(bad)
