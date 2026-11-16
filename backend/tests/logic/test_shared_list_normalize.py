"""``logic.shared_lists.normalize``: what people type into a list's form, cleaned
the one way everything compares it."""

import unicodedata
from typing import Annotated

import pytest
from pydantic import BaseModel, ValidationError
from pydantic.functional_validators import AfterValidator

from app.logic.shared_lists.normalize import (
    first_name,
    normalize_email,
    normalize_name,
    normalize_phone,
)


class TestNormalizeName:
    def test_trims_and_collapses_whitespace(self) -> None:
        assert normalize_name("  Anna \t  Maria\nMüller ") == "Anna Maria Müller"

    def test_composes_to_nfc(self) -> None:
        decomposed = unicodedata.normalize("NFD", "Jürgen")
        assert decomposed != "Jürgen"
        assert normalize_name(decomposed) == "Jürgen"

    @pytest.mark.parametrize("value", ["A", "  B  ", "x" * 101])
    def test_refuses_too_short_or_too_long(self, value: str) -> None:
        with pytest.raises(ValueError, match="2 to 100"):
            normalize_name(value)

    def test_the_bounds_are_inclusive(self) -> None:
        assert normalize_name("Al") == "Al"
        assert normalize_name("x" * 100) == "x" * 100

    def test_refuses_control_characters(self) -> None:
        """A NUL would be a 500 from PostgreSQL, not a 422."""
        with pytest.raises(ValueError, match="control"):
            normalize_name("Anna\x00Müller")


class TestNormalizeEmail:
    def test_trims_and_lowercases_all_of_it(self) -> None:
        assert (
            normalize_email("  Anna.Muster@Example.ORG ") == "anna.muster@example.org"
        )

    def test_no_provider_specific_folding(self) -> None:
        assert normalize_email("a.n.n.a+lists@gmail.com") == "a.n.n.a+lists@gmail.com"

    @pytest.mark.parametrize("value", ["", "anna", "anna@", "@example.org"])
    def test_refuses_what_is_not_an_address(self, value: str) -> None:
        with pytest.raises(ValueError):
            normalize_email(value)

    def test_at_most_254_characters(self) -> None:
        """What ``shared_list_guests.email`` holds."""
        longest = f"{'a' * 64}@{'b' * 63}.{'c' * 63}.{'d' * 57}.org"
        assert len(longest) == 254
        assert normalize_email(longest) == longest
        with pytest.raises(ValueError, match="too long"):
            normalize_email(longest.replace(".org", "d.org"))


class TestNormalizePhone:
    def test_trims_and_keeps_the_layout(self) -> None:
        assert normalize_phone("  +49 (030) 123-45/6.7 ") == "+49 (030) 123-45/6.7"

    @pytest.mark.parametrize("value", ["0171 12x45", "030;12345", "＋49 30 1234"])
    def test_refuses_other_characters(self, value: str) -> None:
        with pytest.raises(ValueError, match="only digits"):
            normalize_phone(value)

    @pytest.mark.parametrize("value", ["1234", "1" * 31])
    def test_refuses_too_short_or_too_long(self, value: str) -> None:
        with pytest.raises(ValueError, match="5 to 30"):
            normalize_phone(value)


class TestFirstName:
    def test_the_first_word(self) -> None:
        assert first_name("Anna Maria Müller") == "Anna"

    def test_at_most_thirty_characters(self) -> None:
        assert first_name("x" * 40 + " Müller") == "x" * 30

    def test_nothing_from_nothing(self) -> None:
        assert first_name("") == ""


def test_works_as_a_pydantic_validator() -> None:
    """How a request schema uses it: a refused value is a validation error."""

    class Form(BaseModel):
        name: Annotated[str, AfterValidator(normalize_name)]
        email: Annotated[str, AfterValidator(normalize_email)]

    form = Form(name=" Anna  Müller ", email="Anna@Example.org")
    assert (form.name, form.email) == ("Anna Müller", "anna@example.org")
    with pytest.raises(ValidationError):
        Form(name="A", email="anna@example.org")
    with pytest.raises(ValidationError):
        Form(name="Anna", email="not an address")
