import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.api.deps import (
    AnyUser,
    CurrentSuperuser,
    CurrentUser,
    DBDep,
)
from app.core.errors import raise_problem
from app.crud.event import event as crud_event
from app.crud.event_membership import event_membership as crud_membership
from app.crud.task import task as crud_task
from app.crud.user import user as crud_user
from app.logic.auth.service import build_user_profile
from app.models.booking import Booking
from app.models.notification import NotificationSubscription
from app.models.user import User
from app.models.user_availability import UserAvailability, UserAvailabilityDate
from app.schemas.user import (
    OwnershipTransferRequest,
    OwnershipTransferResult,
    RejectRegistrationRequest,
    UserCounts,
    UserCreate,
    UserListResponse,
    UserOwnedContent,
    UserRead,
    UserUpdate,
)
from app.schemas.users import (
    SelectedEventUpdate,
    UserProfile,
    UserProfileUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    user: AnyUser,
    *,
    session: DBDep,
) -> UserProfile:
    """Return the signed-in account's own profile.

    A plain read. This used to be a ``POST`` that accepted the identity
    provider's ID token in the body and lazily wrote ``name``, ``email`` and
    ``email_verified`` onto the row, because first login was the only moment
    those values were known. Registration now supplies them directly, and the
    superadmin bootstrap that was duplicated here lives in
    ``app.logic.auth.service.sync_superadmin_role`` — so nothing is left to
    upsert and the verb finally matches what the endpoint does.

    Deliberately ``AnyUser`` rather than ``CurrentUser``: a suspended account
    must still be able to load its own profile, since that response is how the
    UI knows to explain why everything else is refused.
    """
    return await build_user_profile(session, user)


@router.patch("/me", response_model=UserProfile)
async def update_user_profile(
    user_update: UserProfileUpdate,
    current_user: CurrentUser,
    *,
    session: DBDep,
) -> UserProfile:
    """Update the signed-in account's own profile.

    Every field below is a column on ``users``. That is new: ``name``,
    ``nickname`` and ``bio`` used to live in the identity provider, so this
    endpoint made a Management API call and then patched those three values
    back into its own response with ``model_copy``, because no local column
    held them. The response looked right and the next profile load lost the
    edit. All three now persist like everything else.

    ``None`` means "not supplied", not "clear it" — a field left out of the
    body keeps its current value. Setting a nullable column back to NULL is
    therefore not expressible here, which is the same contract this endpoint
    has always had; an empty string is the closest a caller can get.

    Avatar changes go through the dedicated /users/me/avatar endpoints.
    """
    updates: dict[str, object] = {
        "name": user_update.name,
        "nickname": user_update.nickname,
        "bio": user_update.bio,
        "phone_number": user_update.phone_number,
        "preferred_language": user_update.preferred_language,
        "time_format": user_update.time_format,
        "theme": user_update.theme,
        "show_event_switcher_in_nav": user_update.show_event_switcher_in_nav,
    }
    for field, value in updates.items():
        if value is not None:
            setattr(current_user, field, value)

    session.add(current_user)
    await session.flush()

    return await build_user_profile(session, current_user)


@router.put("/me/selected-event", response_model=UserProfile)
async def update_selected_event(
    body: SelectedEventUpdate,
    current_user: CurrentUser,
    *,
    session: DBDep,
) -> UserProfile:
    """Set or clear the event that scopes this user's dashboard."""
    if body.selected_event_id is not None:
        event = await crud_event.get(
            session, body.selected_event_id, raise_404_error=True
        )
        # The membership test below lets ``is_admin`` straight through, which
        # would let the superadmin adopt a stranger's demo as their dashboard
        # scope. A sandbox belongs to its guest alone, so it is refused here —
        # and with 404 rather than 403, matching ``require_event_visible``,
        # because whether someone else's demo exists is not a fact this
        # endpoint should confirm.
        if event.is_sandbox and event.created_by_id != current_user.id:
            raise_problem(404, code="event.not_found", detail="Event not found")
        # You can only work inside an event you belong to.
        if not current_user.is_admin and not await crud_membership.get(
            session, user_id=current_user.id, event_id=event.id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of that event",
            )

    current_user.selected_event_id = body.selected_event_id
    session.add(current_user)
    await session.flush()
    await session.refresh(current_user)
    return await build_user_profile(session, current_user)


