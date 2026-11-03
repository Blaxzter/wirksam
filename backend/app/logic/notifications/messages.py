"""Notification message translations loaded from JSON locale files."""

import datetime as dt
import json
from pathlib import Path
from typing import Any

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


def date_range(first: dt.date, last: dt.date) -> str:
    """``17.07.2026`` for one day, ``17.07.2026 – 19.07.2026`` for several.

    The date format ``booking.confirmed`` uses, the same in both languages.
    """
    if first == last:
        return first.strftime("%d.%m.%Y")
    return f"{first.strftime('%d.%m.%Y')} – {last.strftime('%d.%m.%Y')}"


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
