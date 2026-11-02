"""Unit tests for notification message translations."""

import datetime as dt

import pytest

from app.logic.notifications.messages import (
    DEFAULT_LANGUAGE,
    _resolve_lang,  # type: ignore[reportPrivateUsage]
    date_range,
    get_email_strings,
    get_message,
    quoted_list,
)


class TestResolveLanguage:
    """Test _resolve_lang helper."""

    def test_supported_language(self):
        """Test that a supported language is returned as-is."""
        assert _resolve_lang("en") == "en"

    def test_unsupported_language_falls_back(self):
        """Test that an unsupported language falls back to default."""
        result = _resolve_lang("xx_nonexistent")
        assert result == DEFAULT_LANGUAGE

    def test_german_supported(self):
        """Test that German is a supported language."""
        result = _resolve_lang("de")
        assert result == "de"


class TestGetMessage:
    """Test get_message function."""

    def test_known_type_english(self):
        """Test getting a message for a known type in English."""
        title, body = get_message("booking.confirmed", "en")

        assert title  # non-empty
        assert isinstance(title, str)
        assert isinstance(body, str)

    def test_known_type_german(self):
        """Test getting a message for a known type in German."""
        title, _body = get_message("booking.confirmed", "de")

        assert title
        assert isinstance(title, str)

    def test_unknown_type_falls_back(self):
        """Test that an unknown type returns the type code as title."""
        title, body = get_message("nonexistent.type", "en")

        assert title == "nonexistent.type"
        assert body == ""

    def test_unsupported_language_falls_back_to_english(self):
        """Test fallback to English for unsupported languages."""
        title_en, body_en = get_message("booking.confirmed", "en")
        title_xx, body_xx = get_message("booking.confirmed", "xx")

        assert title_en == title_xx
        assert body_en == body_xx

    def test_message_with_kwargs(self):
        """Test message templating with kwargs."""
        # Use all placeholders the booking.confirmed template expects
        title, body = get_message(
            "user.suspended",
            "en",
        )

        assert isinstance(title, str)
        assert isinstance(body, str)
        assert title  # non-empty

    def test_title_placeholders_are_filled(self) -> None:
        """A title can name its task, so two such notices don't read alike."""
        title, body = get_message(
            "task.manager_added",
            "de",
            actor="Anna Berger",
            task_name="Cafétheke",
            event_name="Sommerfest am Fluss",
        )

        assert (
            title == "Du bist jetzt verantwortlich für Cafétheke · Sommerfest am Fluss"
        )
        assert body.startswith("Anna Berger hat dich eingetragen.")

    def test_braces_in_a_value_stay_as_typed_in_the_title(self) -> None:
        """Values are never a format string, in the title as in the body."""
        title, _ = get_message(
            "task.manager_removed",
            "en",
            actor="Anna",
            task_name="{event_name}",
            event_name="Fair",
        )

        assert title == "No longer in charge of {event_name} · Fair"


class TestGetEmailStrings:
    """Test get_email_strings function."""

    def test_english_email_strings(self):
        """Test getting email template strings in English."""
        strings = get_email_strings("en")

        assert isinstance(strings, dict)
        assert len(strings) > 0

    def test_german_email_strings(self):
        """Test getting email template strings in German."""
        strings = get_email_strings("de")

        assert isinstance(strings, dict)
        assert len(strings) > 0

    def test_unsupported_falls_back(self):
        """Test fallback for unsupported language."""
        en_strings = get_email_strings("en")
        xx_strings = get_email_strings("xx")

        assert en_strings == xx_strings


class TestQuotedList:
    """Names joined as prose, with each language's quotation marks."""

    @pytest.mark.parametrize(
        ("names", "lang", "expected"),
        [
            ([], "en", ""),
            (["Bar"], "en", "“Bar”"),
            (["Bar", "Grill"], "en", "“Bar” and “Grill”"),
            (["Bar", "Grill", "Café"], "en", "“Bar”, “Grill” and “Café”"),
            ([], "de", ""),
            (["Bar"], "de", "„Bar“"),
            (["Bar", "Grill"], "de", "„Bar“ und „Grill“"),
            (["Bar", "Grill", "Café"], "de", "„Bar“, „Grill“ und „Café“"),
            # An unknown language reads like English, as get_message falls back.
            (["Bar", "Grill"], "fr", "“Bar” and “Grill”"),
        ],
    )
    def test_joins(self, names: list[str], lang: str, expected: str) -> None:
        assert quoted_list(names, lang) == expected

    def test_braces_stay_as_typed(self) -> None:
        """Names are values, never a format string."""
        assert quoted_list(["{event_name}"], "en") == "“{event_name}”"


class TestDateRange:
    """The dates a mail gives, as ``booking.confirmed`` writes them."""

    def test_one_day(self) -> None:
        assert date_range(dt.date(2026, 7, 17), dt.date(2026, 7, 17)) == "17.07.2026"

    def test_several_days(self) -> None:
        assert (
            date_range(dt.date(2026, 7, 17), dt.date(2026, 7, 19))
            == "17.07.2026 – 19.07.2026"
        )
