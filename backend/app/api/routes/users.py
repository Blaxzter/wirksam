import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentSuperuser, CurrentUser, DBDep, auth0, current_user
from app.core.config import settings
from app.crud.user import user as crud_user
from app.logic.auth0.auth0_service import update_auth0_user
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.schemas.users import ProfileInit, UserProfile, UserProfileUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/me", response_model=UserProfile)
async def get_current_user_profile(
    profile_init: ProfileInit | None = None,
    *,
    session: DBDep,
    claims: dict[str, Any] = Depends(auth0.require_auth()),  # type: ignore[assignment]
) -> UserProfile:
    """Get current user profile information.

    Accepts optional profile data from frontend for user initialization.
    This allows the frontend to send email/name from Auth0 ID token
    when the user first logs in.
    """
    # Pass profile data to current_user dependency for potential user creation
    profile_dict = profile_init.model_dump() if profile_init else None
    user_dep = current_user(profile_data=profile_dict)
    current_user_obj = await user_dep(session, claims)

    return UserProfile(
        **claims,
        roles=current_user_obj.roles,
        is_admin=current_user_obj.is_admin,
        is_active=current_user_obj.is_active,
    )


@router.patch("/me", response_model=UserProfile)
async def update_user_profile(
    user_update: UserProfileUpdate,
    current_user: CurrentUser,
    claims: dict[str, Any] = Depends(auth0.require_auth()),  # type: ignore[assignment]
) -> UserProfile:
    """Update current user profile information using Auth0 Management API."""
    user_id: str | None = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID not found")

    # Update user in Auth0 using Management API
    success = await update_auth0_user(user_id, user_update)

    if not success:
        raise HTTPException(
            status_code=500, detail="Failed to update user profile in Auth0"
        )

    # Sync picture to local DB
    if user_update.picture is not None:
        current_user.picture = str(user_update.picture)

    # Return updated user data
    updated_user: dict[str, Any] = claims.copy()

    if user_update.name is not None:
        updated_user["name"] = user_update.name
    if user_update.nickname is not None:
        updated_user["nickname"] = user_update.nickname
    if user_update.picture is not None:
        updated_user["picture"] = str(user_update.picture)
    if user_update.bio is not None:
        updated_user["bio"] = user_update.bio

    return UserProfile(
        **updated_user,
        roles=current_user.roles,
        is_admin=current_user.is_admin,
        is_active=current_user.is_active,
    )


@router.get("/auth0-management-url")
async def get_auth0_management_url(
    _: CurrentUser,
) -> dict[str, str]:
    """Get the Auth0 management URL for advanced account settings."""
    return {
        "management_url": f"https://{settings.AUTH0_DOMAIN}/login",
        "note": "For email and password changes, please use Auth0's account management",
    }


@router.get("/", response_model=list[UserRead])
async def list_users(
    session: DBDep,
    _: CurrentSuperuser,
    skip: int = 0,
    limit: int = 100,
) -> Sequence[User]:
    return await crud_user.get_multi(session, skip=skip, limit=limit)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    session: DBDep,
    _: CurrentSuperuser,
) -> User:
    return await crud_user.get(session, id=user_id, raise_404_error=True)


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    session: DBDep,
    _: CurrentSuperuser,
) -> User:
    return await crud_user.create(session, obj_in=user_in)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    user_in: UserUpdate,
    session: DBDep,
    _: CurrentSuperuser,
) -> User:
    user = await crud_user.get(session, id=user_id, raise_404_error=True)
    return await crud_user.update(session, db_obj=user, obj_in=user_in)


@router.delete("/{user_id}", response_model=UserRead)
async def delete_user(
    user_id: uuid.UUID,
    session: DBDep,
    _: CurrentSuperuser,
) -> User:
    user = await crud_user.get(session, id=user_id, raise_404_error=True)
    await session.delete(user)
    await session.commit()
    return user
