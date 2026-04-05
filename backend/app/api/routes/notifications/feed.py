import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DBDep, QueryTokenUser
from app.core.db import async_session
from app.core.errors import raise_problem
from app.core.sse import sse_manager
from app.crud.notification import notification as crud_notification
from app.schemas.notification import (
    NotificationListResponse,
    NotificationRead,
    UnreadCountResponse,
)

router = APIRouter()

SSE_HEARTBEAT_SECONDS = 30


@router.get("/stream")
async def notification_stream(
    request: Request,
    user: QueryTokenUser,
) -> StreamingResponse:
    """SSE stream that pushes unread-count updates in real time.

    EventSource doesn't support custom headers, so the JWT is passed
    as a query parameter instead (handled by the QueryTokenUser dep).
    """
    user_id = user.id

    # Fetch initial unread count
    async with async_session.begin() as session:
        initial_count = await crud_notification.get_unread_count(
            session, user_id=user_id
        )

    queue = sse_manager.connect(user_id)

    shutdown_event = sse_manager.shutdown_event

    async def event_generator():
        queue_task: asyncio.Task[dict[str, Any]] | None = None
        shutdown_task: asyncio.Task[bool] | None = None
        try:
            # Send initial unread count immediately
            yield _sse_format("unread_count", {"unread_count": initial_count})

            while not shutdown_event.is_set():
                if await request.is_disconnected():
                    break

                try:
                    # Reuse queue_task across heartbeat timeouts
                    if queue_task is None or queue_task.done():
                        queue_task = asyncio.ensure_future(queue.get())
                    if shutdown_task is None or shutdown_task.done():
                        shutdown_task = asyncio.ensure_future(shutdown_event.wait())

                    done, _pending = await asyncio.wait(
                        {queue_task, shutdown_task},
                        timeout=SSE_HEARTBEAT_SECONDS,
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    if shutdown_task in done:
                        break

                    if queue_task in done:
                        message = queue_task.result()
                        yield _sse_format(message["event"], message["data"])
                        queue_task = None  # consumed; create fresh next iteration
                    else:
                        # Timeout — send heartbeat
                        yield ": heartbeat\n\n"
                except asyncio.CancelledError:
                    break
        finally:
            # Cancel and await outstanding tasks to avoid "Task was destroyed
            # but it is pending" warnings.
            for task in (queue_task, shutdown_task):
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
            sse_manager.disconnect(user_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


def _sse_format(event: str, data: dict[str, Any]) -> str:
    """Format a server-sent event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


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
    # Broadcast updated unread count via SSE
    new_count = await crud_notification.get_unread_count(
        session, user_id=current_user.id
    )
    await sse_manager.broadcast(
        current_user.id, "unread_count", {"unread_count": new_count}
    )

    return NotificationRead.model_validate(notif)


@router.post("/mark-all-read", response_model=dict[str, int])
async def mark_all_notifications_read(
    session: DBDep,
    current_user: CurrentUser,
) -> dict[str, int]:
    """Mark all of the current user's notifications as read."""
    count = await crud_notification.mark_all_as_read(session, user_id=current_user.id)

    await sse_manager.broadcast(current_user.id, "unread_count", {"unread_count": 0})

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
