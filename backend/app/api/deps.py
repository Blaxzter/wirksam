"""Request-scoped dependencies: the database session and the caller's identity.

Identity used to arrive here as a set of claims validated by a remote issuer.
It now arrives as an HS256 JWT this application minted itself (see
``app.core.security``), which changes exactly two things and nothing else:

* verification is local, so there is no JWKS cache to warm and no third-party
  outage that can lock everyone out; and
* ``sub`` is the ``users.id`` primary key rather than an opaque external
  subject string, so resolving a request to a ``User`` is a single primary-key
  lookup with no second identity path to keep in sync.

Everything downstream — roles, ``EventMembership``, ``logic.permissions`` —
was already pure database logic and is untouched. This module is the only
place that knows how a credential becomes a ``User``.
"""

from collections.abc import AsyncGenerator, Callable, Coroutine, Iterable
from contextlib import AsyncExitStack
from typing import Annotated, Any, Final

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import async_session
from app.core.errors import raise_problem
from app.core.security import AccessClaims, AuthTokenError, decode_access_token
from app.crud.user import user as crud_user
from app.models.user import User

_CurrentUserDep = Callable[..., Coroutine[Any, Any, User]]


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped session that COMMITs before the response is sent.

    FastAPI finalises ``yield`` dependencies only *after* the response has gone
    out to the client (``request_response`` in ``fastapi.routing`` awaits the
    response, then unwinds its exit stack). Owning the transaction here meant
    the COMMIT landed after the client already had its answer, so a client that
    immediately issued a follow-up request could race it and read stale data —
    a freshly created event 404ing, a just-granted permission still 403ing.

    FastAPI keeps a second, per-endpoint exit stack that unwinds *before* the
    response is sent. Registering the transaction there moves the COMMIT ahead
    of the response, and it also means background tasks (which run while the
    response is being sent) observe the data they were handed IDs for.
    """
    stack = request.scope.get("fastapi_function_astack")
    if not isinstance(stack, AsyncExitStack):
        # No per-endpoint stack (e.g. a future FastAPI that drops it) — fall
        # back to the previous behaviour rather than failing the request.
        async with async_session.begin() as session:
            yield session
        return
    session: AsyncSession = await stack.enter_async_context(  # pyright: ignore[reportUnknownMemberType]
        async_session.begin()
    )
    yield session


DBDep = Annotated[AsyncSession, Depends(get_db)]


# The E2E impersonation header. The entire Playwright suite authenticates
# through it (``frontend/e2e/fixtures.ts``, ``frontend/src/testing``), which is
# why it survived the move off a remote issuer: in CI the browser origin and
# ``VITE_API_URL=http://backend:8787`` are genuinely cross-site, so the
# httpOnly refresh cookie a real login depends on is silently dropped. It is
# reachable only while ``settings.TESTING`` is true, and ``config.py`` refuses
# to construct settings with TESTING on in production.
TEST_USER_EMAIL_HEADER: Final = "X-Test-User-Email"

# RFC 6750 says a 401 on a bearer-protected resource names the scheme. Browsers
# only pop a credential dialog for ``Basic``, so this is safe to send and lets
# a client tell "no/!bad token" apart from an authorisation failure.
_WWW_AUTHENTICATE: Final[dict[str, str]] = {"WWW-Authenticate": "Bearer"}

# ``auto_error=False`` on purpose: the built-in 403 that FastAPI raises for a
# missing Authorization header is both the wrong status and the wrong body
# shape. Returning ``None`` lets us decide — a problem+json 401 with an
# ``auth.*`` code the frontend can switch on, or, under TESTING, the header
# bypass below.
_bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Access token issued by POST /auth/login or /auth/refresh.",
)


def _decode_bearer_token(token: str) -> AccessClaims:
    """Validate a raw access token, translating failures into problem+json.

    ``AuthTokenError`` already carries the ``auth.*`` code and a user-facing
    sentence, so the two failure modes the client must distinguish —
    ``auth.token_expired`` ("refresh and retry") and ``auth.invalid_token``
    ("sign in again") — come straight from ``core.security`` rather than being
    re-derived here from the exception type.
    """
    try:
        return decode_access_token(token)
    except AuthTokenError as exc:
        raise_problem(
            status.HTTP_401_UNAUTHORIZED,
            code=exc.code,
            detail=str(exc),
            headers=_WWW_AUTHENTICATE,
        )


def _claims_from_credentials(
    credentials: HTTPAuthorizationCredentials | None,
) -> AccessClaims:
    """Require a bearer token and return its validated claims."""
    if credentials is None or not credentials.credentials:
        raise_problem(
            status.HTTP_401_UNAUTHORIZED,
            code="auth.invalid_token",
            detail="Please sign in to continue.",
            headers=_WWW_AUTHENTICATE,
        )
    return _decode_bearer_token(credentials.credentials)


async def get_access_claims(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
) -> AccessClaims:
    """Resolve the caller's access-token claims without touching the database.

    Useful where the *session* the request was made with matters and the user
    row does not — "sign out of every other device" needs the ``jti`` to know
    which session to spare. Anything that needs the account itself should take
    ``CurrentUser`` instead, which does this and the lookup in one step.
    """
    return _claims_from_credentials(credentials)


AccessClaimsDep = Annotated[AccessClaims, Depends(get_access_claims)]


def _normalize_required_roles(
    required_roles: str | Iterable[str] | None,
) -> list[str]:
    if required_roles is None:
        return []
    if isinstance(required_roles, str):
        return [required_roles]
    return list(required_roles)


def _refuse_unusable(user: User) -> None:
    """Turn away an account that may sign in but not use the app.

    Two different reasons, kept apart because the person needs to hear which
    one applies: a moderator suspended the account (``is_active``), or it is
    still in, or was turned away from, the registration queue that
    ``REGISTRATION_MODE=approval`` puts in front of signup.
    """
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    if user.approval_status == "pending":
        raise_problem(
            status.HTTP_403_FORBIDDEN,
            code="auth.account_pending",
            detail="This account is waiting for an administrator's approval.",
        )
    if user.approval_status != "approved":
        raise_problem(
            status.HTTP_403_FORBIDDEN,
            code="auth.account_rejected",
            detail="The registration for this account was not approved.",
        )


def current_user(
    required_roles: str | Iterable[str] | None = None,
    *,
    any_of_roles: str | Iterable[str] | None = None,
    require_active: bool = True,
) -> _CurrentUserDep:
    """Build a dependency resolving the caller to a ``User``.

    Only the platform-wide ``admin`` role is checked here. Anything scoped to
    a single event is decided by ``app.logic.permissions`` against that
    event's membership, not by a global role on the account.
    """
    required_roles_list = _normalize_required_roles(required_roles)
    any_of_roles_list = _normalize_required_roles(any_of_roles)

    async def _check_roles(session: AsyncSession, user: User) -> None:
        _ = session
        if required_roles_list and not set(required_roles_list).issubset(
            set(user.roles)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

        if any_of_roles_list and not set(any_of_roles_list).intersection(
            set(user.roles)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

    async def _current_user(
        request: Request,
        session: DBDep,
        credentials: Annotated[
            HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
        ],
    ) -> User:
        # In test mode, use X-Test-User-Email header instead of a real token.
        # Checked before the Authorization header so a stale or fake token in
        # the E2E harness cannot make an impersonated request fail.
        if settings.TESTING:
            test_email = request.headers.get(TEST_USER_EMAIL_HEADER)
            if test_email:
                user = await crud_user.get_by_email(session, email=test_email)
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"Test user not found: {test_email}",
                    )
                if require_active:
                    _refuse_unusable(user)
                await _check_roles(session, user)
                return user

        claims = _claims_from_credentials(credentials)

        # ``sub`` is the primary key, so this is the whole identity lookup.
        # There is no just-in-time provisioning any more: an account exists
        # because someone registered it, and a token naming a row that is gone
        # (a deleted account whose 15-minute token has not expired yet) is a
        # credential for nothing.
        user = await crud_user.get(session, claims.user_id)
        if user is None:
            raise_problem(
                status.HTTP_401_UNAUTHORIZED,
                code="auth.invalid_token",
                detail="This account no longer exists. Please sign in again.",
                headers=_WWW_AUTHENTICATE,
            )

        if require_active:
            _refuse_unusable(user)

        await _check_roles(session, user)

        return user

    return _current_user


CurrentUser = Annotated[User, Depends(current_user())]
CurrentSuperuser = Annotated[User, Depends(current_user("admin"))]
AnyUser = Annotated[User, Depends(current_user(require_active=False))]


async def _get_user_from_query_token(
    request: Request,
    token: str = Query(..., description="Bearer token for auth"),
) -> User:
    """Resolve user from a query-param JWT.

    EventSource doesn't support custom headers, so endpoints like SSE
    pass the token as ``?token=…``.  This dep opens short-lived sessions
    so the caller isn't pinned to one for the life of the connection.

    That last point is the reason this function does not take ``DBDep``: an
    SSE stream stays open for as long as the user keeps the tab open, and a
    request-scoped session would hold a pooled connection open for exactly
    that long. The session here is opened, used and closed before the stream
    starts producing.
    """
    if settings.TESTING:
        test_email = request.query_params.get("test_email") or request.headers.get(
            TEST_USER_EMAIL_HEADER
        )
        if test_email:
            async with async_session.begin() as session:
                user = await crud_user.get_by_email(session, email=test_email)
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"Test user not found: {test_email}",
                    )
                return user

    claims = _decode_bearer_token(token)

    async with async_session.begin() as session:
        user = await crud_user.get(session, claims.user_id)
        if user is None:
            raise_problem(
                status.HTTP_401_UNAUTHORIZED,
                code="auth.invalid_token",
                detail="This account no longer exists. Please sign in again.",
                headers=_WWW_AUTHENTICATE,
            )
        return user


QueryTokenUser = Annotated[User, Depends(_get_user_from_query_token)]
