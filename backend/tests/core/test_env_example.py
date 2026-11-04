"""What someone gets who copies ``.env.example`` and changes what the docs say."""

import pytest

from app.core.config import PROJECT_DIR, Settings


def test_sentry_stays_off_until_someone_sets_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A placeholder here isn't harmless: ``sentry_sdk.init`` refuses it, which
    stops the backend as soon as ``ENVIRONMENT`` isn't ``local``. Compose passes
    the line on as an empty variable, which ``env_ignore_empty`` reads as unset.
    """
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    settings = Settings(_env_file=PROJECT_DIR / ".env.example")  # type: ignore[call-arg]

    assert settings.SENTRY_DSN is None


def test_an_empty_variable_from_compose_also_means_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTRY_DSN", "")

    settings = Settings(_env_file=PROJECT_DIR / ".env.example")  # type: ignore[call-arg]

    assert settings.SENTRY_DSN is None
