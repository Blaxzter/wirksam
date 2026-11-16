# pyright: reportPrivateUsage=false
"""Unit tests for authentication dependencies.

``app.api.deps`` is the only place in the application that turns a credential
into a ``User``. Everything downstream — roles, ``EventMembership``,
``logic.permissions`` — trusts whatever comes out of here, so the tests below
are deliberately paranoid about the *negative* cases: an expired token, a token
signed with the wrong key, a token naming an account that has since been
deleted, and a token that is simply absent.

Two things this file used to test are gone with the identity provider. There is
no just-in-time provisioning any more (an account exists because someone
registered it, so an unrecognised ``sub`` is a credential for nothing rather
than an invitation to create a row), and there is no profile sync on login
(``email_verified`` is now this application's own flag, moved by its own
verify-email flow). The ``X-Test-User-Email`` branches deliberately survive: the
Playwright suite authenticates through them because in CI the browser origin and
``VITE_API_URL`` are genuinely cross-site, which silently drops the httpOnly
refresh cookie a real login depends on.
"""

import uuid
from contextlib import AsyncExitStack
from types import SimpleNamespace
from typing import Any, cast, get_args

import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps as deps_module
from app.api.deps import (
    _get_user_from_query_token,
    current_user,
    get_access_claims,
    get_db,
)
from app.core.config import settings
from app.core.security import create_access_token
from app.models.shared_list import SharedList
from app.models.user import User
from tests.fixtures.auth import AuthHeadersFactory, RawTokenFactory
from tests.fixtures.shared_lists import ListGuestFactory

# ── helpers ───────────────────────────────────────────────────────


class _FakeBegin:
    """Async context manager standing in for ``async_session.begin()``.

    A real ``begin()`` COMMITs on exit, which would escape the ``db_session``
    fixture's outer transaction and leave rows behind for the next test. Exiting
    here is therefore a deliberate no-op; exceptions still propagate.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *args: object) -> bool:
        return False


class _FakeSessionFactory:
    """Drop-in for ``app.api.deps.async_session``.

    ``get_db`` and ``_get_user_from_query_token`` open their *own* sessions off
    the module-level factory rather than the injected one, so the factory has to
    be replaced for those code paths to run against the test transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.begin_calls = 0

    def begin(self) -> _FakeBegin:
        self.begin_calls += 1
        return _FakeBegin(self._session)


def _make_request(
    *,
    query_string: str = "",
    headers: dict[str, str] | None = None,
    scope_extra: dict[str, Any] | None = None,
) -> Request:
    """Build a real Starlette ``Request``.

    ``MagicMock`` is not enough here: the deps under test read
    ``request.query_params``, ``request.headers`` and ``str(request.url)``, and
    ``get_db`` inspects ``request.scope``.
    """
    scope: dict[str, Any] = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "root_path": "",
        "path": "/api/v1/notifications/stream",
        "raw_path": b"/api/v1/notifications/stream",
        "query_string": query_string.encode("latin-1"),
        "headers": [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in (headers or {}).items()
        ],
        "app": SimpleNamespace(state=SimpleNamespace()),
    }
    if scope_extra:
        scope.update(scope_extra)
    return Request(scope)


