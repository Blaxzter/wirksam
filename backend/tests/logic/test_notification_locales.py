"""The backend message files, en.json and de.json, say the same things.

The pre-commit parity hook only covers ``frontend/src/locales``. A key added
to one backend file and forgotten in the other degrades quietly: a missing
message falls back to English (``get_message``), and a missing e-mail string
falls back per key (``auth/emails.py::_chrome``), so nobody notices that German
readers get English. A placeholder spelled differently in one language is
worse: ``str.format`` raises ``KeyError`` and the trigger logs and drops the
notification for everyone who reads that language.
"""

import json
import string
from pathlib import Path
from typing import Any

import pytest

LOCALES = Path(__file__).parents[2] / "app" / "logic" / "notifications" / "locales"


def _load(lang: str) -> dict[str, Any]:
    with open(LOCALES / f"{lang}.json", encoding="utf-8") as f:
        return json.load(f)


def _fields(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


EN = _load("en")
DE = _load("de")


def test_no_other_locale_files() -> None:
    """A third language would need its own parity checks here."""
    assert sorted(p.stem for p in LOCALES.glob("*.json")) == ["de", "en"]


def test_same_messages() -> None:
    assert set(EN) - set(DE) == set(), "missing in de.json"
    assert set(DE) - set(EN) == set(), "missing in en.json"


def test_same_email_strings() -> None:
    assert set(EN["email"]) - set(DE["email"]) == set(), "missing in de.json"
    assert set(DE["email"]) - set(EN["email"]) == set(), "missing in en.json"


#: Blocks that are not a notification message: e-mail chrome, date names.
NOT_MESSAGES = {"email", "dates"}


@pytest.mark.parametrize("key", sorted(k for k in EN if k not in NOT_MESSAGES))
def test_each_message_has_a_title_a_body_and_the_same_placeholders(key: str) -> None:
    assert set(EN[key]) == {"title", "body"}
    assert set(DE[key]) == {"title", "body"}
    for part in ("title", "body"):
        assert _fields(EN[key][part]) == _fields(DE[key][part]), f"{key}.{part}"


@pytest.mark.parametrize("key", sorted(EN["email"]))
def test_each_email_string_has_the_same_placeholders(key: str) -> None:
    assert _fields(EN["email"][key]) == _fields(DE["email"][key]), key


def test_same_date_strings() -> None:
    assert set(EN["dates"]) == set(DE["dates"])


@pytest.mark.parametrize("lang", [EN, DE], ids=["en", "de"])
def test_a_name_for_every_weekday_and_month(lang: dict[str, Any]) -> None:
    assert len(lang["dates"]["weekdays"]) == 7
    assert len(lang["dates"]["months"]) == 12
    assert all(isinstance(name, str) and name for name in lang["dates"]["weekdays"])
    assert all(isinstance(name, str) and name for name in lang["dates"]["months"])


@pytest.mark.parametrize(
    "key", sorted(k for k, v in EN["dates"].items() if isinstance(v, str))
)
def test_each_date_template_has_the_same_placeholders(key: str) -> None:
    assert _fields(EN["dates"][key]) == _fields(DE["dates"][key]), key