@router.get("/", response_model=UserListResponse)
async def list_users(
    session: DBDep,
    _: CurrentSuperuser,
    q: str | None = None,
    status_filter: Literal["all", "active", "pending", "rejected", "suspended"] = "all",
    skip: int = 0,
    limit: int = 20,
) -> UserListResponse:
    items, counts = await crud_user.search(
        session, q=q, status=status_filter, skip=skip, limit=limit
    )
    return UserListResponse(
        items=[UserRead.model_validate(u) for u in items],
        skip=skip,
        limit=limit,
        counts=UserCounts(**counts),
    )


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

    # Suspension controls. With open signup, is_active is a moderation switch
    # rather than an approval gate — flipping it back on is a reinstatement.
    from app.logic.notifications.triggers import (
        dispatch_user_reinstated,
        dispatch_user_suspended,
    )

    if not was_active and updated.is_active:
        background_tasks.add_task(dispatch_user_reinstated, user_id=updated.id)
    elif not old_rejection and updated.rejection_reason:
        background_tasks.add_task(
            dispatch_user_suspended,
            user_id=updated.id,
            reason=updated.rejection_reason,
        )

    return updated


@router.post("/{user_id}/approve", response_model=UserRead)
async def approve_user(
    user_id: uuid.UUID,
    session: DBDep,
    _: CurrentSuperuser,
    background_tasks: BackgroundTasks,
) -> User:
    """Let a registration out of the approval queue.

    Also the way back for a rejected one: a superadmin who changes their mind
    approves it like any other. Approving an account that is already approved
    does nothing and sends nothing.
    """
    from app.logic.notifications.triggers import dispatch_user_approved

    user = await crud_user.get(session, id=user_id, raise_404_error=True)
    if user.approval_status == "approved":
        return user
    user.approval_status = "approved"
    user.rejection_reason = None
    session.add(user)
    # Flushed, not committed: ``get_db`` commits before the response goes out,
    # and the notification task scheduled below runs after that.
    await session.flush()
    await session.refresh(user)
    background_tasks.add_task(dispatch_user_approved, user_id=user.id)
    return user


