import logging
import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    CurrentSuperuser,
    CurrentUser,
    DBDep,
    _get_or_create_user,
    auth0,
)
from app.core.config import settings
from app.core.security import verify_password
from app.crud.site_settings import site_settings as crud_site_settings
from app.crud.user import user as crud_user
from app.logic.auth0.auth0_service import delete_auth0_user, update_auth0_user
from app.models.user import User
from app.schemas.site_settings import SelfApproveRequest
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.schemas.users import ProfileInit, UserProfile, UserProfileUpdate

logger = logging.getLogger(__name__)

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

    Note: This endpoint does NOT check is_active, so even pending users
    can retrieve their profile status after registering.
    """
    profile_dict = profile_init.model_dump() if profile_init else None
    user = await _get_or_create_user(session, claims, profile_data=profile_dict)

    return UserProfile(
        sub=claims["sub"],
        name=user.name,
        email=user.email,
        picture=user.picture,
        email_verified=user.email_verified,
        roles=user.roles,
        is_admin=user.is_admin,
        is_active=user.is_active,
        rejection_reason=user.rejection_reason,
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

    return UserProfile(
        sub=claims["sub"],
        name=user_update.name if user_update.name is not None else current_user.name,
        email=current_user.email,
        picture=(
            user_update.picture
            if user_update.picture is not None
            else current_user.picture
        ),
        email_verified=current_user.email_verified,
        bio=user_update.bio,
        nickname=user_update.nickname,
        roles=current_user.roles,
        is_admin=current_user.is_admin,
        is_active=current_user.is_active,
    )


@router.get("/approval-password-status")
async def get_approval_password_status(
    session: DBDep,
    claims: dict[str, Any] = Depends(auth0.require_auth()),  # type: ignore[assignment]
) -> dict[str, bool]:
    """Check whether an approval password is configured.

    Available to any authenticated user (including inactive/pending users)
    so the pending-approval page knows whether to show the password input.
    """
    _ = claims  # just need valid JWT
    site_settings = await crud_site_settings.get(session)
    return {"has_approval_password": site_settings.approval_password is not None}


@router.post("/self-approve", response_model=UserProfile)
async def self_approve(
    body: SelfApproveRequest,
    session: DBDep,
    claims: dict[str, Any] = Depends(auth0.require_auth()),  # type: ignore[assignment]
) -> UserProfile:
    """Allow a pending user to self-approve by providing the approval password.

    Does NOT require is_active so that pending users can call this.
    Returns 400 if the user is already active or rejected.
    Returns 403 if no approval password is configured or the password is wrong.
    """
    user = await _get_or_create_user(session, claims)

    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already active",
        )
    if user.rejection_reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has been rejected",
        )

    site_settings = await crud_site_settings.get(session)
    if not site_settings.approval_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-approval is not enabled",
        )

    if not verify_password(body.password, site_settings.approval_password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid approval password",
        )

    user.is_active = True
    session.add(user)
    await session.flush()

    return UserProfile(
        sub=claims["sub"],
        name=user.name,
        email=user.email,
        picture=user.picture,
        email_verified=user.email_verified,
        roles=user.roles,
        is_admin=user.is_admin,
        is_active=user.is_active,
        rejection_reason=user.rejection_reason,
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


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_current_user(
    session: DBDep,
    claims: dict[str, Any] = Depends(auth0.require_auth()),  # type: ignore[assignment]
) -> None:
    """Delete the currently authenticated user's account.

    This endpoint does NOT require is_active so that pending users
    can revoke their approval request before being activated.

    This will:
    1. Delete all user data (projects, tasks) from the database
    2. Delete the user record from the database
    3. Delete the user from Auth0
    """
    auth0_sub: str | None = claims.get("sub")
    if not auth0_sub:
        raise HTTPException(status_code=400, detail="User ID not found in token")

    user = await _get_or_create_user(session, claims)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete user from Auth0 first — if this fails, we abort to keep things consistent
    auth0_deleted = await delete_auth0_user(auth0_sub)
    if not auth0_deleted:
        raise HTTPException(
            status_code=500,
            detail="Failed to delete account from authentication provider",
        )

    # Delete user from DB (cascades to projects → tasks)
    await session.delete(user)
    await session.commit()

    logger.info("User account deleted: %s", auth0_sub)


@router.delete("/{user_id}", response_model=UserRead)
async def delete_user(
    user_id: uuid.UUID,
    session: DBDep,
    _: CurrentSuperuser,
) -> User:
    """Admin-only: delete a user by ID from the database."""
    user = await crud_user.get(session, id=user_id, raise_404_error=True)
    # Also delete from Auth0
    await delete_auth0_user(user.auth0_sub)
    await session.delete(user)
    await session.commit()
    return user
