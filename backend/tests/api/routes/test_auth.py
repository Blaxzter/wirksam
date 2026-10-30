"""End-to-end tests for the endpoints that hand out and take away credentials.

These are written against HTTP rather than against ``app.logic.auth`` because
in this corner of the application the transport *is* half the behaviour. A
login that returns the right body but forgets the ``HttpOnly`` flag, a refresh
that rotates the row but not the cookie, a logout that clears a cookie at the
wrong path — every one of those is a real bug that a service-level test cannot
see. So each test here drives ``unauthenticated_client``, which runs the whole
dependency chain for real: no ``CurrentUser`` override, no impersonation
header, a genuine ``Authorization: Bearer`` and a genuine cookie jar.

Three mechanics are worth knowing before reading further:

* **The raw tokens exist only in flight.** Both token tables store a sha256, so
  a test cannot read a verification or reset secret back out of the database.
  The ``outbox`` fixture below intercepts the mails the routes schedule, which
  is the only way to follow a link the way its recipient would.
* **``other_client`` is a second browser**, not a second user. Its own cookie
  jar is what makes "this device" versus "my other devices" testable at all —
  and that distinction is the entire point of session revocation.
* **Status codes carry meaning.** 401 means "prove who you are", 403 means "not
  allowed", and 404 — for a session belonging to somebody else — means "you
  cannot even see this", matching ``logic.permissions.require_event_visible``.
  Asserting the ``auth.*`` code alongside the status is what pins the
  frontend's ``errorCodes`` translations to something real.
"""

import uuid
from collections.abc import AsyncGenerator, Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import auth as auth_routes
from app.core.config import settings
from app.core.rate_limit import (
    forgot_password_limiter,
    login_limiter,
    register_limiter,
    resend_verification_limiter,
    reset_password_limiter,
)
from app.core.security import hash_token
from app.crud.auth_session import auth_session as crud_auth_session
from app.crud.user import user as crud_user
from app.crud.user_token import user_token as crud_user_token
from app.logic.auth.tokens import issue_user_token
from app.models.user import User
from tests.fixtures.auth import AuthHeadersFactory
from tests.fixtures.users import TEST_USER_PASSWORD

AUTH = f"{settings.API_V1_STR}/auth"

# A password that is not the fixtures' password, and comfortably longer than any
# plausible PASSWORD_MIN_LENGTH so that raising the setting does not quietly
# turn every happy path in this file into a 422.
NEW_PASSWORD = "a-completely-different-password"

# 36 umlauts: 36 characters, exactly 72 bytes. Sits on bcrypt's ceiling from the
# inside, and is the reason the policy has to measure bytes — the same string
# measured in characters is only half way to the limit.
UMLAUT_PASSWORD_AT_LIMIT = "ä" * 36

# 40 umlauts: 80 bytes, still only 40 characters. Must be refused.
UMLAUT_PASSWORD_OVER_LIMIT = "ä" * 40


def _naive_utc_now() -> datetime:
    """The house datetime: UTC, with the tzinfo taken off again."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Mail capture ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SentMail:
    """One token-bearing mail a route handed to ``BackgroundTasks``."""

    kind: str
    email: str
    name: str | None
    token: str
    language: str


@pytest.fixture(autouse=True)
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[SentMail]:
    """Capture verification and reset mails instead of sending them.

    Autouse, and deliberately not optional. Locally ``SMTP_HOST`` points at the
    mailcatcher container, so an un-stubbed test would open a real socket from
    inside a background task — slow when it works and slower when it does not.

    It is also the only way to obtain a live token. ``user_tokens`` stores a
    sha256, so the secret that goes into the link exists exactly once, in the
    argument list of the call recorded here. Tests that redeem a link read it
    from this list; tests that must prove *nothing* was sent assert that the
    list stayed empty, which is a far stronger statement than "the endpoint
    answered 202".
    """
    sent: list[SentMail] = []

    def _recorder(kind: str) -> Callable[..., Coroutine[Any, Any, bool]]:
        async def _record(
            *, email: str, name: str | None, token: str, language: str
        ) -> bool:
            sent.append(
                SentMail(
                    kind=kind, email=email, name=name, token=token, language=language
                )
            )
            return True

        return _record

    monkeypatch.setattr(auth_routes, "send_verify_email", _recorder("verify_email"))
    monkeypatch.setattr(
        auth_routes, "send_password_reset_email", _recorder("reset_password")
    )
    return sent


@pytest.fixture(autouse=True)
def fresh_rate_limit_windows() -> None:
    """Start every test in this file with empty rate-limit counters.

    ``RateLimiter.check`` short-circuits while ``settings.TESTING`` is true —
    which it is for the whole suite, since every ``.env.example`` CI copies sets
    ``ENVIRONMENT=local`` — so today this resets counters that were never
    incremented.

    It is here because the counters are module-level and shared across tests.
    If that flag were ever false, this file would run past "5 registrations per
    hour per IP" somewhere in the middle of ``TestRegister`` and every test
    after it would fail with a 429 having nothing to do with what it asserts.
    """
    for limiter in (
        login_limiter,
        register_limiter,
        forgot_password_limiter,
        reset_password_limiter,
        resend_verification_limiter,
    ):
        limiter.reset()


@pytest_asyncio.fixture
async def other_client(
    unauthenticated_app: FastAPI,
) -> AsyncGenerator[AsyncClient, None]:
    """A second browser: same application, same database, its own cookie jar.

    "Sign out this device but not that one" is not expressible with a single
    client — two logins through one jar simply overwrite each other's cookie,
    and the test would pass against an implementation that revoked everything.
    """
    transport = ASGITransport(app=unauthenticated_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ── Helpers ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SignedIn:
    """What a successful sign-in leaves a test holding."""

    access_token: str
    refresh_token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


def _refresh_cookie(client: AsyncClient) -> str | None:
    """The refresh token currently in this client's jar, if any."""
    return client.cookies.get(settings.REFRESH_COOKIE_NAME)


def _replay(client: AsyncClient, token: str) -> None:
    """Arm the client with an arbitrary refresh token, discarding its own.

    The jar is cleared first on purpose. Adding a second cookie of the same
    name at a different path sends both, and the server then reads whichever
    one ``SimpleCookie`` happened to parse last — a test that passes or fails
    by dictionary ordering.
    """
    client.cookies.clear()
    client.cookies.set(settings.REFRESH_COOKIE_NAME, token)


