"""FastAPI app and client fixtures for testing."""

from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager
from typing import Any, get_args

import pytest_asyncio
from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps as deps_module
from app.main import app as fastapi_app
from app.models.user import User


def _identity_dependency(alias: Any) -> Any:
    """Extract the callable FastAPI keys a dependency override by.

    ``CurrentUser`` and friends are ``Annotated[User, Depends(current_user())]``,
    and ``dependency_overrides`` is keyed by the object inside that ``Depends``
    — not by the alias, and not by ``current_user`` itself, which is a *factory*
    returning a fresh closure per call site.

    This reaching-in is fragile by nature, so it is written once here rather
    than at the four call sites it used to be spelled out at. If ``deps.py``
    ever stops using the ``Annotated[..., Depends(...)]`` shape, this function
    raises immediately instead of the overrides quietly failing to apply — which
    would leave every route test hitting real authentication and 401ing, all at
    once, for a reason nothing in the failure output would name.
    """
    metadata = get_args(alias)[1]
    dependency = getattr(metadata, "dependency", None)
    if dependency is None:  # pragma: no cover - guards a refactor, not a branch
        raise TypeError(
            f"{alias} is no longer an Annotated[..., Depends(...)] alias, so test "
            "dependency overrides cannot be keyed off it. Update "
            "tests/fixtures/client.py together with app/api/deps.py."
        )
    return dependency


@pytest_asyncio.fixture
async def app(
    db_session: AsyncSession,
    test_user: User,
) -> AsyncGenerator[FastAPI, None]:
    """FastAPI app with test dependency overrides.

    Three identity dependencies survive the self-service refactor:
    ``CurrentUser``, ``AnyUser`` and ``CurrentSuperuser``. Everything that used
    to be a global manager role is now a per-event membership, so tests grant
    access by inserting an ``EventMembership`` rather than by swapping a
    dependency.

    Identity is pinned here rather than authenticated: the point of a route
    test is the route, and making all ~500 of them mint and present a real
    token would test ``deps.py`` five hundred times over. The real credential
    path has its own coverage — ``tests/api/test_deps.py`` for the dependency
    and ``unauthenticated_client`` below for the endpoints that must work
    without one.

    ``AnyUser`` is pinned alongside ``CurrentUser`` and not left to run for
    real. It is a *separate* closure, so leaving it out meant the two endpoints
    that use it (``GET`` and ``DELETE /users/me``) answered 401 to an otherwise
    perfectly ordinary route test, with nothing in the failure naming the
    reason. Only ``CurrentSuperuser`` still denies by default, because that one
    is a genuine authorisation boundary rather than a question of who is
    calling.
    """

    # KNOWN GAP, worth knowing before you trust a test here. The real
    # ``deps.get_db`` owns its transaction via ``async_session.begin()`` inside
    # an exit stack, so a route that raises unwinds that stack and ROLLS THE
    # REQUEST BACK. This override yields the savepoint-wrapped ``db_session``
    # with no such context manager, so writes made on the way to an error
    # response survive here and do not survive in production.
    #
    # That difference already hid one real bug: refresh-token reuse detection
    # revoked every session and then raised 401, and the 401 rolled the
    # revocation back — invisible to a passing test, found only by driving a
    # live server. ``logic/auth/tokens.py`` now commits explicitly before
    # raising. If you write a route that must persist something *and* return an
    # error, do not let this fixture convince you it works.
    async def override_get_db():
        yield db_session

    async def override_current_user():
        return test_user

    # CurrentSuperuser denies by default — use the as_admin fixture for the
    # handful of endpoints that are still platform-wide.
    async def override_deny():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )

    user_dep = _identity_dependency(deps_module.CurrentUser)
    any_user_dep = _identity_dependency(deps_module.AnyUser)
    superuser_dep = _identity_dependency(deps_module.CurrentSuperuser)

    installed: dict[Any, Any] = {
        deps_module.get_db: override_get_db,
        user_dep: override_current_user,
        any_user_dep: override_current_user,
        superuser_dep: override_deny,
    }
    fastapi_app.dependency_overrides.update(installed)

    yield fastapi_app

    # Targeted removal rather than ``dependency_overrides = {}``. Wiping the
    # whole dict also discards anything another fixture installed — including
    # ``unauthenticated_app``'s — and does so at whatever point pytest happens
    # to tear this one down.
    for dep in installed:
        fastapi_app.dependency_overrides.pop(dep, None)