async def _make_user(
    db_session: AsyncSession,
    *,
    email: str,
    subject: str,
    roles: list[str] | None = None,
    is_active: bool = False,
    email_verified: bool = False,
) -> User:
    """Persist a user with an exact email/role/active combination."""
    user = User(
        subject=subject,
        email=email,
        name="Fixture User",
        roles=roles if roles is not None else [],
        is_active=is_active,
        email_verified=email_verified,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


def _token_for(user_id: uuid.UUID) -> str:
    """Mint a valid access token naming ``user_id``."""
    token, _ = create_access_token(user_id=user_id, session_id=uuid.uuid4())
    return token


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    """Wrap a raw token the way ``HTTPBearer`` hands it to a dependency."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _credentials_for(user: User) -> HTTPAuthorizationCredentials:
    return _bearer(_token_for(user.id))


def _problem_code(exc: HTTPException) -> str:
    """Read the ``auth.*`` code out of a ``raise_problem`` exception.

    ``raise_problem`` puts a problem+json body in ``detail`` rather than a
    string, and the code — not the sentence — is what the frontend switches on,
    so that is what these tests assert against.
    """
    detail = cast(dict[str, Any], exc.detail)
    return str(detail["code"])


# ── the bearer-token path ─────────────────────────────────────────


@pytest.mark.asyncio
class TestGetAccessClaims:
    """``get_access_claims`` — validation with no database lookup at all.

    It exists for the handful of callers that need the *session* a request was
    made with rather than the account: "sign out my other devices" has to know
    which ``jti`` to spare. Every failure mode here is shared with
    ``current_user``, which is why they are pinned down once, here.
    """

    async def test_valid_token_yields_claims(self, test_user: User) -> None:
        """A well-formed token is decoded into its claims."""
        session_id = uuid.uuid4()
        token, _ = create_access_token(user_id=test_user.id, session_id=session_id)

        claims = await get_access_claims(credentials=_bearer(token))

        assert claims.user_id == test_user.id
        assert claims.session_id == session_id
        assert claims.token_type == "access"

    async def test_missing_credentials_raise_401(self) -> None:
        """No Authorization header is a 401, not FastAPI's default 403.

        ``HTTPBearer`` is constructed with ``auto_error=False`` precisely so
        that this case can be answered with the right status *and* a problem+json
        body the frontend can switch on.
        """
        with pytest.raises(HTTPException) as exc_info:
            await get_access_claims(credentials=None)

        assert exc_info.value.status_code == 401
        assert _problem_code(exc_info.value) == "auth.invalid_token"
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

    async def test_empty_credentials_raise_401(self) -> None:
        """A bare ``Authorization: Bearer`` with nothing after it is refused."""
        with pytest.raises(HTTPException) as exc_info:
            await get_access_claims(credentials=_bearer(""))

        assert exc_info.value.status_code == 401
        assert _problem_code(exc_info.value) == "auth.invalid_token"

    async def test_expired_token_is_reported_as_expired(
        self, test_user: User, make_expired_access_token: RawTokenFactory
    ) -> None:
        """Expiry gets its own code so the client knows to refresh and retry.

        Collapsing it into ``auth.invalid_token`` would send everyone back to
        the login form every fifteen minutes.
        """
        credentials = _bearer(make_expired_access_token(test_user))

        with pytest.raises(HTTPException) as exc_info:
            await get_access_claims(credentials=credentials)

        assert exc_info.value.status_code == 401
        assert _problem_code(exc_info.value) == "auth.token_expired"

    async def test_forged_signature_is_rejected(
        self, test_user: User, make_tampered_access_token: RawTokenFactory
    ) -> None:
        """Every claim is right and only the signature is wrong — still refused."""
        credentials = _bearer(make_tampered_access_token(test_user))

        with pytest.raises(HTTPException) as exc_info:
            await get_access_claims(credentials=credentials)

        assert exc_info.value.status_code == 401
        assert _problem_code(exc_info.value) == "auth.invalid_token"

    async def test_garbage_is_rejected(self) -> None:
        """A value that is not a JWT at all fails the same flat way."""
        with pytest.raises(HTTPException) as exc_info:
            await get_access_claims(credentials=_bearer("not-a-jwt"))

        assert exc_info.value.status_code == 401
        assert _problem_code(exc_info.value) == "auth.invalid_token"


@pytest.mark.asyncio
class TestCurrentUserDependency:
    """``current_user()`` — token in, ``User`` out.

    ``sub`` is the ``users.id`` primary key, so resolving a request is a single
    lookup with no second identity path to keep in sync. The tests below cover
    that lookup and the two gates layered on top of it: the active check and the
    platform-role check.
    """

    async def test_valid_token_resolves_the_user(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A token minted for an account resolves to that account."""
        dependency = current_user()

        user = await dependency(
            request=_make_request(),
            session=db_session,
            credentials=_credentials_for(test_user),
        )

        assert user.id == test_user.id
        assert user.is_active is True

    async def test_missing_token_raises_401(self, db_session: AsyncSession) -> None:
        """An anonymous request is 401, never a silently provisioned account."""
        dependency = current_user()

        with pytest.raises(HTTPException) as exc_info:
            await dependency(
                request=_make_request(), session=db_session, credentials=None
            )

        assert exc_info.value.status_code == 401
        assert _problem_code(exc_info.value) == "auth.invalid_token"

    async def test_token_for_a_deleted_account_raises_401(
        self, db_session: AsyncSession
    ) -> None:
        """A token outliving its account is a credential for nothing.

        Access tokens live fifteen minutes and are not checked against the
        session table on every request, so a deleted user's token stays
        cryptographically valid for up to that long. There is no just-in-time
        provisioning to fall back on any more, and re-creating the row here
        would resurrect a deleted account from a stale token.
        """
        dependency = current_user()

        with pytest.raises(HTTPException) as exc_info:
            await dependency(
                request=_make_request(),
                session=db_session,
                credentials=_bearer(_token_for(uuid.uuid4())),
            )

        assert exc_info.value.status_code == 401
        assert _problem_code(exc_info.value) == "auth.invalid_token"

    async def test_expired_token_raises_401(
        self,
        db_session: AsyncSession,
        test_user: User,
        make_expired_access_token: RawTokenFactory,
    ) -> None:
        """An expired token never reaches the database lookup."""
        dependency = current_user()

        with pytest.raises(HTTPException) as exc_info:
            await dependency(
                request=_make_request(),
                session=db_session,
                credentials=_bearer(make_expired_access_token(test_user)),
            )

        assert exc_info.value.status_code == 401
        assert _problem_code(exc_info.value) == "auth.token_expired"

    async def test_forged_token_raises_401(
        self,
        db_session: AsyncSession,
        test_user: User,
        make_tampered_access_token: RawTokenFactory,
    ) -> None:
        """A token signed with someone else's key names a real user and fails."""
        dependency = current_user()

        with pytest.raises(HTTPException) as exc_info:
            await dependency(
                request=_make_request(),
                session=db_session,
                credentials=_bearer(make_tampered_access_token(test_user)),
            )

        assert exc_info.value.status_code == 401
        assert _problem_code(exc_info.value) == "auth.invalid_token"

    async def test_inactive_user_raises_403(
        self, db_session: AsyncSession, test_inactive_user: User
    ) -> None:
        """``is_active`` is a moderation switch, and it still bars entry.

        403 rather than 401 is the meaningful distinction: the credential was
        accepted, the account was not.
        """
        dependency = current_user()

        with pytest.raises(HTTPException) as exc_info:
            await dependency(
                request=_make_request(),
                session=db_session,
                credentials=_credentials_for(test_inactive_user),
            )

        assert exc_info.value.status_code == 403
        assert "Inactive user" in str(exc_info.value.detail)

    async def test_inactive_user_allowed_when_active_not_required(
        self, db_session: AsyncSession, test_inactive_user: User
    ) -> None:
        """``AnyUser`` lets a suspended account reach its own profile."""
        dependency = current_user(require_active=False)

        user = await dependency(
            request=_make_request(),
            session=db_session,
            credentials=_credentials_for(test_inactive_user),
        )

        assert user.id == test_inactive_user.id

    async def test_role_check_success(
        self, db_session: AsyncSession, test_admin_user: User
    ) -> None:
        """Test role-based access control with valid role."""
        dependency = current_user(required_roles="admin")

        user = await dependency(
            request=_make_request(),
            session=db_session,
            credentials=_credentials_for(test_admin_user),
        )

        assert user.id == test_admin_user.id
        assert "admin" in user.roles

    async def test_role_check_failure(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Test role-based access control with missing role."""
        dependency = current_user(required_roles="admin")

        with pytest.raises(HTTPException) as exc_info:
            await dependency(
                request=_make_request(),
                session=db_session,
                credentials=_credentials_for(test_user),
            )

        assert exc_info.value.status_code == 403
        assert "Not enough permissions" in str(exc_info.value.detail)

    async def test_multiple_required_roles_all_present(
        self, db_session: AsyncSession
    ) -> None:
        """``required_roles`` is AND-semantics: every listed role must be held."""
        user = await _make_user(
            db_session,
            email="multirole@example.com",
            subject="local|multirole123",
            roles=["admin", "moderator"],
            is_active=True,
        )
        dependency = current_user(required_roles=["admin", "moderator"])

        result_user = await dependency(
            request=_make_request(),
            session=db_session,
            credentials=_credentials_for(user),
        )

        assert result_user.id == user.id

    async def test_multiple_required_roles_missing_one(
        self, db_session: AsyncSession, test_admin_user: User
    ) -> None:
        """Holding one of two required roles is not enough."""
        dependency = current_user(required_roles=["admin", "moderator"])

        with pytest.raises(HTTPException) as exc_info:
            await dependency(
                request=_make_request(),
                session=db_session,
                credentials=_credentials_for(test_admin_user),
            )

        assert exc_info.value.status_code == 403
        assert "Not enough permissions" in str(exc_info.value.detail)

    async def test_token_carries_no_roles_of_its_own(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Roles are read from the row on every request, never from the token.

        Nothing role-shaped is embedded in the JWT, deliberately: a permission
        change takes effect on the next request rather than whenever the token
        happens to expire. This test proves it by minting a token *before* the
        role is granted and using it afterwards.
        """
        credentials = _credentials_for(test_user)
        test_user.roles = ["admin"]
        db_session.add(test_user)
        await db_session.flush()

        dependency = current_user(required_roles="admin")

        user = await dependency(
            request=_make_request(), session=db_session, credentials=credentials
        )

        assert user.id == test_user.id


class TestIdentityAliasShape:
    """The exported ``Annotated[User, Depends(...)]`` aliases, as a *shape*.

    This is load-bearing beyond typing: ``tests/fixtures/client.py`` reaches
    into each alias to find the callable FastAPI keys a dependency override by.
    Replace them with plain functions or a class-based dependency and every
    override in the suite silently stops applying — all ~500 route tests would
    start hitting real authentication and 401ing at once, for a reason nothing
    in the failure output would name. Failing here instead points at the cause.
    """

    @pytest.mark.parametrize(
        "alias_name", ["CurrentUser", "CurrentSuperuser", "AnyUser", "QueryTokenUser"]
    )
    def test_alias_exposes_an_overridable_dependency(self, alias_name: str) -> None:
        """Each alias is ``Annotated[User, Depends(callable)]``."""
        alias = getattr(deps_module, alias_name)
        args = get_args(alias)

        assert args[0] is User
        assert callable(getattr(args[1], "dependency", None))

    def test_the_three_user_aliases_are_distinct_dependencies(self) -> None:
        """``current_user()`` is a factory, so each alias holds its own closure.

        Which is exactly why a test fixture has to override all three: pinning
        ``CurrentUser`` leaves ``AnyUser`` running for real, and the endpoints
        behind it then answer 401 in the middle of an otherwise ordinary route
        test.
        """
        deps = {
            id(get_args(alias)[1].dependency)
            for alias in (
                deps_module.CurrentUser,
                deps_module.CurrentSuperuser,
                deps_module.AnyUser,
            )
        }

        assert len(deps) == 3


@pytest.mark.asyncio
class TestCurrentUserAnnotated:
    """The same aliases, resolved end to end against a real token."""

    async def test_current_user_alias_resolves(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Test CurrentUser typed dependency."""
        dependency = get_args(deps_module.CurrentUser)[1].dependency

        user = await dependency(
            request=_make_request(),
            session=db_session,
            credentials=_credentials_for(test_user),
        )

        assert user.id == test_user.id
        assert isinstance(user, User)

    async def test_current_superuser_alias_admits_an_admin(
        self, db_session: AsyncSession, test_admin_user: User
    ) -> None:
        """Test CurrentSuperuser typed dependency."""
        dependency = get_args(deps_module.CurrentSuperuser)[1].dependency

        user = await dependency(
            request=_make_request(),
            session=db_session,
            credentials=_credentials_for(test_admin_user),
        )

        assert user.id == test_admin_user.id
        assert user.is_admin is True

    async def test_current_superuser_alias_rejects_a_plain_user(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Test CurrentSuperuser rejects non-admin users."""
        dependency = get_args(deps_module.CurrentSuperuser)[1].dependency

        with pytest.raises(HTTPException) as exc_info:
            await dependency(
                request=_make_request(),
                session=db_session,
                credentials=_credentials_for(test_user),
            )

        assert exc_info.value.status_code == 403
        assert "Not enough permissions" in str(exc_info.value.detail)


class TestRoleNormalization:
    """Test suite for _normalize_required_roles helper."""

    def test_normalize_none(self):
        """Test normalizing None to empty list."""
        from app.api.deps import (
            _normalize_required_roles,  # type: ignore[reportPrivateUsage]
        )

        result = _normalize_required_roles(None)
        assert result == []

    def test_normalize_string(self):
        """Test normalizing single string to list."""
        from app.api.deps import (
            _normalize_required_roles,  # type: ignore[reportPrivateUsage]
        )

        result = _normalize_required_roles("admin")
        assert result == ["admin"]

    def test_normalize_list(self):
        """Test normalizing list of strings."""
        from app.api.deps import (
            _normalize_required_roles,  # type: ignore[reportPrivateUsage]
        )

        result = _normalize_required_roles(["admin", "moderator"])
        assert result == ["admin", "moderator"]

    def test_normalize_iterable(self):
        """Test normalizing tuple to list."""
        from app.api.deps import (
            _normalize_required_roles,  # type: ignore[reportPrivateUsage]
        )

        result = _normalize_required_roles(("admin", "user"))
        assert result == ["admin", "user"]


@pytest.mark.asyncio
class TestCurrentUserAnyOfRoles:
    """Test suite for any_of_roles OR-semantics in current_user dependency."""

    async def test_first_role_matches(
        self, db_session: AsyncSession, test_admin_user: User
    ) -> None:
        """Test that first matching role grants access."""
        dependency = current_user(any_of_roles=["admin", "moderator"])

        user = await dependency(
            request=_make_request(),
            session=db_session,
            credentials=_credentials_for(test_admin_user),
        )

        assert user.id == test_admin_user.id

    async def test_second_role_matches(self, db_session: AsyncSession) -> None:
        """Test that second matching role grants access."""
        moderator = await _make_user(
            db_session,
            email="moderator@example.com",
            subject="local|moderator",
            roles=["moderator"],
            is_active=True,
        )
        dependency = current_user(any_of_roles=["admin", "moderator"])

        user = await dependency(
            request=_make_request(),
            session=db_session,
            credentials=_credentials_for(moderator),
        )

        assert user.id == moderator.id

    async def test_neither_role_matches_raises_403(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Test that user with no matching role is rejected."""
        dependency = current_user(any_of_roles=["admin", "moderator"])

        with pytest.raises(HTTPException) as exc_info:
            await dependency(
                request=_make_request(),
                session=db_session,
                credentials=_credentials_for(test_user),
            )

        assert exc_info.value.status_code == 403
        assert "Not enough permissions" in str(exc_info.value.detail)


@pytest.mark.asyncio
class TestCurrentUserTestEmailHeader:
    """The TESTING-only ``X-Test-User-Email`` branch inside ``_current_user``.

    The E2E suite authenticates with this header instead of a token, so the
    branch still has to enforce the active check and the role check. It survived
    the move to local authentication because in CI the Playwright browser origin
    and ``VITE_API_URL=http://backend:8787`` are genuinely cross-site: a
    ``SameSite=Lax`` refresh cookie is silently dropped there, and
    ``SameSite=None`` requires ``Secure`` requires HTTPS. A real-login E2E suite
    would pass on a developer's machine and fail only in CI.
    """

    async def test_header_resolves_user_without_a_token(
        self,
        db_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A known test email is resolved with no Authorization header at all."""
        monkeypatch.setattr(settings, "TESTING", True)
        request = _make_request(headers={"X-Test-User-Email": "test@example.com"})
        dependency = current_user()

        user = await dependency(request=request, session=db_session, credentials=None)

        assert user.id == test_user.id

    async def test_header_wins_over_a_stale_token(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_admin_user: User,
        make_expired_access_token: RawTokenFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The header is checked first, so a dead token cannot break the harness.

        The E2E fixtures inject the header on every request while the browser
        may still be holding whatever token it last saw. If the token were
        consulted first, an expired one would 401 a request the harness fully
        intended to succeed.
        """
        monkeypatch.setattr(settings, "TESTING", True)
        request = _make_request(headers={"X-Test-User-Email": "test@example.com"})
        dependency = current_user()

        user = await dependency(
            request=request,
            session=db_session,
            credentials=_bearer(make_expired_access_token(test_admin_user)),
        )

        assert user.id == test_user.id

    async def test_unknown_header_email_raises_401(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An unknown test email is rejected rather than auto-provisioned."""
        monkeypatch.setattr(settings, "TESTING", True)
        request = _make_request(headers={"X-Test-User-Email": "ghost@example.com"})
        dependency = current_user()

        with pytest.raises(HTTPException) as exc_info:
            await dependency(request=request, session=db_session, credentials=None)

        assert exc_info.value.status_code == 401
        assert "Test user not found: ghost@example.com" in str(exc_info.value.detail)

    async def test_header_inactive_user_raises_403(
        self,
        db_session: AsyncSession,
        test_inactive_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The active check is enforced on the header branch too."""
        monkeypatch.setattr(settings, "TESTING", True)
        request = _make_request(headers={"X-Test-User-Email": "inactive@example.com"})
        dependency = current_user()

        with pytest.raises(HTTPException) as exc_info:
            await dependency(request=request, session=db_session, credentials=None)

        assert exc_info.value.status_code == 403
        assert "Inactive user" in str(exc_info.value.detail)

    async def test_header_inactive_user_allowed_when_active_not_required(
        self,
        db_session: AsyncSession,
        test_inactive_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``require_active=False`` (AnyUser) lets suspended accounts through."""
        monkeypatch.setattr(settings, "TESTING", True)
        request = _make_request(headers={"X-Test-User-Email": "inactive@example.com"})
        dependency = current_user(require_active=False)

        user = await dependency(request=request, session=db_session, credentials=None)

        assert user.id == test_inactive_user.id

    async def test_header_still_enforces_role_check(
        self,
        db_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The header is an authentication bypass, not an authorization one."""
        monkeypatch.setattr(settings, "TESTING", True)
        request = _make_request(headers={"X-Test-User-Email": "test@example.com"})
        dependency = current_user(required_roles="admin")

        with pytest.raises(HTTPException) as exc_info:
            await dependency(request=request, session=db_session, credentials=None)

        assert exc_info.value.status_code == 403
        assert "Not enough permissions" in str(exc_info.value.detail)

    async def test_header_is_ignored_when_not_testing(
        self,
        db_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Outside TESTING the header carries no authority at all.

        ``config.py`` already refuses to construct settings with TESTING on in
        production, so this is the second of two independent guards.
        """
        monkeypatch.setattr(settings, "TESTING", False)
        request = _make_request(headers={"X-Test-User-Email": "ghost@example.com"})
        dependency = current_user()

        user = await dependency(
            request=request,
            session=db_session,
            credentials=_credentials_for(test_user),
        )

        assert user.id == test_user.id

    async def test_header_without_testing_and_without_token_raises_401(
        self,
        db_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Outside TESTING the header is not merely outranked — it is nothing."""
        monkeypatch.setattr(settings, "TESTING", False)
        request = _make_request(headers={"X-Test-User-Email": "test@example.com"})
        dependency = current_user()

        with pytest.raises(HTTPException) as exc_info:
            await dependency(request=request, session=db_session, credentials=None)

        assert exc_info.value.status_code == 401
        assert _problem_code(exc_info.value) == "auth.invalid_token"


@pytest.mark.asyncio
class TestGetDb:
    """``get_db`` registers the transaction on the per-endpoint exit stack.

    Every route test runs with ``get_db`` overridden, so the real body is only
    exercised here. Both halves matter: the normal path (COMMIT before the
    response is sent) and the fallback for a FastAPI that stops exposing
    ``fastapi_function_astack``.
    """

    async def test_uses_endpoint_exit_stack_when_present(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The transaction is entered on the stack FastAPI put in the scope."""
        factory = _FakeSessionFactory(db_session)
        monkeypatch.setattr(deps_module, "async_session", factory)

        async with AsyncExitStack() as stack:
            request = _make_request(scope_extra={"fastapi_function_astack": stack})
            generator = get_db(request)

            session = await anext(generator)

            assert session is db_session
            assert factory.begin_calls == 1
            with pytest.raises(StopAsyncIteration):
                await anext(generator)

    async def test_falls_back_when_scope_has_no_stack(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without the stack the dep owns the transaction itself."""
        factory = _FakeSessionFactory(db_session)
        monkeypatch.setattr(deps_module, "async_session", factory)
        request = _make_request()
        generator = get_db(request)

        session = await anext(generator)

        assert session is db_session
        assert factory.begin_calls == 1
        with pytest.raises(StopAsyncIteration):
            await anext(generator)

    async def test_falls_back_when_scope_entry_is_not_a_stack(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A scope entry of the wrong type is treated as absent, not trusted."""
        factory = _FakeSessionFactory(db_session)
        monkeypatch.setattr(deps_module, "async_session", factory)
        request = _make_request(scope_extra={"fastapi_function_astack": object()})
        generator = get_db(request)

        session = await anext(generator)

        assert session is db_session
        assert factory.begin_calls == 1
        with pytest.raises(StopAsyncIteration):
            await anext(generator)


@pytest.mark.asyncio
class TestGetUserFromQueryToken:
    """``_get_user_from_query_token`` — the SSE ``?token=…`` authentication dep.

    ``EventSource`` cannot send headers, so this is a second, independent entry
    point into the authorization boundary and it verifies the same tokens the
    header path does. It opens its own short-lived sessions off the module-level
    factory — a request-scoped session would hold a pooled connection for as
    long as the user leaves the tab open — which is why every test below
    redirects that factory at the transactional test session.
    """

    async def test_testing_query_param_resolves_user(
        self,
        db_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``?test_email=`` resolves a real user while TESTING."""
        monkeypatch.setattr(settings, "TESTING", True)
        monkeypatch.setattr(
            deps_module, "async_session", _FakeSessionFactory(db_session)
        )
        request = _make_request(query_string="token=unused&test_email=test@example.com")

        user = await _get_user_from_query_token(request, token="unused")

        assert user.id == test_user.id

    async def test_testing_header_resolves_user(
        self,
        db_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The X-Test-User-Email header is accepted as well as the query param."""
        monkeypatch.setattr(settings, "TESTING", True)
        monkeypatch.setattr(
            deps_module, "async_session", _FakeSessionFactory(db_session)
        )
        request = _make_request(
            query_string="token=unused",
            headers={"X-Test-User-Email": "test@example.com"},
        )

        user = await _get_user_from_query_token(request, token="unused")

        assert user.id == test_user.id

    async def test_testing_unknown_email_raises_401(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An unknown test email is rejected instead of being provisioned."""
        monkeypatch.setattr(settings, "TESTING", True)
        monkeypatch.setattr(
            deps_module, "async_session", _FakeSessionFactory(db_session)
        )
        request = _make_request(
            query_string="token=unused&test_email=ghost@example.com"
        )

        with pytest.raises(HTTPException) as exc_info:
            await _get_user_from_query_token(request, token="unused")

        assert exc_info.value.status_code == 401
        assert "Test user not found: ghost@example.com" in str(exc_info.value.detail)

    async def test_testing_without_test_email_falls_through_to_token(
        self,
        db_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """TESTING alone is not a bypass — without a test email the JWT is used."""
        monkeypatch.setattr(settings, "TESTING", True)
        monkeypatch.setattr(
            deps_module, "async_session", _FakeSessionFactory(db_session)
        )
        token = _token_for(test_user.id)
        request = _make_request(query_string=f"token={token}")

        user = await _get_user_from_query_token(request, token=token)

        assert user.id == test_user.id

    async def test_valid_token_returns_the_user(
        self,
        db_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Outside TESTING the query token is verified and mapped to a user."""
        monkeypatch.setattr(settings, "TESTING", False)
        factory = _FakeSessionFactory(db_session)
        monkeypatch.setattr(deps_module, "async_session", factory)
        request = _make_request(query_string="token=sse-token")

        user = await _get_user_from_query_token(request, token=_token_for(test_user.id))

        assert user.id == test_user.id
        # One short-lived session, opened and closed before the stream starts.
        assert factory.begin_calls == 1

    async def test_token_for_a_deleted_account_raises_401(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A stale token does not re-create the account it names."""
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(
            deps_module, "async_session", _FakeSessionFactory(db_session)
        )
        request = _make_request(query_string="token=sse-token")

        with pytest.raises(HTTPException) as exc_info:
            await _get_user_from_query_token(request, token=_token_for(uuid.uuid4()))

        assert exc_info.value.status_code == 401
        assert _problem_code(exc_info.value) == "auth.invalid_token"

    async def test_expired_token_raises_401(
        self,
        db_session: AsyncSession,
        test_user: User,
        make_expired_access_token: RawTokenFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An SSE connection cannot outlive its token by reconnecting with it."""
        monkeypatch.setattr(settings, "TESTING", False)
        factory = _FakeSessionFactory(db_session)
        monkeypatch.setattr(deps_module, "async_session", factory)
        request = _make_request(query_string="token=expired")

        with pytest.raises(HTTPException) as exc_info:
            await _get_user_from_query_token(
                request, token=make_expired_access_token(test_user)
            )

        assert exc_info.value.status_code == 401
        assert _problem_code(exc_info.value) == "auth.token_expired"
        # Rejected before any connection was taken from the pool.
        assert factory.begin_calls == 0

    async def test_a_token_for_a_list_guest_raises_403(
        self,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A guest of a shared list never holds a token; if one were minted,
        the stream would not open for it either."""
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(
            deps_module, "async_session", _FakeSessionFactory(db_session)
        )
        guest = await make_list_guest(test_shared_list)
        request = _make_request(query_string="token=sse-token")

        with pytest.raises(HTTPException) as exc_info:
            await _get_user_from_query_token(request, token=_token_for(guest.user.id))

        assert exc_info.value.status_code == 403
        assert _problem_code(exc_info.value) == "auth.guest_account"

    async def test_testing_email_of_a_list_guest_raises_403(
        self,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A guest has no ``users.email`` to be found by; given one anyway, the
        ``?test_email=`` path refuses it as the token path does."""
        monkeypatch.setattr(settings, "TESTING", True)
        monkeypatch.setattr(
            deps_module, "async_session", _FakeSessionFactory(db_session)
        )
        guest = await make_list_guest(test_shared_list)
        guest.user.email = "listguest@example.org"
        db_session.add(guest.user)
        await db_session.flush()
        request = _make_request(
            query_string="token=unused&test_email=listguest@example.org"
        )

        with pytest.raises(HTTPException) as exc_info:
            await _get_user_from_query_token(request, token="unused")

        assert exc_info.value.status_code == 403
        assert _problem_code(exc_info.value) == "auth.guest_account"

    async def test_garbage_token_raises_401(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Any verification failure becomes a flat 401, never a 500."""
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(
            deps_module, "async_session", _FakeSessionFactory(db_session)
        )
        request = _make_request(query_string="token=nonsense")

        with pytest.raises(HTTPException) as exc_info:
            await _get_user_from_query_token(request, token="nonsense")

        assert exc_info.value.status_code == 401
        assert _problem_code(exc_info.value) == "auth.invalid_token"


@pytest.mark.asyncio
class TestAuthenticationOverHttp:
    """The whole chain, through a real request, with nothing overridden.

    Everything above calls the dependencies directly, which is the right way to
    cover their branches but proves nothing about the wiring: ``HTTPBearer``
    parsing the header, FastAPI resolving the dependency, and the exception
    handler turning ``raise_problem`` into a problem+json body all sit outside
    those calls. This class closes that gap, and in doing so pins down the
    contract ``unauthenticated_client`` exists to provide — that a request it
    sends is genuinely anonymous until it carries a token.
    """

    async def test_anonymous_request_is_refused(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """No Authorization header means 401, and a body naming the reason."""
        response = await unauthenticated_client.get("/api/v1/users/me")

        assert response.status_code == 401
        assert response.json()["code"] == "auth.invalid_token"
        assert response.headers["www-authenticate"] == "Bearer"

    async def test_bearer_token_is_accepted(
        self,
        unauthenticated_client: AsyncClient,
        auth_headers: AuthHeadersFactory,
        test_user: User,
    ) -> None:
        """A minted token resolves to its account through the real chain."""
        response = await unauthenticated_client.get(
            "/api/v1/users/me", headers=auth_headers(test_user)
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(test_user.id)
        assert body["sub"] == test_user.subject

    async def test_expired_token_is_refused_with_its_own_code(
        self,
        unauthenticated_client: AsyncClient,
        make_expired_access_token: RawTokenFactory,
        test_user: User,
    ) -> None:
        """The code survives the trip through the exception handler.

        The frontend refreshes on ``auth.token_expired`` and sends the user back
        to the login form on anything else, so this is the one distinction that
        has to be intact in the serialised response and not merely in the
        exception.
        """
        token = make_expired_access_token(test_user)
        response = await unauthenticated_client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 401
        assert response.json()["code"] == "auth.token_expired"

    async def test_a_non_bearer_scheme_is_refused(
        self,
        unauthenticated_client: AsyncClient,
        auth_headers: AuthHeadersFactory,
        test_user: User,
    ) -> None:
        """``Basic <token>`` is not a bearer credential, however valid the token."""
        token = auth_headers(test_user)["Authorization"].split(" ", 1)[1]
        response = await unauthenticated_client.get(
            "/api/v1/users/me", headers={"Authorization": f"Basic {token}"}
        )

        assert response.status_code == 401
