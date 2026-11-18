"""The one way what people type into a shared list's form is cleaned.

Names, addresses and phone numbers of guests come only from that form. Anything
that stores or compares them goes through these functions, so "Anna  Müller"
and "anna müller " are the same person on a roster, and " A@Example.org" is the
address another sign-up already used.

Each raises ``ValueError`` for a value it cannot accept, so it serves as a
pydantic validator as well (``AfterValidator(normalize_name)``), which turns
that into a 422.
"""

import re
import unicodedata

from pydantic import validate_email

NAME_MIN_LENGTH = 2
NAME_MAX_LENGTH = 100
PHONE_MIN_LENGTH = 5
PHONE_MAX_LENGTH = 30
FIRST_NAME_MAX_LENGTH = 30

_PHONE = re.compile(r"[0-9+()/.\- ]+")


def normalize_name(value: str) -> str:
    """NFC, trimmed, every run of whitespace one space; 2 to 100 characters.

    Control characters are refused: PostgreSQL rejects a NUL in text, and the
    others have no business in a name on a roster.
    """
    name = " ".join(unicodedata.normalize("NFC", value).split())
    if any(unicodedata.category(ch) == "Cc" for ch in name):
        msg = "Name contains control characters"
        raise ValueError(msg)
    if not NAME_MIN_LENGTH <= len(name) <= NAME_MAX_LENGTH:
        msg = f"Name must be {NAME_MIN_LENGTH} to {NAME_MAX_LENGTH} characters"
        raise ValueError(msg)
    return name


def normalize_email(value: str) -> str:
    """Trimmed, validated as ``EmailStr`` is, and lower-cased.

    The validation also refuses more than 254 characters, which is what
    ``shared_list_guests.email`` holds. Lower-cased whole, the local part
    included, although mail servers may treat it as case-sensitive: nobody
    types their address the same way twice, and comparing addresses is what
    this is for. No provider-specific folding (Gmail's dots), which would merge
    addresses that are not the same.
    """
    _, email = validate_email(value.strip())
    return email.lower()


def normalize_phone(value: str) -> str:
    """Trimmed; digits, spaces and ``+ ( ) / - .`` only; 5 to 30 characters."""
    phone = value.strip()
    if not _PHONE.fullmatch(phone):
        msg = "Phone number may contain only digits, spaces and + ( ) / - ."
        raise ValueError(msg)
    if not PHONE_MIN_LENGTH <= len(phone) <= PHONE_MAX_LENGTH:
        msg = (
            f"Phone number must be {PHONE_MIN_LENGTH} to {PHONE_MAX_LENGTH} characters"
        )
        raise ValueError(msg)
    return phone


def first_name(name: str) -> str:
    """What the public page shows of a guest who agreed to it: the first word of
    their (normalised) name, at most 30 characters."""
    words = name.split(maxsplit=1)
    return words[0][:FIRST_NAME_MAX_LENGTH] if words else ""
