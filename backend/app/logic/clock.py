"""The two clocks the application reads.

* :func:`utc_now` is for **stored timestamps** (``created_at``, expiry times):
  naive UTC, like every datetime column in the database.
* :func:`wall_clock_now` is for **comparing against shifts**. A shift's date
  and times are what the rota says ("Saturday, 18:00-22:00") and carry no
  zone. Comparing them with UTC would make an 18:00 shift in a German summer
  start at 20:00. So "now" is read in the zone of the event the shift belongs
  to (``events.timezone``) and the zone dropped, which puts both sides on the
  venue's wall clock.

:func:`wall_clock_to_utc` crosses from one to the other, for a moment the rota
names that something has to fire at, such as a reminder.

Both take the event's zone. ``None`` means ``settings.EVENT_TIMEZONE``, for a
task without an event; that setting is also what a new event starts with. A
view across events judges each shift on its own clock:
``app.crud.shift.wall_clocks`` and ``on_own_clock``.

Callers go through the module attribute (``clock.wall_clock_now(zone)``), never
a ``from ... import``, so a test patches one target:
``monkeypatch.setattr("app.logic.clock.wall_clock_now", lambda zone=None: ...)``.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from app.core.config import settings


def utc_now() -> dt.datetime:
    """Naive UTC, matching how every timestamp in the database is stored."""
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def wall_clock_now(zone: str | None = None) -> dt.datetime:
    """The wall-clock time in ``zone``, naive, for comparing with shift times."""
    return dt.datetime.now(ZoneInfo(zone or settings.EVENT_TIMEZONE)).replace(
        tzinfo=None
    )


def wall_clock_to_utc(wall_clock: dt.datetime, zone: str | None = None) -> dt.datetime:
    """A time on ``zone``'s wall clock as naive UTC, to store and compare as such."""
    return (
        wall_clock.replace(tzinfo=ZoneInfo(zone or settings.EVENT_TIMEZONE))
        .astimezone(dt.UTC)
        .replace(tzinfo=None)
    )
