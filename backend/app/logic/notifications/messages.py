"""Notification message translations loaded from JSON locale files."""

import datetime as dt
import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.logic import clock

DEFAULT_LANGUAGE = "en"

_LOCALES_DIR = Path(__file__).parent / "locales"

# Load all locale JSON files at import time
_messages: dict[str, dict[str, Any]] = {}
for locale_file in _LOCALES_DIR.glob("*.json"):
    lang = locale_file.stem
    with open(locale_file, encoding="utf-8") as f:
        _messages[lang] = json.load(f)


def _resolve_lang(language: str) -> str:
    """Return the language code if supported, otherwise fall back to default."""
    return language if language in _messages else DEFAULT_LANGUAGE


def get_message(type_code: str, language: str, **kwargs: str) -> tuple[str, str]:
    """Return (title, body) for a notification type in the given language.

    Falls back to English if the language is not found.
    kwargs are passed to str.format() on both templates, so a title can name
    the task it is about (``task.manager_added``) and two such notices don't
    read the same in the inbox or thread together as one e-mail subject.
    """
    lang = _resolve_lang(language)
    msg = _messages.get(lang, _messages[DEFAULT_LANGUAGE]).get(type_code)
    if not msg:
        # Graceful fallback: try English, then return raw type_code
        msg = _messages[DEFAULT_LANGUAGE].get(
            type_code, {"title": type_code, "body": ""}
        )

    title = msg["title"].format(**kwargs) if kwargs else msg["title"]
    body = msg["body"].format(**kwargs) if kwargs else msg["body"]
    return title, body


def get_email_strings(language: str) -> dict[str, str]:
    """Return email template strings for the given language."""
    lang = _resolve_lang(language)
    return _messages.get(lang, _messages[DEFAULT_LANGUAGE]).get(
        "email", _messages[DEFAULT_LANGUAGE]["email"]
    )


def quoted_list(names: list[str], lang: str) -> str:
    """Quote names and join them as prose, in the recipient's language.

    ``["Bar", "Grill", "Café"]`` reads “Bar”, “Grill” and “Café” in English and
    „Bar“, „Grill“ und „Café“ in German: German quotes open low, and neither
    language puts a comma before the last name. One name is just that name,
    quoted; none is an empty string. The names stay values, never part of a
    format string, so a task called ``{event_name}`` prints as typed.
    """
    if _resolve_lang(lang) == "de":
        quoted = [f"„{name}“" for name in names]
    else:
        quoted = [f"“{name}”" for name in names]
    return name_list(quoted, lang)


def name_list(names: list[str], lang: str) -> str:
    """Join names as prose without quoting them: ``Mira, Pia und Jonas``.

    For people, whose names need no quotes to stand out. No comma before the
    last name in either language; one name is just that name.
    """
    last_joiner = " und " if _resolve_lang(lang) == "de" else " and "
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + last_joiner + names[-1]


def get_date_strings(language: str) -> dict[str, Any]:
    """The ``dates`` block: weekday and month names and how a day is written.

    Falls back to English per key, as ``auth/emails.py::_chrome`` does for the
    e-mail strings, so a key missing from one file degrades to English rather
    than raising inside a mail being sent.
    """
    english: dict[str, Any] = _messages[DEFAULT_LANGUAGE]["dates"]
    return {**english, **_messages[_resolve_lang(language)].get("dates", {})}


def shift_times(
    start: dt.time | None, end: dt.time | None, zone: str | None
) -> dict[str, str]:
    """``start_time`` and ``end_time`` for a message that states a shift's time.

    Shift times are the event's wall clock. When the event isn't in the
    installation's zone, the zone follows the time so that someone elsewhere
    can't misread it: ``10:00–12:00 (Asia/Tokyo)``. Otherwise the wording is the
    same as ever. ``zone`` ``None`` is a task without an event.
    """
    note = ""
    if (start or end) and zone and zone != settings.EVENT_TIMEZONE:
        note = f" ({zone})"
    return {
        "start_time": start.strftime("%H:%M") if start else "",
        "end_time": (end.strftime("%H:%M") if end else "") + note,
    }


def day_span(
    first: dt.date,
    last: dt.date,
    language: str,
    *,
    today: dt.date | None = None,
    zone: str | None = None,
) -> str:
    """The days something runs, as a mail says them.

    ``Fr, 17. – So, 19. Juli`` and ``Fri 17 – Sun 19 July``; one day is
    ``Fr, 17. Juli``, two months ``Fr, 31. Juli – So, 2. August``. The year
    is added only when either end is outside the current one (on the wall
    clock of ``zone``, the event's), the rule ``formatDaySpan`` follows in the app, so a mail and
    the task page it links to read the same. The names and the order come
    from the ``dates`` block of the recipient's locale file.
    """
    if last < first:
        first, last = last, first
    strings = get_date_strings(language)
    if today is None:
        today = clock.wall_clock_now(zone).date()
    with_year = first.year != today.year or last.year != today.year

    def write(day: dt.date, template: str) -> str:
        return strings[template].format(
            weekday=strings["weekdays"][day.weekday()],
            day=day.day,
            month=strings["months"][day.month - 1],
            year=day.year,
        )

    full = "day_month_year" if with_year else "day_month"
    if first == last:
        return write(first, full)
    if first.year != last.year:
        start = write(first, "day_month_year")
    elif first.month != last.month:
        start = write(first, "day_month")
    else:
        start = write(first, "day")
    return strings["span"].format(first=start, last=write(last, full))


def format_time_until(offset_minutes: int, lang: str) -> str:
    """Human-readable time-until string for the ``booking.reminder`` body.

    Lives here rather than in ``reminder_poller`` because it is the wording of
    a message placeholder, and it has two callers: the poller that sends real
    reminders, and the sandbox seeder that writes a demo inbox. A demo whose
    reminder is phrased differently from the real one is a tell.
    """
    if offset_minutes < 60:
        if lang == "de":
            return f"in {offset_minutes} Minuten"
        return f"in {offset_minutes} minutes"
    hours = offset_minutes // 60
    remaining_mins = offset_minutes % 60
    if offset_minutes < 1440:
        if lang == "de":
            if remaining_mins:
                return f"in {hours} Std. {remaining_mins} Min."
            return f"in {hours} Stunde{'n' if hours > 1 else ''}"
        if remaining_mins:
            return f"in {hours}h {remaining_mins}min"
        return f"in {hours} hour{'s' if hours > 1 else ''}"
    days = offset_minutes // 1440
    if lang == "de":
        return f"in {days} Tag{'en' if days > 1 else ''}"
    return f"in {days} day{'s' if days > 1 else ''}"
