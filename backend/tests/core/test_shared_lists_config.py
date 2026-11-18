"""The shared-list settings, and the boot warning when a deployment runs the lists
without Turnstile in front of their sign-up form."""

import warnings
from typing import Any

import pytest

from app.core.config import Settings


def _settings(**overrides: Any) -> Settings:
    """Settings as a deployment outside ``local`` reads them.

    CI's .env is a copy of .env.example, whose S3 example key refuses to boot
    there, hence the Postgres storage.
    """
    values: dict[str, Any] = {
        "ENVIRONMENT": "production",
        "TESTING": False,
        "SECRET_KEY": "x" * 32,
        "STORAGE_BACKEND": "postgres",
        **overrides,
    }
    return Settings(**values)


def test_the_defaults() -> None:
    """What .env.example and docs/deployment.md promise."""
    defaults = {
        name: Settings.model_fields[name].default
        for name in (
            "SHARED_LISTS_ENABLED",
            "GUEST_DATA_RETENTION_DAYS",
            "GUEST_SIGNUPS_PER_ADDRESS_PER_DAY",
            "GUEST_SIGNUP_EVENTS_PER_ADDRESS_PER_DAY",
            "GUEST_MAILS_PER_ADDRESS_PER_DAY",
            "GUEST_MAILS_PER_EVENT_PER_DAY",
            "GUEST_MAILS_PER_ORGANISER_PER_DAY",
            "SHARED_LIST_SIGNUPS_PER_LIST_PER_DAY",
            "SHARED_LISTS_PER_EVENT",
        )
    }
    assert defaults == {
        "SHARED_LISTS_ENABLED": True,
        "GUEST_DATA_RETENTION_DAYS": 30,
        "GUEST_SIGNUPS_PER_ADDRESS_PER_DAY": 20,
        "GUEST_SIGNUP_EVENTS_PER_ADDRESS_PER_DAY": 3,
        "GUEST_MAILS_PER_ADDRESS_PER_DAY": 10,
        "GUEST_MAILS_PER_EVENT_PER_DAY": 1000,
        "GUEST_MAILS_PER_ORGANISER_PER_DAY": 2000,
        "SHARED_LIST_SIGNUPS_PER_LIST_PER_DAY": 500,
        "SHARED_LISTS_PER_EVENT": 200,
    }


def test_a_deployment_without_turnstile_is_warned() -> None:
    with pytest.warns(UserWarning, match="SHARED_LISTS_ENABLED without TURNSTILE"):
        _settings(TURNSTILE_SECRET_KEY=None)


@pytest.mark.parametrize(
    "overrides",
    [
        {"TURNSTILE_SECRET_KEY": "secret"},
        {"TURNSTILE_SECRET_KEY": None, "SHARED_LISTS_ENABLED": False},
        # Local development and the test suite run without Turnstile.
        {"TURNSTILE_SECRET_KEY": None, "ENVIRONMENT": "local", "TESTING": True},
    ],
)
def test_no_warning_with_turnstile_without_the_lists_or_locally(
    overrides: dict[str, Any],
) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _settings(**overrides)