async def _sign_in(
    client: AsyncClient,
    *,
    email: str,
    password: str = TEST_USER_PASSWORD,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> SignedIn:
    """Log in through the real endpoint and keep both halves of the credential."""
    headers: dict[str, str] = {}
    if user_agent is not None:
        headers["User-Agent"] = user_agent
    if ip_address is not None:
        headers["X-Forwarded-For"] = ip_address

    response = await client.post(
        f"{AUTH}/login",
        json={"email": email, "password": password},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return SignedIn(
        access_token=str(response.json()["access_token"]),
        refresh_token=_refresh_cookie(client) or "",
    )


async def _register(
    client: AsyncClient,
    *,
    email: str,
    password: str = NEW_PASSWORD,
    name: str = "New Comer",
    preferred_language: str | None = None,
    turnstile_token: str | None = None,
) -> Response:
    """POST /auth/register with the fields a registration form would send."""
    body: dict[str, Any] = {"email": email, "password": password, "name": name}
    if preferred_language is not None:
        body["preferred_language"] = preferred_language
    if turnstile_token is not None:
        body["turnstile_token"] = turnstile_token
    return await client.post(f"{AUTH}/register", json=body)


def _error_locations(payload: Any) -> list[str]:
    """Flatten a 422 problem body into the field names it complains about."""
    return [str(part) for error in payload["errors"] for part in error["loc"]]


# ── Registration ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRegister:
    """``POST /auth/register`` — the only way an account comes into existence.

    Just-in-time provisioning went away with the external issuer, so this
    endpoint is now the single door into the system. That makes two of its
    properties security-relevant rather than cosmetic: the uniqueness check has
    to agree with the ``lower(email)`` index (or two accounts race into one
    address and neither can be reasoned about), and the password ceiling has to
    be measured the way bcrypt measures it (or an over-long password reaches
    ``hash_password`` and returns a 500 instead of a field error).
    """

    async def test_creates_an_account_and_signs_it_in(
        self, unauthenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test that a new account comes back signed in, with a usable token."""
        response = await _register(
            unauthenticated_client, email="newcomer@example.com", name="New Comer"
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        assert body["user"]["email"] == "newcomer@example.com"
        assert body["user"]["name"] == "New Comer"
        assert body["user"]["email_verified"] is False
        assert body["user"]["is_active"] is True

        created = await crud_user.get_by_email(db_session, email="newcomer@example.com")
        assert created is not None
        assert created.password_hash, "the chosen password must have been stored"
        assert created.password_hash != NEW_PASSWORD, "and stored hashed"
        assert created.subject.startswith("local|")

        # The access token is real: it opens an authenticated endpoint.
        sessions = await unauthenticated_client.get(
            f"{AUTH}/sessions",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        assert sessions.status_code == 200
        assert len(sessions.json()) == 1

    async def test_refresh_token_goes_out_only_as_a_host_only_cookie(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Test that the long-lived half is httpOnly, path-scoped and undomained.

        A ``Domain`` attribute would broadcast a live session credential to
        every other application on the shared apex, and a refresh token in the
        JSON body would be readable by any script on the page — the two
        mistakes this cookie's attributes exist to prevent.
        """
        response = await _register(unauthenticated_client, email="cookie@example.com")

        assert response.status_code == 201, response.text
        assert "refresh_token" not in response.json()

        raw_cookie = response.headers["set-cookie"]
        assert raw_cookie.startswith(f"{settings.REFRESH_COOKIE_NAME}=")
        assert "HttpOnly" in raw_cookie
        assert f"Path={settings.API_V1_STR}/auth" in raw_cookie
        assert "Domain=" not in raw_cookie
        assert _refresh_cookie(unauthenticated_client)

    async def test_schedules_a_verification_mail(
        self, unauthenticated_client: AsyncClient, outbox: list[SentMail]
    ) -> None:
        """Test that registering mails a verification link that actually works."""
        response = await _register(
            unauthenticated_client,
            email="verifyme@example.com",
            preferred_language="de",
        )
        assert response.status_code == 201, response.text

        assert len(outbox) == 1
        mail = outbox[0]
        assert mail.kind == "verify_email"
        assert mail.email == "verifyme@example.com"
        assert mail.language == "de"

        redeemed = await unauthenticated_client.post(
            f"{AUTH}/verify-email", json={"token": mail.token}
        )
        assert redeemed.status_code == 204

    async def test_duplicate_email_is_rejected(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Test that a second registration for the same address is a 409."""
        first = await _register(unauthenticated_client, email="taken@example.com")
        assert first.status_code == 201, first.text

        second = await _register(unauthenticated_client, email="taken@example.com")
        assert second.status_code == 409
        assert second.json()["code"] == "auth.email_taken"

    async def test_duplicate_detection_is_case_insensitive(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Test that ``A@b.com`` collides with ``a@b.com``.

        Addresses are case-insensitive in practice, and the database agrees:
        ``ix_users_email_lower`` is a unique index on ``lower(email)``. If the
        application check compared raw strings instead, this second request
        would pass its check and then fail on the index — a 500 for what is
        plainly "you already have an account".
        """
        first = await _register(unauthenticated_client, email="A@b.com")
        assert first.status_code == 201, first.text

        second = await _register(unauthenticated_client, email="a@b.com")
        assert second.status_code == 409
        assert second.json()["code"] == "auth.email_taken"

    async def test_collides_with_an_existing_account_regardless_of_case(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that an existing row is found even when the case differs."""
        assert test_user.email is not None

        response = await _register(
            unauthenticated_client, email=test_user.email.upper()
        )

        assert response.status_code == 409
        assert response.json()["code"] == "auth.email_taken"

    async def test_password_below_the_minimum_is_a_field_error(
        self, unauthenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test that a short password is refused as 422 against ``password``."""
        response = await _register(
            unauthenticated_client, email="short@example.com", password="a" * 4
        )

        assert response.status_code == 422
        assert "password" in _error_locations(response.json())
        assert (
            await crud_user.get_by_email(db_session, email="short@example.com") is None
        )

    async def test_password_over_72_bytes_is_refused(
        self, unauthenticated_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test that the ceiling counts bytes, not characters.

        Forty umlauts are forty characters and eighty bytes. A check written
        against ``len(password)`` waves this through, ``bcrypt.hashpw`` then
        raises ``ValueError`` — since 5.0 it no longer truncates silently — and
        a German-speaking user gets a 500 while an English-speaking one with the
        same number of characters registers fine.
        """
        assert len(UMLAUT_PASSWORD_OVER_LIMIT) == 40
        assert len(UMLAUT_PASSWORD_OVER_LIMIT.encode("utf-8")) == 80

        response = await _register(
            unauthenticated_client,
            email="umlaut-over@example.com",
            password=UMLAUT_PASSWORD_OVER_LIMIT,
        )

        assert response.status_code == 422
        assert "password" in _error_locations(response.json())
        assert (
            await crud_user.get_by_email(db_session, email="umlaut-over@example.com")
            is None
        )

    async def test_password_of_exactly_72_bytes_is_accepted(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Test that the boundary itself is inside the limit, and can sign in.

        The complement of the test above: a rule that rejects 80 bytes but also
        rejects 72 would be indistinguishable from one that counts characters
        and stops at 36.
        """
        assert len(UMLAUT_PASSWORD_AT_LIMIT.encode("utf-8")) == 72

        registered = await _register(
            unauthenticated_client,
            email="umlaut-limit@example.com",
            password=UMLAUT_PASSWORD_AT_LIMIT,
        )
        assert registered.status_code == 201, registered.text

        signed_in = await unauthenticated_client.post(
            f"{AUTH}/login",
            json={
                "email": "umlaut-limit@example.com",
                "password": UMLAUT_PASSWORD_AT_LIMIT,
            },
        )
        assert signed_in.status_code == 200

    async def test_a_configured_superadmin_address_bootstraps_the_platform_admin(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that registering a listed address grants the ``admin`` role.

        This is the whole bootstrap story for a fresh deployment: no row holds
        ``admin``, every route that could grant it is itself behind
        ``CurrentSuperuser``, and so the only way in is to register with an
        address named in ``SUPERADMIN_EMAILS``. Lose this and a new installation
        has no administrator and no way to appoint one.

        The configured address is spelled in a different case on purpose — an
        operator who typed it with a capital letter must not be silently left
        without the role.
        """
        monkeypatch.setattr(settings, "SUPERADMIN_EMAILS", ["Boss@Example.com"])

        response = await _register(unauthenticated_client, email="boss@example.com")

        assert response.status_code == 201, response.text
        assert response.json()["user"]["roles"] == ["admin"]
        assert response.json()["user"]["is_admin"] is True

        created = await crud_user.get_by_email(db_session, email="boss@example.com")
        assert created is not None
        assert created.roles == ["admin"]

    async def test_an_ordinary_address_gains_no_roles(
        self, unauthenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that signing up grants nothing on its own."""
        monkeypatch.setattr(settings, "SUPERADMIN_EMAILS", ["boss@example.com"])

        response = await _register(unauthenticated_client, email="nobody@example.com")

        assert response.status_code == 201, response.text
        assert response.json()["user"]["roles"] == []
        assert response.json()["user"]["event_roles"] == {}


@pytest.mark.asyncio
class TestRegisterTurnstile:
    """The bot check in front of the one endpoint that creates accounts.

    ``verify_turnstile`` itself is covered in ``tests/core/test_turnstile.py``;
    what matters here is the wiring around it — that the gate is the *secret*
    and not the environment, that a refusal is a translatable 403 rather than a
    422 about a field nobody typed, and above all that a rejected challenge
    leaves no account behind. A check that blocks the response but has already
    written the row protects nothing.
    """

    @pytest.fixture
    def turnstile_verdict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> Callable[[bool], list[str | None]]:
        """Configure a secret and pin what Cloudflare would have answered."""

        def install(passes: bool) -> list[str | None]:
            tokens: list[str | None] = []

            async def fake_verify(token: str | None) -> bool:
                tokens.append(token)
                return passes

            monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", "test-secret")
            monkeypatch.setattr(auth_routes, "verify_turnstile", fake_verify)
            return tokens

        return install

    async def test_is_skipped_when_no_secret_is_configured(
        self, unauthenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that a deployment without Turnstile registers as it always did.

        This is the default everywhere but production: no Cloudflare account is
        needed to run the stack locally, and the E2E suite registers through the
        real form without solving anything.
        """
        monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", None)

        response = await _register(
            unauthenticated_client, email="nocaptcha@example.com"
        )

        assert response.status_code == 201, response.text

    async def test_lets_a_solved_challenge_through(
        self,
        unauthenticated_client: AsyncClient,
        turnstile_verdict: Callable[[bool], list[str | None]],
    ) -> None:
        """Test that the token from the form is the one that gets verified."""
        tokens = turnstile_verdict(True)

        response = await _register(
            unauthenticated_client,
            email="solved@example.com",
            turnstile_token="a-solved-token",
        )

        assert response.status_code == 201, response.text
        assert tokens == ["a-solved-token"]

    async def test_refuses_a_failed_challenge_with_a_translatable_code(
        self,
        unauthenticated_client: AsyncClient,
        turnstile_verdict: Callable[[bool], list[str | None]],
    ) -> None:
        """Test that a rejection is a 403 carrying ``auth.captcha_failed``.

        403 rather than 422: nothing the person typed is wrong. The frontend
        renders the code through its ``errorCodes`` namespace, so a code with no
        entry there would surface as a raw string on the registration form.
        """
        turnstile_verdict(False)

        response = await _register(
            unauthenticated_client,
            email="blocked@example.com",
            turnstile_token="a-forged-token",
        )

        assert response.status_code == 403, response.text
        assert response.json()["code"] == "auth.captcha_failed"

    async def test_refuses_a_request_that_carries_no_token_at_all(
        self,
        unauthenticated_client: AsyncClient,
        turnstile_verdict: Callable[[bool], list[str | None]],
    ) -> None:
        """Test that omitting the field is a refusal, not a bypass.

        The schema allows the field to be absent so that deployments without
        Turnstile need not invent one — which would be a hole if the route read
        "absent" as "not applicable". It asks the verifier either way, and the
        verifier refuses an empty token.
        """
        tokens = turnstile_verdict(False)

        response = await _register(unauthenticated_client, email="silent@example.com")

        assert response.status_code == 403, response.text
        assert tokens == [None]

    async def test_creates_no_account_when_the_challenge_fails(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        outbox: list[SentMail],
        turnstile_verdict: Callable[[bool], list[str | None]],
    ) -> None:
        """Test that a blocked registration leaves nothing behind.

        Not just no row: no verification mail either. Registration is the one
        endpoint that will send a message to any address a stranger names, and
        an account created before the check would still be an account.
        """
        turnstile_verdict(False)

        response = await _register(
            unauthenticated_client, email="ghost@example.com", turnstile_token="nope"
        )

        assert response.status_code == 403
        assert (
            await crud_user.get_by_email(db_session, email="ghost@example.com") is None
        )
        assert outbox == []

    async def test_the_rate_limit_still_applies_underneath(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        turnstile_verdict: Callable[[bool], list[str | None]],
    ) -> None:
        """Test that Turnstile is a second gate, not a replacement for the first.

        The limiter runs first and is cheap; a caller that solves challenges
        (a headless browser will) still cannot mint accounts without a ceiling.
        """
        turnstile_verdict(True)
        monkeypatch.setattr(settings, "TESTING", False)
        register_limiter.reset()

        for index in range(register_limiter.limit):
            allowed = await _register(
                unauthenticated_client,
                email=f"burst{index}@example.com",
                turnstile_token="solved",
            )
            assert allowed.status_code == 201, allowed.text

        refused = await _register(
            unauthenticated_client,
            email="one-too-many@example.com",
            turnstile_token="solved",
        )
        assert refused.status_code == 429
        assert refused.json()["code"] == "auth.rate_limited"


# ── Sign-in ───────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestLogin:
    """``POST /auth/login`` — the credential check, and what it must not reveal.

    Every negative case in this class asserts the *same* answer. That sameness
    is the feature: a volunteer-scheduling app's user list says who is involved
    in what, so an endpoint that distinguishes "no such account" from "wrong
    password" is an oracle for exactly that. The one case that would otherwise
    stand out is an account with no password at all — bcrypt raises on an empty
    hash, and a 500 there would announce "this address exists" more loudly than
    any error message could.
    """

    async def test_successful_login_returns_a_token_and_sets_the_cookie(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that valid credentials yield an access token and a refresh cookie."""
        assert test_user.email is not None

        response = await unauthenticated_client.post(
            f"{AUTH}/login",
            json={"email": test_user.email, "password": TEST_USER_PASSWORD},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["user"]["id"] == str(test_user.id)
        assert body["user"]["sub"] == test_user.subject
        assert "refresh_token" not in body
        assert "HttpOnly" in response.headers["set-cookie"]
        assert _refresh_cookie(unauthenticated_client)

    async def test_email_is_matched_case_insensitively(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that a shouted address signs in as the same account."""
        assert test_user.email is not None

        response = await unauthenticated_client.post(
            f"{AUTH}/login",
            json={"email": test_user.email.upper(), "password": TEST_USER_PASSWORD},
        )

        assert response.status_code == 200, response.text
        assert response.json()["user"]["id"] == str(test_user.id)

    async def test_wrong_password_is_rejected(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that a bad password is a 401 and leaves no cookie behind."""
        assert test_user.email is not None

        response = await unauthenticated_client.post(
            f"{AUTH}/login",
            json={"email": test_user.email, "password": "not-the-password"},
        )

        assert response.status_code == 401
        assert response.json()["code"] == "auth.invalid_credentials"
        assert _refresh_cookie(unauthenticated_client) is None

    async def test_unknown_address_answers_exactly_like_a_wrong_password(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that neither response says whether the account exists.

        Compared byte for byte rather than field by field, because anything
        that differs — a code, a sentence, a header — is enough to enumerate
        the membership of every event this application hosts.
        """
        assert test_user.email is not None

        wrong_password = await unauthenticated_client.post(
            f"{AUTH}/login",
            json={"email": test_user.email, "password": "not-the-password"},
        )
        unknown_account = await unauthenticated_client.post(
            f"{AUTH}/login",
            json={"email": "nobody-here@example.com", "password": "not-the-password"},
        )

        assert unknown_account.status_code == wrong_password.status_code == 401
        assert unknown_account.content == wrong_password.content

    async def test_account_without_a_password_is_refused_cleanly(
        self, unauthenticated_client: AsyncClient, test_passwordless_user: User
    ) -> None:
        """Test that a NULL ``password_hash`` is a 401 and not a 500.

        Demo accounts and every row predating local authentication have no hash
        at all. ``bcrypt.checkpw`` raises ``ValueError: Invalid salt`` on an
        empty string, so without the guard in ``verify_password`` this exact
        request would return an unhandled-exception 500 — which, unlike a 401,
        tells the caller that the address is real.
        """
        assert test_passwordless_user.email is not None

        response = await unauthenticated_client.post(
            f"{AUTH}/login",
            json={
                "email": test_passwordless_user.email,
                "password": "anything-at-all",
            },
        )

        assert response.status_code == 401
        assert response.json()["code"] == "auth.invalid_credentials"

    async def test_a_suspended_account_may_still_sign_in(
        self, unauthenticated_client: AsyncClient, test_inactive_user: User
    ) -> None:
        """Test that suspension is an authorisation state, not a credential one.

        The tokens open nothing — ``CurrentUser`` refuses an inactive user on
        every protected route — but signing in is what lets the frontend read
        the profile behind ``AnyUser`` and explain *why* the account is on hold,
        instead of rejecting a correct password with no reason given.
        """
        assert test_inactive_user.email is not None

        response = await unauthenticated_client.post(
            f"{AUTH}/login",
            json={"email": test_inactive_user.email, "password": TEST_USER_PASSWORD},
        )

        assert response.status_code == 200, response.text
        assert response.json()["user"]["is_active"] is False

    async def test_superadmin_promotion_also_happens_on_sign_in(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that an address added to the list after signup is still promoted.

        The realistic order of events: someone deploys, registers, discovers
        there are no admin screens, and only then puts their address in the env
        file. Promoting on registration alone would mean deleting the account
        and making it again.
        """
        assert test_user.email is not None
        monkeypatch.setattr(settings, "SUPERADMIN_EMAILS", [test_user.email])

        response = await unauthenticated_client.post(
            f"{AUTH}/login",
            json={"email": test_user.email, "password": TEST_USER_PASSWORD},
        )

        assert response.status_code == 200, response.text
        assert response.json()["user"]["roles"] == ["admin"]

        await db_session.refresh(test_user)
        assert test_user.roles == ["admin"]


# ── Refresh ───────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRefresh:
    """``POST /auth/refresh`` — rotation, and the theft detection built on it.

    Rotation is only worth its extra row per refresh if the *old* value stops
    working, so the two halves are tested separately: that the client gets a
    new cookie, and that the previous one is dead. Together they turn a stolen
    cookie from a permanent key into a race the thief has to keep winning.

    The reuse case is the reason revoked rows are kept rather than deleted. A
    token that matches a dead session means the secret was in two places at
    once, so the account is treated as compromised and every session it owns is
    closed — including the one the legitimate client is holding, which is the
    intended and unavoidable cost.
    """

    async def test_rotates_the_cookie_and_mints_a_new_access_token(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that refreshing swaps the cookie for a different one."""
        assert test_user.email is not None
        signed_in = await _sign_in(unauthenticated_client, email=test_user.email)

        response = await unauthenticated_client.post(f"{AUTH}/refresh")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        # No profile on this call: the client already knows who it is, and this
        # request fires every fifteen minutes for as long as the tab is open.
        assert "user" not in body

        rotated = _refresh_cookie(unauthenticated_client)
        assert rotated is not None
        assert rotated != signed_in.refresh_token

    async def test_the_new_access_token_works(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that the token minted by a refresh opens a protected route."""
        assert test_user.email is not None
        _ = await _sign_in(unauthenticated_client, email=test_user.email)

        refreshed = await unauthenticated_client.post(f"{AUTH}/refresh")
        assert refreshed.status_code == 200, refreshed.text

        sessions = await unauthenticated_client.get(
            f"{AUTH}/sessions",
            headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
        )
        assert sessions.status_code == 200

    async def test_the_previous_token_stops_working(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that a spent refresh token is refused."""
        assert test_user.email is not None
        signed_in = await _sign_in(unauthenticated_client, email=test_user.email)
        assert (await unauthenticated_client.post(f"{AUTH}/refresh")).status_code == 200

        _replay(unauthenticated_client, signed_in.refresh_token)
        response = await unauthenticated_client.post(f"{AUTH}/refresh")

        assert response.status_code == 401
        assert response.json()["code"] == "auth.session_revoked"

    async def test_replaying_a_spent_token_revokes_every_session(
        self,
        unauthenticated_client: AsyncClient,
        other_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test that reuse detection signs the account out everywhere.

        Two devices are signed in and only one of them replays a spent token,
        yet both end up signed out. That is the point: a token presented twice
        means the secret exists in two places, and there is no way to tell which
        of the two holders is the owner — so neither keeps access and both are
        made to sign in again.
        """
        assert test_user.email is not None
        first = await _sign_in(unauthenticated_client, email=test_user.email)
        _ = await _sign_in(other_client, email=test_user.email)
        assert (await unauthenticated_client.post(f"{AUTH}/refresh")).status_code == 200

        _replay(unauthenticated_client, first.refresh_token)
        replayed = await unauthenticated_client.post(f"{AUTH}/refresh")

        assert replayed.status_code == 401
        assert replayed.json()["code"] == "auth.session_revoked"

        # The untouched second device is signed out too, and nothing survives.
        assert (await other_client.post(f"{AUTH}/refresh")).status_code == 401
        remaining = await crud_auth_session.list_active_for_user(
            db_session, user_id=test_user.id
        )
        assert list(remaining) == []

    async def test_missing_cookie_is_a_flat_401(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Test that never having signed in is answered, not celebrated.

        This is what the frontend's ``bootstrap()`` call receives on every first
        visit, so it has to be an ordinary, cheap 401 rather than anything that
        looks like an error worth reporting.
        """
        response = await unauthenticated_client.post(f"{AUTH}/refresh")

        assert response.status_code == 401
        assert response.json()["code"] == "auth.invalid_token"

    async def test_an_unknown_token_is_a_401(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Test that a value that never was a session is refused."""
        _replay(unauthenticated_client, "not-a-token-this-server-ever-issued")

        response = await unauthenticated_client.post(f"{AUTH}/refresh")

        assert response.status_code == 401
        assert response.json()["code"] == "auth.invalid_token"

    async def test_an_expired_session_is_refused_as_expired(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test that a lapsed session says so, rather than crying theft.

        The distinction matters to whoever reads the logs: an expired token is
        an ordinary abandoned tab, while ``auth.session_revoked`` is a signal
        that someone may be holding a stolen cookie.
        """
        assert test_user.email is not None
        signed_in = await _sign_in(unauthenticated_client, email=test_user.email)

        row = await crud_auth_session.get_by_token_hash(
            db_session, token_hash=hash_token(signed_in.refresh_token)
        )
        assert row is not None
        row.expires_at = _naive_utc_now() - timedelta(minutes=1)
        db_session.add(row)
        await db_session.flush()

        response = await unauthenticated_client.post(f"{AUTH}/refresh")

        assert response.status_code == 401
        assert response.json()["code"] == "auth.token_expired"

    async def test_rotation_keeps_the_original_sign_in_time(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that a device does not look freshly signed in after every refresh.

        Rotation replaces the row, so without deliberately carrying
        ``created_at`` across, the Security settings card would report every
        active device as having signed in fifteen minutes ago — and the list's
        "newest sign-in first" ordering would become "most recently refreshed".
        """
        assert test_user.email is not None
        signed_in = await _sign_in(unauthenticated_client, email=test_user.email)

        before = await unauthenticated_client.get(
            f"{AUTH}/sessions", headers=signed_in.headers
        )
        assert before.status_code == 200
        created_at = before.json()[0]["created_at"]

        assert (await unauthenticated_client.post(f"{AUTH}/refresh")).status_code == 200

        after = await unauthenticated_client.get(
            f"{AUTH}/sessions", headers=signed_in.headers
        )
        assert after.status_code == 200
        assert len(after.json()) == 1, "rotation must not leave the old row visible"
        assert after.json()[0]["created_at"] == created_at
        assert after.json()[0]["last_used_at"] is not None


# ── Sign-out ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestLogout:
    """``POST /auth/logout`` — end this device's session and nothing else.

    Two properties, and the second is the one that regresses quietly: the
    cookie has to be cleared with exactly the attributes it was set with (a
    mismatched path creates a *second*, empty cookie and leaves the original
    working), and the other devices have to survive.
    """

    async def test_ends_the_session_and_clears_the_cookie(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that after signing out the refresh token no longer works."""
        assert test_user.email is not None
        signed_in = await _sign_in(unauthenticated_client, email=test_user.email)

        response = await unauthenticated_client.post(f"{AUTH}/logout")

        assert response.status_code == 204
        assert _refresh_cookie(unauthenticated_client) is None

        _replay(unauthenticated_client, signed_in.refresh_token)
        assert (await unauthenticated_client.post(f"{AUTH}/refresh")).status_code == 401

    async def test_revokes_only_the_calling_device(
        self,
        unauthenticated_client: AsyncClient,
        other_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test that signing out on one device leaves the others signed in."""
        assert test_user.email is not None
        _ = await _sign_in(unauthenticated_client, email=test_user.email)
        _ = await _sign_in(other_client, email=test_user.email)

        assert (await unauthenticated_client.post(f"{AUTH}/logout")).status_code == 204

        assert (await other_client.post(f"{AUTH}/refresh")).status_code == 200

    async def test_signing_out_twice_is_still_a_204(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that logout never fails, however little there is to do.

        A client cleaning up after itself must not be answered with an error
        that leaves the dead cookie in place — being signed out is the state
        the caller asked for, and it already holds.
        """
        assert test_user.email is not None
        _ = await _sign_in(unauthenticated_client, email=test_user.email)

        assert (await unauthenticated_client.post(f"{AUTH}/logout")).status_code == 204
        assert (await unauthenticated_client.post(f"{AUTH}/logout")).status_code == 204

    async def test_logout_without_a_cookie_is_a_204(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Test that signing out when never signed in is not an error."""
        response = await unauthenticated_client.post(f"{AUTH}/logout")

        assert response.status_code == 204

    async def test_logout_with_an_unknown_cookie_is_a_204(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Test that a cookie naming no session is still answered with success.

        Unlike ``/auth/refresh``, an unrecognised token here is *not* treated as
        evidence of theft. Logout is the one request whose intent is already
        satisfied by the failure, and answering 401 would only leave the dead
        cookie in a browser that was trying to clean up after itself.
        """
        _replay(unauthenticated_client, "a-token-from-some-other-lifetime")

        response = await unauthenticated_client.post(f"{AUTH}/logout")

        assert response.status_code == 204


# ── Password reset ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestForgotPassword:
    """``POST /auth/forgot-password`` — 202, whoever asked and whatever for.

    The endpoint's only interesting property is the one it *refuses* to have.
    Any observable difference between a known and an unknown address turns it
    into "does this person have an account here?", which for this application
    is a real disclosure about who volunteers where.
    """

    async def test_known_address_is_sent_a_reset_link(
        self,
        unauthenticated_client: AsyncClient,
        outbox: list[SentMail],
        test_user: User,
    ) -> None:
        """Test that a real account gets a mail carrying a working token."""
        assert test_user.email is not None

        response = await unauthenticated_client.post(
            f"{AUTH}/forgot-password", json={"email": test_user.email}
        )

        assert response.status_code == 202
        assert len(outbox) == 1
        assert outbox[0].kind == "reset_password"
        assert outbox[0].email == test_user.email
        assert outbox[0].language == test_user.preferred_language

    async def test_unknown_address_is_answered_identically(
        self,
        unauthenticated_client: AsyncClient,
        outbox: list[SentMail],
        test_user: User,
    ) -> None:
        """Test that both answers are byte-identical and only one mail is sent."""
        assert test_user.email is not None

        known = await unauthenticated_client.post(
            f"{AUTH}/forgot-password", json={"email": test_user.email}
        )
        unknown = await unauthenticated_client.post(
            f"{AUTH}/forgot-password", json={"email": "nobody-here@example.com"}
        )

        assert known.status_code == unknown.status_code == 202
        assert known.content == unknown.content
        assert len(outbox) == 1, "the unknown address must not produce a mail"

    async def test_the_mail_goes_to_the_stored_address_not_the_typed_one(
        self,
        unauthenticated_client: AsyncClient,
        outbox: list[SentMail],
        test_user: User,
    ) -> None:
        """Test that the link is sent to the address the account actually holds.

        The lookup is case-insensitive, so the form can be filled in with any
        capitalisation. What must not vary is the recipient — a mail addressed
        to whatever was typed is a mail an attacker gets to choose the casing,
        and eventually the routing, of.
        """
        assert test_user.email is not None

        response = await unauthenticated_client.post(
            f"{AUTH}/forgot-password", json={"email": test_user.email.upper()}
        )

        assert response.status_code == 202
        assert len(outbox) == 1
        assert outbox[0].email == test_user.email

    async def test_an_account_without_a_password_may_still_request_one(
        self,
        unauthenticated_client: AsyncClient,
        outbox: list[SentMail],
        test_passwordless_user: User,
    ) -> None:
        """Test that a passwordless account can obtain its first password.

        Demo accounts and rows created before local authentication have no
        hash. This flow is how they get one, so skipping them here would leave
        them permanently unable to sign in.
        """
        assert test_passwordless_user.email is not None

        response = await unauthenticated_client.post(
            f"{AUTH}/forgot-password", json={"email": test_passwordless_user.email}
        )

        assert response.status_code == 202
        assert len(outbox) == 1


@pytest.mark.asyncio
class TestResetPassword:
    """``POST /auth/reset-password`` — redeem the link, and sweep the account.

    Someone reaching for a password reset is usually telling us they believe
    their account is in somebody else's hands. So the endpoint does three
    things that all have to hold together: the new password takes effect, the
    link cannot be used twice, and every session — the attacker's included —
    is closed. Any one of them alone makes the flow decorative.
    """

    async def _reset_token_for(
        self, client: AsyncClient, outbox: list[SentMail], email: str
    ) -> str:
        """Run the forgot-password flow and return the token that was mailed."""
        response = await client.post(f"{AUTH}/forgot-password", json={"email": email})
        assert response.status_code == 202
        assert outbox, "no reset mail was scheduled"
        return outbox[-1].token

    async def test_sets_the_new_password_and_retires_the_old_one(
        self,
        unauthenticated_client: AsyncClient,
        outbox: list[SentMail],
        test_user: User,
    ) -> None:
        """Test that after a reset only the new password is accepted."""
        assert test_user.email is not None
        token = await self._reset_token_for(
            unauthenticated_client, outbox, test_user.email
        )

        response = await unauthenticated_client.post(
            f"{AUTH}/reset-password", json={"token": token, "password": NEW_PASSWORD}
        )
        assert response.status_code == 204

        with_new = await unauthenticated_client.post(
            f"{AUTH}/login",
            json={"email": test_user.email, "password": NEW_PASSWORD},
        )
        assert with_new.status_code == 200, with_new.text

        with_old = await unauthenticated_client.post(
            f"{AUTH}/login",
            json={"email": test_user.email, "password": TEST_USER_PASSWORD},
        )
        assert with_old.status_code == 401

    async def test_the_token_cannot_be_used_twice(
        self,
        unauthenticated_client: AsyncClient,
        outbox: list[SentMail],
        test_user: User,
    ) -> None:
        """Test that a redeemed link is dead, however quickly it is clicked again."""
        assert test_user.email is not None
        token = await self._reset_token_for(
            unauthenticated_client, outbox, test_user.email
        )

        first = await unauthenticated_client.post(
            f"{AUTH}/reset-password", json={"token": token, "password": NEW_PASSWORD}
        )
        assert first.status_code == 204

        second = await unauthenticated_client.post(
            f"{AUTH}/reset-password",
            json={"token": token, "password": "yet-another-password"},
        )
        assert second.status_code == 400
        assert second.json()["code"] == "auth.invalid_token"

    async def test_an_expired_token_is_refused(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        outbox: list[SentMail],
        test_user: User,
    ) -> None:
        """Test that a link older than its hour is rejected as expired.

        A reset link is a live password sitting in an inbox, which is why its
        lifetime is an hour rather than the verification link's two days.
        """
        assert test_user.email is not None
        token = await self._reset_token_for(
            unauthenticated_client, outbox, test_user.email
        )

        row = await crud_user_token.get_by_token_hash(
            db_session, token_hash=hash_token(token)
        )
        assert row is not None
        row.expires_at = _naive_utc_now() - timedelta(minutes=1)
        db_session.add(row)
        await db_session.flush()

        response = await unauthenticated_client.post(
            f"{AUTH}/reset-password", json={"token": token, "password": NEW_PASSWORD}
        )

        assert response.status_code == 400
        assert response.json()["code"] == "auth.token_expired"

    async def test_every_session_is_revoked(
        self,
        unauthenticated_client: AsyncClient,
        other_client: AsyncClient,
        db_session: AsyncSession,
        outbox: list[SentMail],
        test_user: User,
    ) -> None:
        """Test that a reset signs out every device, not just the resetting one.

        The device that performs the reset is typically not the compromised
        one — the whole point is to eject whoever else is holding a cookie.
        """
        assert test_user.email is not None
        _ = await _sign_in(unauthenticated_client, email=test_user.email)
        _ = await _sign_in(other_client, email=test_user.email)

        token = await self._reset_token_for(
            unauthenticated_client, outbox, test_user.email
        )
        response = await unauthenticated_client.post(
            f"{AUTH}/reset-password", json={"token": token, "password": NEW_PASSWORD}
        )
        assert response.status_code == 204

        assert (await other_client.post(f"{AUTH}/refresh")).status_code == 401
        remaining = await crud_auth_session.list_active_for_user(
            db_session, user_id=test_user.id
        )
        assert list(remaining) == []

    async def test_every_other_outstanding_link_is_burned(
        self,
        unauthenticated_client: AsyncClient,
        outbox: list[SentMail],
        test_user: User,
    ) -> None:
        """Test that succeeding invalidates the reset links that did not win.

        Asking twice is ordinary — the first mail went to spam, or the tab was
        closed — so issuing a token deliberately leaves the earlier ones alive.
        Completing the flow is the moment that changes: every remaining link is
        a spare key to an account whose owner has just told us they are worried
        about it, including one an attacker may have requested.
        """
        assert test_user.email is not None
        first = await self._reset_token_for(
            unauthenticated_client, outbox, test_user.email
        )
        second = await self._reset_token_for(
            unauthenticated_client, outbox, test_user.email
        )
        assert first != second

        redeemed = await unauthenticated_client.post(
            f"{AUTH}/reset-password", json={"token": first, "password": NEW_PASSWORD}
        )
        assert redeemed.status_code == 204

        leftover = await unauthenticated_client.post(
            f"{AUTH}/reset-password",
            json={"token": second, "password": "a-third-password-entirely"},
        )
        assert leftover.status_code == 400
        assert leftover.json()["code"] == "auth.invalid_token"

    async def test_a_verification_token_cannot_reset_a_password(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test that tokens are bound to the flow they were issued for.

        A verification link is mailed to an address that has not yet proved it
        belongs to anybody. If it could be replayed here, confirming an address
        and taking over the account would be the same action.
        """
        token = await issue_user_token(
            db_session, user_id=test_user.id, purpose="verify_email"
        )

        response = await unauthenticated_client.post(
            f"{AUTH}/reset-password", json={"token": token, "password": NEW_PASSWORD}
        )

        assert response.status_code == 400
        assert response.json()["code"] == "auth.invalid_token"

    async def test_an_unknown_token_is_refused(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Test that a made-up token is refused as invalid."""
        response = await unauthenticated_client.post(
            f"{AUTH}/reset-password",
            json={"token": "nothing-like-a-real-token", "password": NEW_PASSWORD},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "auth.invalid_token"

    async def test_a_rejected_password_does_not_burn_the_link(
        self,
        unauthenticated_client: AsyncClient,
        outbox: list[SentMail],
        test_user: User,
    ) -> None:
        """Test that a too-short password leaves the token still redeemable.

        Ordering, not validation, is what this pins down: the password is
        hashed before the token is consumed, so a typo costs a retry rather
        than a whole new mail. Swap the two statements and this test is the
        only thing that notices.
        """
        assert test_user.email is not None
        token = await self._reset_token_for(
            unauthenticated_client, outbox, test_user.email
        )

        rejected = await unauthenticated_client.post(
            f"{AUTH}/reset-password", json={"token": token, "password": "short"}
        )
        assert rejected.status_code == 422

        accepted = await unauthenticated_client.post(
            f"{AUTH}/reset-password", json={"token": token, "password": NEW_PASSWORD}
        )
        assert accepted.status_code == 204


# ── Email verification ────────────────────────────────────────────


@pytest.mark.asyncio
class TestVerifyEmail:
    """``POST /auth/verify-email`` — confirm an address from a mailed link.

    Unauthenticated on purpose: the link is routinely opened somewhere other
    than the browser that registered — a phone, or a mail client's in-app view
    — and requiring a session there would strand people who did exactly what
    the mail told them to.
    """

    async def test_confirms_the_address(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_passwordless_user: User,
    ) -> None:
        """Test that redeeming the link marks the address verified."""
        assert test_passwordless_user.email_verified is False
        token = await issue_user_token(
            db_session, user_id=test_passwordless_user.id, purpose="verify_email"
        )

        response = await unauthenticated_client.post(
            f"{AUTH}/verify-email", json={"token": token}
        )

        assert response.status_code == 204
        await db_session.refresh(test_passwordless_user)
        assert test_passwordless_user.email_verified is True

    async def test_a_consumed_token_is_refused(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_passwordless_user: User,
    ) -> None:
        """Test that a second click on the same link is refused."""
        token = await issue_user_token(
            db_session, user_id=test_passwordless_user.id, purpose="verify_email"
        )
        assert (
            await unauthenticated_client.post(
                f"{AUTH}/verify-email", json={"token": token}
            )
        ).status_code == 204

        response = await unauthenticated_client.post(
            f"{AUTH}/verify-email", json={"token": token}
        )

        assert response.status_code == 400
        assert response.json()["code"] == "auth.invalid_token"

    async def test_an_expired_token_is_refused_as_expired(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_passwordless_user: User,
    ) -> None:
        """Test that a stale link says so, so the UI can offer a resend."""
        token = await issue_user_token(
            db_session, user_id=test_passwordless_user.id, purpose="verify_email"
        )
        row = await crud_user_token.get_by_token_hash(
            db_session, token_hash=hash_token(token)
        )
        assert row is not None
        row.expires_at = _naive_utc_now() - timedelta(hours=1)
        db_session.add(row)
        await db_session.flush()

        response = await unauthenticated_client.post(
            f"{AUTH}/verify-email", json={"token": token}
        )

        assert response.status_code == 400
        assert response.json()["code"] == "auth.token_expired"

    async def test_an_unknown_token_is_refused(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Test that a made-up token is refused as invalid."""
        response = await unauthenticated_client.post(
            f"{AUTH}/verify-email", json={"token": "not-a-token"}
        )

        assert response.status_code == 400
        assert response.json()["code"] == "auth.invalid_token"

    async def test_a_reset_token_cannot_verify_an_address(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_passwordless_user: User,
    ) -> None:
        """Test that the purpose check holds in this direction too."""
        token = await issue_user_token(
            db_session, user_id=test_passwordless_user.id, purpose="reset_password"
        )

        response = await unauthenticated_client.post(
            f"{AUTH}/verify-email", json={"token": token}
        )

        assert response.status_code == 400
        assert response.json()["code"] == "auth.invalid_token"


@pytest.mark.asyncio
class TestResendVerification:
    """``POST /auth/resend-verification`` — a flat 202, mail or no mail.

    The three outcomes (a mail was sent, the address is already confirmed, the
    account has no address at all) are deliberately indistinguishable. There is
    nothing the caller could do differently in any of them, and a status that
    varied would be one more thing for the UI to explain.
    """

    async def test_sends_a_fresh_link_that_works(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        outbox: list[SentMail],
        auth_headers: AuthHeadersFactory,
        test_passwordless_user: User,
    ) -> None:
        """Test that an unverified account is mailed a redeemable token."""
        response = await unauthenticated_client.post(
            f"{AUTH}/resend-verification",
            headers=auth_headers(test_passwordless_user),
        )

        assert response.status_code == 202
        assert len(outbox) == 1
        assert outbox[0].kind == "verify_email"

        redeemed = await unauthenticated_client.post(
            f"{AUTH}/verify-email", json={"token": outbox[0].token}
        )
        assert redeemed.status_code == 204
        await db_session.refresh(test_passwordless_user)
        assert test_passwordless_user.email_verified is True

    async def test_an_already_verified_account_is_sent_nothing(
        self,
        unauthenticated_client: AsyncClient,
        outbox: list[SentMail],
        auth_headers: AuthHeadersFactory,
        test_user: User,
    ) -> None:
        """Test that a confirmed address still answers 202, quietly."""
        assert test_user.email_verified is True

        response = await unauthenticated_client.post(
            f"{AUTH}/resend-verification", headers=auth_headers(test_user)
        )

        assert response.status_code == 202
        assert outbox == []

    async def test_requires_authentication(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Test that an anonymous caller cannot make us send mail."""
        response = await unauthenticated_client.post(f"{AUTH}/resend-verification")

        assert response.status_code == 401


# ── Account security ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestChangePassword:
    """``POST /auth/change-password`` — prove the old one, then eject the others.

    Requiring the current password from an already-authenticated caller is not
    ceremony: it is the only thing standing between a borrowed unlocked laptop
    and a permanent account takeover.

    Which sessions survive is the other half. Everything *except* the caller's
    own is closed — signing someone out of the tab they are typing in reads as
    a bug, while leaving the old phone and the shared machine signed in defeats
    the point of changing the password at all.
    """

    async def test_changes_the_password(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that the new password works and the old one stops working."""
        assert test_user.email is not None
        signed_in = await _sign_in(unauthenticated_client, email=test_user.email)

        response = await unauthenticated_client.post(
            f"{AUTH}/change-password",
            headers=signed_in.headers,
            json={
                "current_password": TEST_USER_PASSWORD,
                "new_password": NEW_PASSWORD,
            },
        )
        assert response.status_code == 204

        with_new = await unauthenticated_client.post(
            f"{AUTH}/login",
            json={"email": test_user.email, "password": NEW_PASSWORD},
        )
        assert with_new.status_code == 200, with_new.text

        with_old = await unauthenticated_client.post(
            f"{AUTH}/login",
            json={"email": test_user.email, "password": TEST_USER_PASSWORD},
        )
        assert with_old.status_code == 401

    async def test_the_wrong_current_password_changes_nothing(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that a bad current password is a 401 and leaves the account alone."""
        assert test_user.email is not None
        signed_in = await _sign_in(unauthenticated_client, email=test_user.email)

        response = await unauthenticated_client.post(
            f"{AUTH}/change-password",
            headers=signed_in.headers,
            json={
                "current_password": "not-the-current-password",
                "new_password": NEW_PASSWORD,
            },
        )

        assert response.status_code == 401
        assert response.json()["code"] == "auth.invalid_credentials"

        unchanged = await unauthenticated_client.post(
            f"{AUTH}/login",
            json={"email": test_user.email, "password": TEST_USER_PASSWORD},
        )
        assert unchanged.status_code == 200, "the old password must still work"

    async def test_revokes_the_other_devices_but_not_the_caller(
        self,
        unauthenticated_client: AsyncClient,
        other_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test that the changing device stays signed in and the others do not.

        The caller's own session is checked **first**, and the order is not
        incidental: the ejected device's next refresh presents a token whose
        row is already revoked, which reuse detection cannot tell from a stolen
        cookie, so it sweeps every remaining session of the account — the
        caller's included. Asserting in the other order would test that sweep
        rather than the exemption.
        """
        assert test_user.email is not None
        signed_in = await _sign_in(unauthenticated_client, email=test_user.email)
        _ = await _sign_in(other_client, email=test_user.email)

        response = await unauthenticated_client.post(
            f"{AUTH}/change-password",
            headers=signed_in.headers,
            json={
                "current_password": TEST_USER_PASSWORD,
                "new_password": NEW_PASSWORD,
            },
        )
        assert response.status_code == 204

        assert (await unauthenticated_client.post(f"{AUTH}/refresh")).status_code == 200
        assert (await other_client.post(f"{AUTH}/refresh")).status_code == 401

    async def test_an_account_without_a_password_is_told_to_use_the_reset_link(
        self,
        unauthenticated_client: AsyncClient,
        auth_headers: AuthHeadersFactory,
        test_passwordless_user: User,
    ) -> None:
        """Test that a NULL hash is a 400 with its own code, not a failed check.

        There is no current password to prove, so answering
        ``auth.invalid_credentials`` would send someone hunting for a password
        that does not exist. ``auth.no_password_set`` is what the frontend
        switches on to offer the reset flow instead.
        """
        response = await unauthenticated_client.post(
            f"{AUTH}/change-password",
            headers=auth_headers(test_passwordless_user),
            json={"current_password": "anything", "new_password": NEW_PASSWORD},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "auth.no_password_set"

    async def test_a_weak_new_password_is_a_field_error(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that the policy applies here as well as at registration."""
        assert test_user.email is not None
        signed_in = await _sign_in(unauthenticated_client, email=test_user.email)

        response = await unauthenticated_client.post(
            f"{AUTH}/change-password",
            headers=signed_in.headers,
            json={"current_password": TEST_USER_PASSWORD, "new_password": "short"},
        )

        assert response.status_code == 422
        assert "new_password" in _error_locations(response.json())

    async def test_requires_authentication(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Test that an anonymous caller cannot change anybody's password."""
        response = await unauthenticated_client.post(
            f"{AUTH}/change-password",
            json={
                "current_password": TEST_USER_PASSWORD,
                "new_password": NEW_PASSWORD,
            },
        )

        assert response.status_code == 401


@pytest.mark.asyncio
class TestSessionList:
    """``GET /auth/sessions`` — the Security settings card's list of devices.

    Everything here is about what the list must *not* contain: another
    account's devices, or sessions that are already dead. Both would be
    harmless-looking display bugs that tell someone their account is signed in
    somewhere it is not.
    """

    async def test_lists_this_accounts_devices_with_their_labels(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that the user agent and address recorded at sign-in come back."""
        assert test_user.email is not None
        signed_in = await _sign_in(
            unauthenticated_client,
            email=test_user.email,
            user_agent="TestBrowser/1.0",
            ip_address="203.0.113.7",
        )

        response = await unauthenticated_client.get(
            f"{AUTH}/sessions", headers=signed_in.headers
        )

        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["user_agent"] == "TestBrowser/1.0"
        assert rows[0]["ip_address"] == "203.0.113.7"
        assert rows[0]["is_current"] is True

    async def test_records_the_address_the_proxy_saw_not_one_the_caller_wrote(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that a caller cannot put its own address in front of the real one.

        Traefik appends the address it saw; whatever the caller sent comes
        before it, so only the rightmost untrusted entry is believable.
        """
        assert test_user.email is not None
        signed_in = await _sign_in(
            unauthenticated_client,
            email=test_user.email,
            ip_address="198.51.100.66, 203.0.113.7",
        )

        response = await unauthenticated_client.get(
            f"{AUTH}/sessions", headers=signed_in.headers
        )

        assert response.json()[0]["ip_address"] == "203.0.113.7"

    async def test_ignores_the_header_from_a_caller_that_is_not_a_proxy(
        self, unauthenticated_app: FastAPI, test_user: User
    ) -> None:
        """Test that X-Forwarded-For from a public address is not believed."""
        assert test_user.email is not None
        transport = ASGITransport(
            app=unauthenticated_app, client=("198.51.100.9", 40000)
        )
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            signed_in = await _sign_in(
                client, email=test_user.email, ip_address="203.0.113.7"
            )
            response = await client.get(f"{AUTH}/sessions", headers=signed_in.headers)

        assert response.json()[0]["ip_address"] == "198.51.100.9"

    async def test_flags_only_the_session_making_the_request(
        self,
        unauthenticated_client: AsyncClient,
        other_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test that exactly one entry is marked ``is_current``.

        Without the flag the card would invite someone to sign themselves out
        and then wonder why the page went blank.
        """
        assert test_user.email is not None
        first = await _sign_in(unauthenticated_client, email=test_user.email)
        _ = await _sign_in(other_client, email=test_user.email)

        response = await unauthenticated_client.get(
            f"{AUTH}/sessions", headers=first.headers
        )

        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 2
        assert [row["is_current"] for row in rows].count(True) == 1

    async def test_a_token_from_another_session_flags_nothing(
        self,
        unauthenticated_client: AsyncClient,
        auth_headers: AuthHeadersFactory,
        test_user: User,
    ) -> None:
        """Test that ``is_current`` follows the token's ``jti``, not the user.

        ``auth_headers`` mints a token for a session id that no row carries,
        which is also the shape of the E2E impersonation header — neither must
        be able to claim one of the listed devices as "this device".
        """
        assert test_user.email is not None
        _ = await _sign_in(unauthenticated_client, email=test_user.email)

        response = await unauthenticated_client.get(
            f"{AUTH}/sessions", headers=auth_headers(test_user)
        )

        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["is_current"] is False

    async def test_another_accounts_sessions_are_not_listed(
        self,
        unauthenticated_client: AsyncClient,
        other_client: AsyncClient,
        test_user: User,
        test_outsider_user: User,
    ) -> None:
        """Test that the list is scoped to the caller."""
        assert test_user.email is not None
        assert test_outsider_user.email is not None
        mine = await _sign_in(unauthenticated_client, email=test_user.email)
        _ = await _sign_in(other_client, email=test_outsider_user.email)

        response = await unauthenticated_client.get(
            f"{AUTH}/sessions", headers=mine.headers
        )

        assert response.status_code == 200
        assert len(response.json()) == 1

    async def test_revoked_sessions_disappear_from_the_list(
        self,
        unauthenticated_client: AsyncClient,
        other_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test that signing a device out removes it from the card.

        Revoked rows are kept in the table for reuse detection, so "kept" and
        "shown" have to be two different questions.
        """
        assert test_user.email is not None
        mine = await _sign_in(unauthenticated_client, email=test_user.email)
        _ = await _sign_in(other_client, email=test_user.email)

        assert (await other_client.post(f"{AUTH}/logout")).status_code == 204

        response = await unauthenticated_client.get(
            f"{AUTH}/sessions", headers=mine.headers
        )
        assert response.status_code == 200
        assert len(response.json()) == 1

    async def test_requires_authentication(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Test that the device list is not readable anonymously."""
        response = await unauthenticated_client.get(f"{AUTH}/sessions")

        assert response.status_code == 401


@pytest.mark.asyncio
class TestRevokeSession:
    """``DELETE /auth/sessions/{id}`` — sign one named device out.

    The status code for somebody else's session is the interesting part: 404,
    not 403. A 403 would confirm that the id names a real session, which is one
    bit more than a stranger should learn from a guess — the same reasoning
    ``logic.permissions.require_event_visible`` applies to private events.
    """

    async def test_signs_the_named_device_out(
        self,
        unauthenticated_client: AsyncClient,
        other_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test that revoking a session kills exactly that refresh token.

        As in ``TestChangePassword``, the surviving session is checked before
        the ejected one is touched: a revoked token presented again is
        indistinguishable from a stolen one, so that attempt sweeps the account
        and would mask the very thing this test is about.
        """
        assert test_user.email is not None
        mine = await _sign_in(unauthenticated_client, email=test_user.email)
        _ = await _sign_in(other_client, email=test_user.email)

        listed = await unauthenticated_client.get(
            f"{AUTH}/sessions", headers=mine.headers
        )
        assert listed.status_code == 200
        others = [row for row in listed.json() if row["is_current"] is False]
        assert len(others) == 1

        response = await unauthenticated_client.delete(
            f"{AUTH}/sessions/{others[0]['id']}", headers=mine.headers
        )

        assert response.status_code == 204
        assert (await unauthenticated_client.post(f"{AUTH}/refresh")).status_code == 200
        assert (await other_client.post(f"{AUTH}/refresh")).status_code == 401

    async def test_revoking_your_own_session_is_allowed(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that "sign out everywhere, including here" is a legal request.

        The effect is simply that the next refresh fails and the client returns
        to the login screen, which is what was asked for.
        """
        assert test_user.email is not None
        mine = await _sign_in(unauthenticated_client, email=test_user.email)

        listed = await unauthenticated_client.get(
            f"{AUTH}/sessions", headers=mine.headers
        )
        assert listed.status_code == 200
        current = listed.json()[0]
        assert current["is_current"] is True

        response = await unauthenticated_client.delete(
            f"{AUTH}/sessions/{current['id']}", headers=mine.headers
        )

        assert response.status_code == 204
        assert (await unauthenticated_client.post(f"{AUTH}/refresh")).status_code == 401

    async def test_another_accounts_session_is_a_404_not_a_403(
        self,
        unauthenticated_client: AsyncClient,
        other_client: AsyncClient,
        test_user: User,
        test_outsider_user: User,
    ) -> None:
        """Test that a stranger's session id is indistinguishable from a wrong one."""
        assert test_user.email is not None
        assert test_outsider_user.email is not None
        mine = await _sign_in(unauthenticated_client, email=test_user.email)
        theirs = await _sign_in(other_client, email=test_outsider_user.email)

        listed = await other_client.get(f"{AUTH}/sessions", headers=theirs.headers)
        assert listed.status_code == 200
        their_session_id = listed.json()[0]["id"]

        response = await unauthenticated_client.delete(
            f"{AUTH}/sessions/{their_session_id}", headers=mine.headers
        )

        assert response.status_code == 404
        assert response.json()["code"] == "auth.session_not_found"
        # And it really is still alive — the 404 is about visibility, not state.
        assert (await other_client.post(f"{AUTH}/refresh")).status_code == 200

    async def test_an_unknown_id_is_a_404(
        self, unauthenticated_client: AsyncClient, test_user: User
    ) -> None:
        """Test that an id nothing owns answers the same way as one somebody else does."""
        assert test_user.email is not None
        mine = await _sign_in(unauthenticated_client, email=test_user.email)

        response = await unauthenticated_client.delete(
            f"{AUTH}/sessions/{uuid.uuid4()}", headers=mine.headers
        )

        assert response.status_code == 404
        assert response.json()["code"] == "auth.session_not_found"

    async def test_requires_authentication(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """Test that sessions cannot be revoked anonymously."""
        response = await unauthenticated_client.delete(
            f"{AUTH}/sessions/{uuid.uuid4()}"
        )

        assert response.status_code == 401


@pytest.mark.asyncio
class TestUnderTheE2EImpersonationHeader:
    """What these endpoints do for a caller with no bearer token at all.

    The whole Playwright suite authenticates with ``X-Test-User-Email`` rather
    than a token, because in CI the browser origin and the API host are
    genuinely cross-site and the refresh cookie a real login depends on is
    silently dropped. So every route that reads the *session* out of the
    caller's token has to cope with there being no token to read.

    Both routes that do — the device list and the password change — are covered
    here, because the failure mode is invisible from the E2E side: the Security
    settings screen would simply 401 for the entire suite, or a password change
    would sign the harness out mid-run.
    """

    async def test_the_header_authenticates_the_device_list(
        self,
        unauthenticated_client: AsyncClient,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that the list is readable without a bearer token, flagging nothing."""
        monkeypatch.setattr(settings, "TESTING", True)
        assert test_user.email is not None
        _ = await _sign_in(unauthenticated_client, email=test_user.email)

        response = await unauthenticated_client.get(
            f"{AUTH}/sessions", headers={"X-Test-User-Email": test_user.email}
        )

        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["is_current"] is False

    async def test_an_unreadable_bearer_token_does_not_break_the_list(
        self,
        unauthenticated_client: AsyncClient,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that a stale token alongside the header is ignored, not fatal.

        The E2E fixtures inject the header on every request while the browser
        may still be holding whatever token it last saw. Decoding that token to
        label "this device" must therefore fail softly — the label is cosmetic,
        and a raised ``AuthTokenError`` here would 401 a request the identity
        layer had already accepted.
        """
        monkeypatch.setattr(settings, "TESTING", True)
        assert test_user.email is not None
        _ = await _sign_in(unauthenticated_client, email=test_user.email)

        response = await unauthenticated_client.get(
            f"{AUTH}/sessions",
            headers={
                "X-Test-User-Email": test_user.email,
                "Authorization": "Bearer not-a-token-at-all",
            },
        )

        assert response.status_code == 200
        assert response.json()[0]["is_current"] is False

    async def test_changing_the_password_then_revokes_every_session(
        self,
        unauthenticated_client: AsyncClient,
        other_client: AsyncClient,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that an unidentifiable session spares nothing.

        With no ``jti`` to exempt there is no way to say "all but mine", and the
        safe direction to fail in is the one that closes too many sessions
        rather than too few.
        """
        monkeypatch.setattr(settings, "TESTING", True)
        assert test_user.email is not None
        _ = await _sign_in(unauthenticated_client, email=test_user.email)
        _ = await _sign_in(other_client, email=test_user.email)

        response = await unauthenticated_client.post(
            f"{AUTH}/change-password",
            headers={"X-Test-User-Email": test_user.email},
            json={
                "current_password": TEST_USER_PASSWORD,
                "new_password": NEW_PASSWORD,
            },
        )

        assert response.status_code == 204
        assert (await unauthenticated_client.post(f"{AUTH}/refresh")).status_code == 401
        assert (await other_client.post(f"{AUTH}/refresh")).status_code == 401
