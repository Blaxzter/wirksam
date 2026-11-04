"""Unit tests for notification message translations."""

import datetime as dt

import pytest

from app.logic.notifications import messages
from app.logic.notifications.messages import (
    DEFAULT_LANGUAGE,
    _resolve_lang,  # type: ignore[reportPrivateUsage]
    day_span,
    get_date_strings,
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


class TestDaySpan:
    """The days a mail gives, as the approved mail design writes them."""

    TODAY = dt.date(2026, 7, 1)

    @pytest.mark.parametrize(
        ("first", "last", "lang", "expected"),
        [
            # The design's example, and one day of it.
            ((2026, 7, 17), (2026, 7, 19), "de", "Fr, 17. – So, 19. Juli"),
            ((2026, 7, 17), (2026, 7, 19), "en", "Fri 17 – Sun 19 July"),
            ((2026, 7, 17), (2026, 7, 17), "de", "Fr, 17. Juli"),
            ((2026, 7, 17), (2026, 7, 17), "en", "Fri 17 July"),
            # Across a month: both ends name theirs.
            ((2026, 7, 31), (2026, 8, 2), "de", "Fr, 31. Juli – So, 2. August"),
            ((2026, 7, 31), (2026, 8, 2), "en", "Fri 31 July – Sun 2 August"),
            # Outside this year, the year is said, once if both ends share it.
            ((2027, 3, 5), (2027, 3, 7), "de", "Fr, 5. – So, 7. März 2027"),
            ((2027, 3, 5), (2027, 3, 5), "en", "Fri 5 March 2027"),
            (
                (2026, 12, 31),
                (2027, 1, 1),
                "en",
                "Thu 31 December 2026 – Fri 1 January 2027",
            ),
            # An unknown language reads like English, as get_message falls back.
            ((2026, 7, 17), (2026, 7, 19), "fr", "Fri 17 – Sun 19 July"),
        ],
    )
    def test_writes_the_span(
        self,
        first: tuple[int, int, int],
        last: tuple[int, int, int],
        lang: str,
        expected: str,
    ) -> None:
        assert (
            day_span(dt.date(*first), dt.date(*last), lang, today=self.TODAY)
            == expected
        )

    def test_ends_given_backwards_are_put_in_order(self) -> None:
        assert (
            day_span(dt.date(2026, 7, 19), dt.date(2026, 7, 17), "en", today=self.TODAY)
            == "Fri 17 – Sun 19 July"
        )

    def test_this_year_is_read_on_the_events_wall_clock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.logic.clock.wall_clock_now", lambda: dt.datetime(2027, 1, 2, 9)
        )
        assert day_span(dt.date(2027, 3, 5), dt.date(2027, 3, 5), "en") == (
            "Fri 5 March"
        )
        assert day_span(dt.date(2026, 7, 17), dt.date(2026, 7, 17), "en") == (
            "Fri 17 July 2026"
        )

    def test_a_missing_name_falls_back_to_english(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A key left out of one file degrades to English, never raises."""
        german = dict(get_date_strings("de"))
        del german["months"]
        monkeypatch.setitem(
            messages._messages["de"],  # type: ignore[reportPrivateUsage]
            "dates",
            german,
        )
        assert (
            day_span(dt.date(2026, 7, 17), dt.date(2026, 7, 17), "de", today=self.TODAY)
            == "Fr, 17. July"
        )
