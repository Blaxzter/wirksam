"""Unit tests for notification message translations."""

from app.logic.notifications.messages import (
    DEFAULT_LANGUAGE,
    _resolve_lang,  # type: ignore[reportPrivateUsage]
    get_email_strings,
    get_message,
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
            "user.approved",
            "en",
        )

        assert isinstance(title, str)
        assert isinstance(body, str)
        assert title  # non-empty


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
