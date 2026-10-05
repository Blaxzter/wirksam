import json
import warnings
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from pydantic import (
    AnyUrl,
    BeforeValidator,
    EmailStr,
    HttpUrl,
    computed_field,
    model_validator,
)
from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self

PROJECT_DIR = Path(__file__).parent.parent.parent.parent


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    elif isinstance(v, list):
        return v  # type: ignore[no-any-return]
    elif isinstance(v, str):
        return v
    raise ValueError(v)


def parse_domains(v: Any) -> list[str]:
    """Normalise an email-domain list: "@Example.org, b.org" -> ["example.org", "b.org"]."""
    items: list[Any]
    if isinstance(v, str):
        items = json.loads(v) if v.startswith("[") else v.split(",")
    elif isinstance(v, list):
        items = cast(list[Any], v)
    else:
        raise ValueError(v)
    cleaned = (str(item).strip().lstrip("@").lower() for item in items)
    return [domain for domain in cleaned if domain]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file=PROJECT_DIR / ".env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    FRONTEND_HOST: str = "http://localhost:5555"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    TESTING: bool | None = None

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 8432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> MultiHostUrl:
        return MultiHostUrl.build(
            scheme="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None  # type: ignore[assignment]

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME  # type: ignore[assignment]
        return self

    @model_validator(mode="after")
    def _resolve_testing_flag(self) -> Self:
        if self.TESTING is None:
            self.TESTING = self.ENVIRONMENT == "local"  # type: ignore[reportConstantRedefinition]
        if self.TESTING and self.ENVIRONMENT == "production":
            raise ValueError("TESTING=true is not allowed in production")
        return self

    # Authentication
    #
    # Access tokens are short-lived HS256 JWTs the client holds in memory;
    # refresh tokens are opaque, rotated on every use, and stored only as a
    # SHA-256 hash in `auth_sessions`. SECRET_KEY signs the access tokens.
    #
    # SECRET_KEY deliberately defaults to the sentinel "changethis" rather than
    # to a freshly minted `secrets.token_urlsafe(32)`. The image runs
    # `fastapi run --workers 4` (backend/Dockerfile), so a per-process random
    # default would hand four workers four different signing keys and roughly
    # three requests in four would fail verification — intermittently, and only
    # in production. It also has to have *some* default: four CI workflows do
    # `cp .env.example .env` before booting the backend, and a required field
    # with no default kills all four with a validation error before a single
    # test runs. The sentinel is caught instead by _enforce_non_default_secrets
    # at the bottom of this class, which warns locally and refuses to boot
    # anywhere else.
    SECRET_KEY: str = "changethis"
    # An access token cannot be revoked, so the only lever against a stolen one
    # is how long it stays useful. Fifteen minutes; the refresh token below
    # carries the long-lived, revocable half of the session.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PASSWORD_MIN_LENGTH: int = 8

    # Refresh-token cookie
    #
    # The cookie is host-only (no Domain attribute) and scoped to
    # f"{API_V1_STR}/auth". Do not add a Domain setting to "fix" a cross-site
    # deployment: the apex that hosts the API also hosts unrelated
    # applications, and a Domain cookie is sent to every one of them.
    REFRESH_COOKIE_NAME: str = "wirksam_refresh"
    REFRESH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    # None means "derive from ENVIRONMENT" (see _resolve_cookie_secure). Local
    # development is plain HTTP, where a Secure cookie is dropped without a
    # word; every deployed environment sits behind TLS at Traefik. An explicit
    # True or False in the env file still wins.
    REFRESH_COOKIE_SECURE: bool | None = None

    @model_validator(mode="after")
    def _resolve_cookie_secure(self) -> Self:
        if self.REFRESH_COOKIE_SECURE is None:
            self.REFRESH_COOKIE_SECURE = self.ENVIRONMENT != "local"  # type: ignore[reportConstantRedefinition]
        # Browsers reject SameSite=None without Secure outright. Left
        # unchecked, the combination yields a refresh cookie that is never
        # stored and a session that silently ends at the first refresh — a
        # failure that looks like a backend bug from every angle except this
        # one. Fail at startup instead.
        if self.REFRESH_COOKIE_SAMESITE == "none" and not self.REFRESH_COOKIE_SECURE:
            raise ValueError(
                "REFRESH_COOKIE_SAMESITE=none requires REFRESH_COOKIE_SECURE=True"
            )
        return self

    # Email-borne auth tokens
    #
    # A reset link is a password sitting in an inbox, so it expires within the
    # hour. A verification link grants nothing on its own — login is not
    # blocked on an unverified address — and is often opened a day later on
    # another device, so it gets the generous window.
    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 1
    EMAIL_VERIFY_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return self.ENVIRONMENT != "local"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_configured(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"

    SUPERADMIN_EMAILS: list[EmailStr] = []

    # Cloudflare Turnstile — the bot check in front of the open registration
    # form. The site key is public and lives on the frontend
    # (`window.__APP_CONFIG__`, from frontend/docker-entrypoint.sh); only the
    # secret belongs here. Leaving it unset disables enforcement outright, which
    # is what keeps local development and the test suite from needing a
    # Cloudflare account — see app/core/turnstile.py for why that gate is the
    # secret rather than ENVIRONMENT.
    TURNSTILE_SECRET_KEY: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def turnstile_enabled(self) -> bool:
        return bool(self.TURNSTILE_SECRET_KEY)

    # Who may create an account. The hosted instance runs open signup, but a
    # church or a club hosting its own copy usually wants a door on it. Three
    # settings, which combine:
    #
    # * REGISTRATION_MODE
    #   - "open": anyone may sign up and the account works immediately.
    #   - "approval": anyone may sign up, but the account waits in a queue until
    #     a superadmin approves or rejects it.
    #   - "invite": nobody may sign up without an event invitation, either the
    #     link they arrived through or an open invitation sent to their address.
    # * REGISTRATION_ALLOWED_DOMAINS limits self-signup to these email domains
    #   (an exact match on the part after the "@"). Empty means any domain.
    # * REGISTRATION_INVITE_BYPASS lets a valid invitation through both of the
    #   other restrictions: an invited address skips the approval queue and the
    #   domain list. An event admin who invites someone by name has already made
    #   the decision the queue exists for. In "invite" mode an invitation is
    #   required anyway, so there it only decides whether the domain list
    #   still applies to invited addresses.
    #
    # SUPERADMIN_EMAILS always get in, whatever the mode. Without that, an
    # "invite" or "approval" deployment would have no way to create the very
    # first administrator, who is the only one who could approve anyone.
    REGISTRATION_MODE: Literal["open", "approval", "invite"] = "open"
    # Typed ``list | str`` for the same reason as BACKEND_CORS_ORIGINS: a plain
    # ``list`` makes pydantic-settings JSON-decode the variable, and the
    # comma-separated form an operator actually writes is not JSON.
    REGISTRATION_ALLOWED_DOMAINS: Annotated[
        list[str] | str, BeforeValidator(parse_domains)
    ] = []
    REGISTRATION_INVITE_BYPASS: bool = True

    @property
    def registration_domains(self) -> list[str]:
        """The parsed domain list; ``parse_domains`` never leaves it a string."""
        domains = self.REGISTRATION_ALLOWED_DOMAINS
        return domains if isinstance(domains, list) else parse_domains(domains)

    # Sandbox demo — the "check out a test event" button.
    #
    # A sandbox is a throwaway guest account plus one seeded event, both hard-
    # deleted once SANDBOX_TTL_MINUTES have passed. Three knobs, because the
    # feature writes to the database on behalf of anonymous callers and each
    # one closes a different hole:
    #
    # * SANDBOX_ENABLED switches the endpoint off entirely (404). The frontend
    #   reads the same value through window.__APP_CONFIG__ so the landing page
    #   does not render a button that cannot work.
    # * SANDBOX_TTL_MINUTES is how long a demo lives. It is also the only thing
    #   standing between the feature and an ever-growing table, since the sweep
    #   is what actually reclaims the rows.
    # * SANDBOX_MAX_ACTIVE is a hard ceiling counted in the database. The rate
    #   limiter cannot serve as that ceiling: its counters are per worker
    #   process and it returns immediately when TESTING is set, so under four
    #   workers it permits four times the intended rate and under pytest it
    #   permits everything.
    SANDBOX_ENABLED: bool = True
    SANDBOX_TTL_MINUTES: int = 60
    SANDBOX_MAX_ACTIVE: int = 25

    # Web Push (VAPID) configuration
    VAPID_PRIVATE_KEY: str | None = None
    VAPID_PUBLIC_KEY: str | None = None
    VAPID_CLAIMS_EMAIL: str | None = None

    # Telegram Bot configuration
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_BOT_USERNAME: str | None = None

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        # `SECRET_KEY=changethis` is what four CI workflows get from
        # .env.example, so locally it may only be noisy. A deployment signing
        # its access tokens with a value published in this repository would let
        # anyone mint a token for any user, so outside local this refuses to
        # boot rather than warns.
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)

        # RFC 7518 §3.2: an HMAC key for HS256 must be at least as long as the
        # hash output, 32 bytes. PyJWT only warns, and a warning in a worker
        # process is a warning nobody reads — so a deployment whose key is
        # merely short (rather than literally "changethis") would sign tokens
        # that are cheaper to brute-force than the algorithm implies. Local
        # keeps the warning so .env.example still boots.
        if len(self.SECRET_KEY.encode("utf-8")) < 32:
            message = (
                "SECRET_KEY must be at least 32 bytes for HS256 (RFC 7518 3.2). "
                'Generate one with: python -c "import secrets; '
                'print(secrets.token_urlsafe(32))"'
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)
        return self


settings = Settings()  # type: ignore[call-arg]
