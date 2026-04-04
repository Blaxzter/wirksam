from collections.abc import AsyncGenerator, Callable, Coroutine, Iterable
from typing import Annotated, Any, cast

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi_plugin import Auth0FastAPI  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import async_session
from app.crud.user import user as crud_user
from app.models.user import User
from app.schemas.user import UserCreate

_CurrentUserDep = Callable[..., Coroutine[Any, Any, User]]


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session.begin() as session:
        yield session


DBDep = Annotated[AsyncSession, Depends(get_db)]


auth0 = Auth0FastAPI(
    domain=settings.AUTH0_DOMAIN,
    audience=settings.AUTH0_AUDIENCE,
)

if settings.TESTING:
    _real_require_auth = auth0.require_auth

    def _test_aware_require_auth() -> Callable[
        ..., Coroutine[Any, Any, dict[str, Any]]
    ]:
        """Auth dependency that bypasses JWT validation only when
        the X-Test-User-Email header is present.
        Real Auth0 tokens still work in local dev.
        """
        real_dep = cast(Callable[[Request], Any], _real_require_auth())

        async def _auth(request: Request) -> dict[str, Any]:
            if request.headers.get("X-Test-User-Email"):
                return {"sub": "test|noop"}
            result: dict[str, Any] = await real_dep(request)
            return result

        return _auth

    auth0.require_auth = _test_aware_require_auth  # type: ignore[assignment]


def _normalize_required_roles(
    required_roles: str | Iterable[str] | None,
) -> list[str]:
    if required_roles is None:
        return []
    if isinstance(required_roles, str):
        return [required_roles]
    return list(required_roles)


async def get_or_create_user(
    session: AsyncSession,
    claims: dict[str, Any],
    profile_data: dict[str, Any] | None = None,
) -> User:
    """Get existing user or create new one with optional profile data from frontend.

    Args:
        session: Database session
        claims: Auth0 JWT claims
        profile_data: Optional profile data from frontend (email, name) for user creation
    """
    auth0_sub: str | None = claims.get("sub")
    if not auth0_sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication payload",
        )

    user = await crud_user.get_by_auth0_sub(session, auth0_sub=auth0_sub)
    if user:
        dirty = False
        # Ensure superadmin emails always have the admin role
        if user.email and user.email in [str(e) for e in settings.SUPERADMIN_EMAILS]:
            if "admin" not in user.roles:
                user.roles = list(user.roles) + ["admin"]
                dirty = True
            if not user.is_active:
                user.is_active = True
                dirty = True
        # Sync profile data from Auth0 on each login
        if profile_data:
            picture = profile_data.get("picture")
            if picture and picture != user.picture:
                user.picture = picture
                dirty = True
            ev = profile_data.get("email_verified")
            if ev is not None and bool(ev) != user.email_verified:
                user.email_verified = bool(ev)
                dirty = True
        if dirty:
            session.add(user)
            await session.flush()
        return user

    # Use profile_data from frontend if available, fallback to claims
    email: str | None = None
    name: str | None = None
    picture: str | None = None
    email_verified: bool = False
    preferred_language: str = "en"
    if profile_data:
        email = profile_data.get("email")
        name = profile_data.get("name") or profile_data.get("nickname")
        picture = profile_data.get("picture")
        email_verified = bool(profile_data.get("email_verified"))
        preferred_language = profile_data.get("preferred_language") or "en"

    # Fallback to claims if profile_data not provided
    if not email:
        email = claims.get("email")
    if not name:
        name = claims.get("name") or claims.get("nickname")
    if not picture:
        picture = claims.get("picture")

    is_superadmin = bool(
        email and email in [str(e) for e in settings.SUPERADMIN_EMAILS]
    )
    user_in = UserCreate(
        auth0_sub=auth0_sub,
        email=email,
        name=name,
        picture=picture,
        email_verified=email_verified,
        roles=["admin"] if is_superadmin else [],
        is_active=is_superadmin,
        preferred_language=preferred_language,
    )
    new_user = await crud_user.create(session, obj_in=user_in)

    # Notify admins about new user registration (fire-and-forget)
    if not is_superadmin:
        import asyncio

        from app.logic.notifications.triggers import dispatch_user_registered

        asyncio.create_task(
            dispatch_user_registered(
                user_id=new_user.id,
                user_name=new_user.name,
                user_email=new_user.email,
            )
        )

    return new_user


def current_user(
    required_roles: str | Iterable[str] | None = None,
    *,
    require_active: bool = True,
) -> _CurrentUserDep:
    required_roles_list = _normalize_required_roles(required_roles)

    async def _current_user(
        request: Request,
        session: DBDep,
        claims: dict[str, Any] = Depends(auth0.require_auth()),  # type: ignore[assignment]
    ) -> User:
        # In test mode, use X-Test-User-Email header instead of Auth0 claims
        if settings.TESTING:
            test_email = request.headers.get("X-Test-User-Email")
            if test_email:
                user = await crud_user.get_by_email(session, email=test_email)
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"Test user not found: {test_email}",
                    )
                if require_active and not user.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Inactive user",
                    )
                if required_roles_list and not set(required_roles_list).issubset(
                    set(user.roles)
                ):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not enough permissions",
                    )
                return user

        user = await get_or_create_user(session, claims)

        if require_active and not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user",
            )

        if required_roles_list and not set(required_roles_list).issubset(
            set(user.roles)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

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
    """
    if settings.TESTING:
        test_email = request.query_params.get("test_email") or request.headers.get(
            "X-Test-User-Email"
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

    try:
        claims: dict[str, Any] = await auth0.api_client.verify_request(  # type: ignore[union-attr]
            headers={"authorization": f"Bearer {token}"},
            http_method="GET",
            http_url=str(request.url),
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    async with async_session.begin() as session:
        return await get_or_create_user(session, claims)


QueryTokenUser = Annotated[User, Depends(_get_user_from_query_token)]
