"""The two clocks the application reads.

* :func:`utc_now` is for **stored timestamps** (``created_at``, expiry times):
  naive UTC, like every datetime column in the database.
* :func:`wall_clock_now` is for **comparing against shifts**. A shift's date
  and times are what the rota says ("Saturday, 18:00-22:00") and carry no
  zone. Comparing them with UTC would make an 18:00 shift in a German summer
  start at 20:00. So "now" is read in ``settings.EVENT_TIMEZONE`` and the zone
  dropped, which puts both sides on the venue's wall clock.

Callers go through the module attribute (``clock.wall_clock_now()``), never a
``from ... import``, so a test patches one target:
``monkeypatch.setattr("app.logic.clock.wall_clock_now", lambda: ...)``.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from app.core.config import settings


def utc_now() -> dt.datetime:
    """Naive UTC, matching how every timestamp in the database is stored."""
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def wall_clock_now() -> dt.datetime:
    """The events' wall-clock time, naive, for comparing with shift times."""
    return dt.datetime.now(ZoneInfo(settings.EVENT_TIMEZONE)).replace(tzinfo=None)