@router.post("/{user_id}/reject", response_model=UserRead)
async def reject_user(
    user_id: uuid.UUID,
    body: RejectRegistrationRequest,
    session: DBDep,
    _: CurrentSuperuser,
    background_tasks: BackgroundTasks,
) -> User:
    """Turn a registration away, optionally saying why.

    The account is kept rather than deleted, so its owner can sign in and read
    the reason, and delete the account themselves if they want it gone. Only an
    account still in the queue can be rejected: an approved one is suspended
    instead, which is a different decision with its own message.
    """
    from app.logic.notifications.triggers import dispatch_user_rejected

    user = await crud_user.get(session, id=user_id, raise_404_error=True)
    if user.approval_status != "pending":
        raise_problem(
            status.HTTP_409_CONFLICT,
            code="user.not_pending",
            detail="Only a registration that is waiting for approval can be rejected.",
        )
    reason = (body.reason or "").strip() or None
    user.approval_status = "rejected"
    user.rejection_reason = reason
    session.add(user)
    # Flushed, not committed: ``get_db`` commits before the response goes out,
    # and the notification task scheduled below runs after that.
    await session.flush()
    await session.refresh(user)
    background_tasks.add_task(dispatch_user_rejected, user_id=user.id, reason=reason)
    return user


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
            "cancelled_shift_title": b.cancelled_shift_title,
            "cancelled_shift_date": str(b.cancelled_shift_date)
            if b.cancelled_shift_date
            else None,
            "cancelled_task_name": b.cancelled_task_name,
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

    Does NOT require is_active, so a suspended account can still erase itself.

    Deleting the row is now the whole operation. It used to have to succeed
    against the identity provider first, and that call was skipped under
    ``settings.TESTING`` — which is why the E2E suite never exercised the path
    that mattered in production. Nothing outside this database holds the
    account any more.

    ``auth_sessions`` and ``user_tokens`` both carry ``ondelete="CASCADE"`` on
    their user FK, so every credential that could reach this account goes in
    the same statement. The browser keeps its refresh cookie, but the row it
    names no longer exists, so the next renewal 401s and the client returns to
    the sign-in screen.
    """
    await session.delete(user)
    await session.commit()

    logger.info("User account deleted: %s", user.id)


async def _get_valid_transfer_target(
    session: AsyncSession,
    *,
    source_user_id: uuid.UUID,
    target_user_id: uuid.UUID,
) -> User:
    """Validate that ``target_user_id`` may take over ownership from the source."""
    if source_user_id == target_user_id:
        raise_problem(
            400,
            code="user.transfer_same_user",
            detail="Ownership cannot be transferred to the same user",
        )
    target = await crud_user.get(session, id=target_user_id)
    if not target:
        raise_problem(
            404,
            code="user.transfer_target_not_found",
            detail="Transfer target user not found",
        )
    if not target.is_active:
        raise_problem(
            400,
            code="user.transfer_target_inactive",
            detail="Transfer target user is not active",
        )
    return target


@router.get("/{user_id}/owned-content", response_model=UserOwnedContent)
async def get_user_owned_content(
    user_id: uuid.UUID,
    session: DBDep,
    _: CurrentSuperuser,
) -> UserOwnedContent:
    """Admin-only: counts of events and tasks created by this user.

    Used before deleting a user to decide whether ownership must be
    transferred first.
    """
    await crud_user.get(session, id=user_id, raise_404_error=True)
    owned_events = await crud_event.count_owned_by(session, user_id=user_id)
    owned_tasks = await crud_task.count_owned_by(session, user_id=user_id)
    return UserOwnedContent(
        events=owned_events,
        tasks=owned_tasks,
        total=owned_events + owned_tasks,
    )


@router.post("/{user_id}/transfer-ownership", response_model=OwnershipTransferResult)
async def transfer_user_ownership(
    user_id: uuid.UUID,
    body: OwnershipTransferRequest,
    session: DBDep,
    _: CurrentSuperuser,
) -> OwnershipTransferResult:
    """Admin-only: reassign all events and tasks created by one user to another.

    The target user must exist, be active, and differ from the source user.
    """
    await crud_user.get(session, id=user_id, raise_404_error=True)
    await _get_valid_transfer_target(
        session, source_user_id=user_id, target_user_id=body.target_user_id
    )
    events_transferred = await crud_event.reassign_owner(
        session, from_user_id=user_id, to_user_id=body.target_user_id
    )
    tasks_transferred = await crud_task.reassign_owner(
        session, from_user_id=user_id, to_user_id=body.target_user_id
    )
    logger.info(
        "Transferred ownership from user %s to user %s (%d events, %d tasks)",
        user_id,
        body.target_user_id,
        events_transferred,
        tasks_transferred,
    )
    return OwnershipTransferResult(
        events_transferred=events_transferred,
        tasks_transferred=tasks_transferred,
    )


@router.delete("/{user_id}", response_model=UserRead)
async def delete_user(
    user_id: uuid.UUID,
    session: DBDep,
    _: CurrentSuperuser,
    transfer_to_user_id: uuid.UUID | None = None,
) -> User:
    """Admin-only: delete a user by ID from the database.

    If the user still owns events or tasks, deletion is refused with a 409
    (code ``user.owns_content``) unless ``transfer_to_user_id`` is provided.
    When a transfer target is given, all owned events and tasks are reassigned
    to that user in the same transaction before the account is deleted.
    """
    user = await crud_user.get(session, id=user_id, raise_404_error=True)

    owned_events = await crud_event.count_owned_by(session, user_id=user_id)
    owned_tasks = await crud_task.count_owned_by(session, user_id=user_id)
    if owned_events or owned_tasks:
        if transfer_to_user_id is None:
            raise_problem(
                409,
                code="user.owns_content",
                detail=(
                    f"User still owns {owned_events} event(s) and "
                    f"{owned_tasks} task(s). Provide transfer_to_user_id to "
                    "reassign them before deletion."
                ),
            )
        await _get_valid_transfer_target(
            session, source_user_id=user_id, target_user_id=transfer_to_user_id
        )
        await crud_event.reassign_owner(
            session, from_user_id=user_id, to_user_id=transfer_to_user_id
        )
        await crud_task.reassign_owner(
            session, from_user_id=user_id, to_user_id=transfer_to_user_id
        )
        logger.info(
            "Reassigned %d event(s) and %d task(s) from user %s to user %s "
            "before deletion",
            owned_events,
            owned_tasks,
            user_id,
            transfer_to_user_id,
        )

    await session.delete(user)
    await session.commit()
    return user