@pytest_asyncio.fixture
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def unauthenticated_app(
    db_session: AsyncSession,
) -> AsyncGenerator[FastAPI, None]:
    """The app with a test database and **no** identity override at all.

    The ``app`` fixture above pins ``CurrentUser`` unconditionally, which makes
    it useless for the endpoints that exist precisely because nobody is signed
    in yet: register, login, refresh, forgot-password, reset-password and
    verify-email. A test of ``POST /auth/login`` written against ``async_client``
    would be issued *by an already-authenticated caller* and would still pass
    while the whole credential path was broken.

    Here the identity dependencies run for real, so a request without an
    ``Authorization`` header is genuinely anonymous and a request with one is
    resolved by ``decode_access_token`` — see the ``auth_headers`` fixture for
    minting the latter.

    Any identity override already in place (from ``app``, if a test happens to
    request both) is removed for the duration and restored afterwards, so the
    two fixtures cannot silently defeat each other depending on ordering.
    """

    async def override_get_db():
        yield db_session

    suspended: dict[Any, Any] = {}
    for alias in (
        deps_module.CurrentUser,
        deps_module.CurrentSuperuser,
        deps_module.AnyUser,
    ):
        dep = _identity_dependency(alias)
        if dep in fastapi_app.dependency_overrides:
            suspended[dep] = fastapi_app.dependency_overrides.pop(dep)

    if deps_module.get_db in fastapi_app.dependency_overrides:
        suspended[deps_module.get_db] = fastapi_app.dependency_overrides.pop(
            deps_module.get_db
        )
    fastapi_app.dependency_overrides[deps_module.get_db] = override_get_db

    yield fastapi_app

    fastapi_app.dependency_overrides.pop(deps_module.get_db, None)
    fastapi_app.dependency_overrides.update(suspended)


@pytest_asyncio.fixture
async def unauthenticated_client(
    unauthenticated_app: FastAPI,
) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client that is nobody until it presents a credential.

    ``base_url`` keeps the ``http://test`` origin the rest of the suite uses so
    that ``Set-Cookie`` on the refresh cookie is accepted by httpx's cookie jar
    and replayed on the next request — which is the only way to exercise the
    login -> refresh -> logout sequence the way a browser does.
    """
    transport = ASGITransport(app=unauthenticated_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _swap_identity(app: FastAPI, user: User, *, superuser: bool):
    """Point CurrentUser and AnyUser (and optionally CurrentSuperuser) at ``user``.

    ``AnyUser`` moves with the others so that "act as X" means the same thing on
    every endpoint. Leaving it behind would make ``GET /users/me`` keep
    answering as ``test_user`` in the middle of an ``as_admin`` block — a
    difference that reads as a bug in the route.
    """
    user_dep: Any = _identity_dependency(deps_module.CurrentUser)
    any_user_dep: Any = _identity_dependency(deps_module.AnyUser)
    superuser_dep: Any = _identity_dependency(deps_module.CurrentSuperuser)
    originals = {
        dep: app.dependency_overrides.get(dep)
        for dep in (user_dep, any_user_dep, superuser_dep)
    }

    async def override():
        return user

    async def override_deny():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )

    app.dependency_overrides[user_dep] = override
    app.dependency_overrides[any_user_dep] = override
    app.dependency_overrides[superuser_dep] = override if superuser else override_deny
    return originals


def _restore(app: FastAPI, originals: dict[Any, Any]) -> None:
    for dep, original in originals.items():
        if original:
            app.dependency_overrides[dep] = original
        else:
            app.dependency_overrides.pop(dep, None)


@contextmanager
def act_as(app: FastAPI, user: User) -> Generator[None]:
    """Switch identity for part of a test, then switch back.

    For tests that need several people in turn (a member, a lead, an admin).
    ``CurrentSuperuser`` keeps denying, as for any non-superadmin.
    """
    originals = _swap_identity(app, user, superuser=False)
    try:
        yield
    finally:
        _restore(app, originals)


@pytest_asyncio.fixture
async def as_admin(app: FastAPI, test_admin_user: User) -> AsyncGenerator[None, None]:
    """Act as the platform superadmin."""
    originals = _swap_identity(app, test_admin_user, superuser=True)
    yield
    _restore(app, originals)


@pytest_asyncio.fixture
async def as_event_admin(
    app: FastAPI, test_event_admin_user: User
) -> AsyncGenerator[None, None]:
    """Act as someone who administers the fixture events but holds no global role.

    Pair with ``test_event`` / ``test_draft_event``, which grant this user the
    ``admin`` membership. CurrentSuperuser still denies — an event admin is
    not a platform admin.
    """
    originals = _swap_identity(app, test_event_admin_user, superuser=False)
    yield
    _restore(app, originals)


@pytest_asyncio.fixture
async def as_outsider(
    app: FastAPI, test_outsider_user: User
) -> AsyncGenerator[None, None]:
    """Act as a signed-in user who belongs to no event at all."""
    originals = _swap_identity(app, test_outsider_user, superuser=False)
    yield
    _restore(app, originals)
