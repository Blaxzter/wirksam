from collections.abc import AsyncGenerator, Callable, Coroutine, Iterable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
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


def _normalize_required_roles(
    required_roles: str | Iterable[str] | None,
) -> list[str]:
    if required_roles is None:
        return []
    if isinstance(required_roles, str):
        return [required_roles]
    return list(required_roles)


async def _get_or_create_user(
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
        # Sync picture from Auth0 on each login
        if profile_data:
            picture = profile_data.get("picture")
            if picture and picture != user.picture:
                user.picture = picture
                dirty = True
        if dirty:
            session.add(user)
            await session.flush()
        return user

    # Use profile_data from frontend if available, fallback to claims
    email: str | None = None
    name: str | None = None
    picture: str | None = None
    if profile_data:
        email = profile_data.get("email")
        name = profile_data.get("name") or profile_data.get("nickname")
        picture = profile_data.get("picture")

    # Fallback to claims if profile_data not provided
    if not email:
        email = claims.get("email")
    if not name:
        name = claims.get("name") or claims.get("nickname")
    if not picture:
        picture = claims.get("picture")

    is_superadmin = bool(email and email in [str(e) for e in settings.SUPERADMIN_EMAILS])
    user_in = UserCreate(
        auth0_sub=auth0_sub,
        email=email,
        name=name,
        picture=picture,
        roles=["admin"] if is_superadmin else [],
    )
    new_user = await crud_user.create(session, obj_in=user_in)
    return new_user


def current_user(
    required_roles: str | Iterable[str] | None = None,
    profile_data: dict[str, Any] | None = None,
) -> _CurrentUserDep:
    required_roles_list = _normalize_required_roles(required_roles)

    async def _current_user(
        session: DBDep,
        claims: dict[str, Any] = Depends(auth0.require_auth()),  # type: ignore[assignment]
    ) -> User:
        user = await _get_or_create_user(session, claims, profile_data)

        if not user.is_active:
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
