import logging
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlmodel import col

from app.api.deps import (
    AnyUser,
    CurrentSuperuser,
    CurrentUser,
    DBDep,
    auth0,
)
from app.core.config import settings
from app.core.security import verify_password
from app.crud.site_settings import site_settings as crud_site_settings
from app.crud.user import user as crud_user
from app.logic.auth0.auth0_service import delete_auth0_user, update_auth0_user
from app.models.booking import Booking
from app.models.notification import NotificationSubscription
from app.models.user import User
from app.models.user_availability import UserAvailability, UserAvailabilityDate
from app.schemas.site_settings import SelfApproveRequest
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.schemas.users import ProfileInit, UserProfile, UserProfileUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/me", response_model=UserProfile)
async def get_current_user_profile(
    user: AnyUser,
    profile_init: ProfileInit | None = None,
    *,
    session: DBDep,
) -> UserProfile:
    """Get current user profile information.

    Accepts optional profile data from frontend for user initialization.
    This allows the frontend to send email/name from Auth0 ID token
    when the user first logs in.

    Does NOT require is_active, so even pending users can retrieve
    their profile status after registering.
    """
    if profile_init:
        dirty = False
        for field in (
            "name",
            "email",
            "picture",
            "email_verified",
            "preferred_language",
        ):
            value = getattr(profile_init, field, None)
            if value is not None and getattr(user, field) != value:
                setattr(user, field, value)
                dirty = True

        # Auto-activate superadmin emails that were created before email was synced
        if user.email and user.email in [str(e) for e in settings.SUPERADMIN_EMAILS]:
            if "admin" not in user.roles:
                user.roles = list(user.roles) + ["admin"]
                dirty = True
            if not user.is_active:
                user.is_active = True
                dirty = True

        if dirty:
            session.add(user)
            await session.flush()

    return UserProfile.model_validate(user)


@router.patch("/me", response_model=UserProfile)
async def update_user_profile(
    user_update: UserProfileUpdate,
    current_user: CurrentUser,
) -> UserProfile:
    """Update current user profile information using Auth0 Management API."""
    auth0_sub = current_user.auth0_sub

    # In test mode, skip Auth0 Management API call
    if not settings.TESTING:
        success = await update_auth0_user(auth0_sub, user_update)
        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to update user profile in Auth0"
            )

    # Sync picture to local DB
    if user_update.picture is not None:
        current_user.picture = str(user_update.picture)

    # Sync phone_number to local DB
    if user_update.phone_number is not None:
        current_user.phone_number = user_update.phone_number

    # Sync preferred_language to local DB (no Auth0 call needed)
    if user_update.preferred_language is not None:
        current_user.preferred_language = user_update.preferred_language

    profile = UserProfile.model_validate(current_user)
    return profile.model_copy(
        update={
            k: v
            for k, v in {
                "name": user_update.name,
                "picture": str(user_update.picture)
                if user_update.picture is not None
                else None,
                "bio": user_update.bio,
                "nickname": user_update.nickname,
            }.items()
            if v is not None
        }
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
    user: AnyUser,
    body: SelfApproveRequest,
    session: DBDep,
) -> UserProfile:
    """Allow a pending user to self-approve by providing the approval password.

    Does NOT require is_active so that pending users can call this.
    Returns 400 if the user is already active or rejected.
    Returns 403 if no approval password is configured or the password is wrong.
    """
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

    return UserProfile.model_validate(user)


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
    background_tasks: BackgroundTasks,
) -> User:
    user = await crud_user.get(session, id=user_id, raise_404_error=True)
    was_active = user.is_active
    old_rejection = user.rejection_reason
    updated = await crud_user.update(session, db_obj=user, obj_in=user_in)

    # Dispatch approval/rejection notifications
    from app.logic.notifications.triggers import (
        dispatch_user_approved,
        dispatch_user_rejected,
    )

    if not was_active and updated.is_active:
        background_tasks.add_task(dispatch_user_approved, user_id=updated.id)
    elif not old_rejection and updated.rejection_reason:
        background_tasks.add_task(
            dispatch_user_rejected, user_id=updated.id, reason=updated.rejection_reason
        )

    return updated


@router.get("/me/export")
async def export_user_data(
    session: DBDep,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Export all personal data for the current user (GDPR Art. 20)."""
    user_id = current_user.id

    # Bookings
    bookings_result = await session.execute(
        select(Booking).where(col(Booking.user_id) == user_id)
    )
    bookings = [
        {
            "id": str(b.id),
            "status": b.status,
            "notes": b.notes,
            "cancellation_reason": b.cancellation_reason,
            "cancelled_slot_title": b.cancelled_slot_title,
            "cancelled_slot_date": str(b.cancelled_slot_date)
            if b.cancelled_slot_date
            else None,
            "cancelled_event_name": b.cancelled_event_name,
            "created_at": b.created_at.isoformat(),
        }
        for b in bookings_result.scalars().all()
    ]

    # Notification preferences
    subs_result = await session.execute(
        select(NotificationSubscription).where(
            col(NotificationSubscription.user_id) == user_id
        )
    )
    notification_preferences = [
        {
            "scope_type": s.scope_type,
            "email_enabled": s.email_enabled,
            "push_enabled": s.push_enabled,
            "telegram_enabled": s.telegram_enabled,
            "is_muted": s.is_muted,
        }
        for s in subs_result.scalars().all()
    ]

    # Availability
    avail_result = await session.execute(
        select(UserAvailability).where(col(UserAvailability.user_id) == user_id)
    )
    availabilities: list[dict[str, Any]] = []
    for a in avail_result.scalars().all():
        dates_result = await session.execute(
            select(UserAvailabilityDate).where(
                col(UserAvailabilityDate.availability_id) == a.id
            )
        )
        availabilities.append(
            {
                "availability_type": a.availability_type,
                "notes": a.notes,
                "dates": [
                    {
                        "date": str(d.slot_date),
                        "start_time": str(d.start_time) if d.start_time else None,
                        "end_time": str(d.end_time) if d.end_time else None,
                    }
                    for d in dates_result.scalars().all()
                ],
            }
        )

    return {
        "profile": {
            "name": current_user.name,
            "email": current_user.email,
            "picture": current_user.picture,
            "preferred_language": current_user.preferred_language,
            "email_verified": current_user.email_verified,
            "roles": current_user.roles,
            "is_active": current_user.is_active,
            "created_at": current_user.created_at.isoformat(),
        },
        "bookings": bookings,
        "notification_preferences": notification_preferences,
        "availabilities": availabilities,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_current_user(
    user: AnyUser,
    session: DBDep,
) -> None:
    """Delete the currently authenticated user's account.

    Does NOT require is_active so that pending users can revoke
    their approval request before being activated.

    This will:
    1. Delete the user from Auth0
    2. Delete the user record and cascaded data from the database
    """
    # Delete user from Auth0 first — if this fails, we abort to keep things consistent
    if not settings.TESTING:
        auth0_deleted = await delete_auth0_user(user.auth0_sub)
        if not auth0_deleted:
            raise HTTPException(
                status_code=500,
                detail="Failed to delete account from authentication provider",
            )

    await session.delete(user)
    await session.commit()

    logger.info("User account deleted: %s", user.auth0_sub)


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
