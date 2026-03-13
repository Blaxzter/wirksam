import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.notification import notification as crud_notification
from app.schemas.notification import (
    NotificationListResponse,
    NotificationRead,
    UnreadCountResponse,
)

router = APIRouter()


@router.get("/", response_model=NotificationListResponse)
async def list_notifications(
    session: DBDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    unread_only: bool = Query(default=False),
) -> NotificationListResponse:
    """List the current user's notifications."""
    items = await crud_notification.get_multi_by_recipient(
        session,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        unread_only=unread_only,
    )
    total = await crud_notification.count_by_recipient(
        session, user_id=current_user.id, unread_only=unread_only
    )
    unread_count = await crud_notification.get_unread_count(
        session, user_id=current_user.id
    )
    return NotificationListResponse(
        items=[NotificationRead.model_validate(n) for n in items],
        total=total,
        unread_count=unread_count,
        skip=skip,
        limit=limit,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    session: DBDep,
    current_user: CurrentUser,
) -> UnreadCountResponse:
    """Get the current user's unread notification count (for badge)."""
    count = await crud_notification.get_unread_count(session, user_id=current_user.id)
    return UnreadCountResponse(unread_count=count)


@router.patch("/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_read(
    notification_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> NotificationRead:
    """Mark a single notification as read."""
    notif = await crud_notification.mark_as_read(
        session,
        notification_id=uuid.UUID(notification_id),
        user_id=current_user.id,
    )
    if not notif:
        raise_problem(
            404, code="notification.not_found", detail="Notification not found"
        )
    return NotificationRead.model_validate(notif)


@router.post("/mark-all-read", response_model=dict[str, int])
async def mark_all_notifications_read(
    session: DBDep,
    current_user: CurrentUser,
) -> dict[str, int]:
    """Mark all of the current user's notifications as read."""
    count = await crud_notification.mark_all_as_read(session, user_id=current_user.id)
    return {"marked_count": count}


@router.delete("/{notification_id}", status_code=204)
async def dismiss_notification(
    notification_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Permanently delete a notification."""
    notif = await crud_notification.get(session, notification_id)
    if not notif:
        raise_problem(
            404, code="notification.not_found", detail="Notification not found"
        )

    if notif.recipient_id != current_user.id:
        raise_problem(
            403, code="notification.forbidden", detail="Not your notification"
        )
    await session.delete(notif)
