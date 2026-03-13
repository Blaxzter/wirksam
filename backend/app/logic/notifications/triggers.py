"""Notification trigger helpers called from route handlers via BackgroundTasks.

Each function opens its own DB session since BackgroundTasks run after
the request session is closed.
"""

import uuid

from app.core.db import async_session
from app.core.logger import get_logger
from app.logic.notifications.service import NotificationService

logger = get_logger(__name__)


async def dispatch_booking_confirmed(
    *,
    booking_id: uuid.UUID,
    user_id: uuid.UUID,
    slot_title: str,
    slot_id: uuid.UUID,
    event_id: uuid.UUID,
    event_group_id: uuid.UUID | None = None,
) -> None:
    """Notify user that their booking was confirmed."""
    try:
        async with async_session() as db:
            svc = NotificationService(db)
            scope_chain = _build_scope_chain(slot_id, event_id, event_group_id)
            await svc.notify(
                recipient_ids=[user_id],
                type_code="booking.confirmed",
                title="Booking Confirmed",
                body=f'Your booking for "{slot_title}" has been confirmed.',
                data={
                    "booking_id": str(booking_id),
                    "slot_id": str(slot_id),
                    "event_id": str(event_id),
                },
                scope_chain=scope_chain,
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch booking.confirmed notification")


async def dispatch_booking_cobooked(
    *,
    slot_id: uuid.UUID,
    slot_title: str,
    event_id: uuid.UUID,
    event_group_id: uuid.UUID | None = None,
    new_user_name: str | None,
    existing_user_ids: list[uuid.UUID],
) -> None:
    """Notify existing bookers that someone else also booked their slot."""
    if not existing_user_ids:
        return
    try:
        async with async_session() as db:
            svc = NotificationService(db)
            scope_chain = _build_scope_chain(slot_id, event_id, event_group_id)
            name = new_user_name or "Someone"
            await svc.notify(
                recipient_ids=existing_user_ids,
                type_code="booking.slot_cobooked",
                title="New Co-booking",
                body=f'{name} also booked the slot "{slot_title}".',
                data={
                    "slot_id": str(slot_id),
                    "event_id": str(event_id),
                },
                scope_chain=scope_chain,
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch booking.slot_cobooked notification")


async def dispatch_booking_cancelled_by_user(
    *,
    booking_id: uuid.UUID,
    user_id: uuid.UUID,
    slot_title: str,
    slot_id: uuid.UUID,
    event_id: uuid.UUID,
    event_group_id: uuid.UUID | None = None,
) -> None:
    """Notify user that their booking cancellation was processed."""
    try:
        async with async_session() as db:
            svc = NotificationService(db)
            scope_chain = _build_scope_chain(slot_id, event_id, event_group_id)
            await svc.notify(
                recipient_ids=[user_id],
                type_code="booking.cancelled_by_user",
                title="Booking Cancelled",
                body=f'Your booking for "{slot_title}" has been cancelled.',
                data={
                    "booking_id": str(booking_id),
                    "slot_id": str(slot_id),
                    "event_id": str(event_id),
                },
                scope_chain=scope_chain,
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch booking.cancelled_by_user notification")


async def dispatch_booking_cancelled_by_admin(
    *,
    user_ids: list[uuid.UUID],
    slot_title: str,
    event_name: str | None = None,
    event_id: uuid.UUID | None = None,
    event_group_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> None:
    """Notify users that their bookings were cancelled by admin action."""
    if not user_ids:
        return
    try:
        async with async_session() as db:
            svc = NotificationService(db)
            detail = f' (Reason: {reason})' if reason else ""
            event_label = f' for event "{event_name}"' if event_name else ""
            await svc.notify(
                recipient_ids=user_ids,
                type_code="booking.cancelled_by_admin",
                title="Booking Cancelled by Admin",
                body=f'Your booking for "{slot_title}"{event_label} was cancelled by an administrator.{detail}',
                data={
                    "event_id": str(event_id) if event_id else None,
                    "event_group_id": str(event_group_id) if event_group_id else None,
                },
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch booking.cancelled_by_admin notification")


async def dispatch_slot_time_changed(
    *,
    slot_id: uuid.UUID,
    slot_title: str,
    event_id: uuid.UUID,
    event_group_id: uuid.UUID | None = None,
    booked_user_ids: list[uuid.UUID],
) -> None:
    """Notify bookers that a slot's time was changed."""
    if not booked_user_ids:
        return
    try:
        async with async_session() as db:
            svc = NotificationService(db)
            scope_chain = _build_scope_chain(slot_id, event_id, event_group_id)
            await svc.notify(
                recipient_ids=booked_user_ids,
                type_code="slot.time_changed",
                title="Slot Time Changed",
                body=f'The time for slot "{slot_title}" has been updated. Please check the new schedule.',
                data={
                    "slot_id": str(slot_id),
                    "event_id": str(event_id),
                },
                scope_chain=scope_chain,
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch slot.time_changed notification")


async def dispatch_event_published(
    *,
    event_id: uuid.UUID,
    event_name: str,
    event_group_id: uuid.UUID | None = None,
) -> None:
    """Notify all active users that an event was published."""
    try:
        from sqlalchemy import select
        from sqlmodel import col

        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(
                select(User).where(col(User.is_active) == True)  # noqa: E712
            )
            users = result.scalars().all()
            user_ids = [u.id for u in users]

            if user_ids:
                svc = NotificationService(db)
                scope_chain: list[tuple[str, uuid.UUID]] = [("event", event_id)]
                if event_group_id:
                    scope_chain.append(("event_group", event_group_id))
                await svc.notify(
                    recipient_ids=user_ids,
                    type_code="event.published",
                    title="New Event Published",
                    body=f'A new event "{event_name}" has been published. Check it out!',
                    data={"event_id": str(event_id)},
                    scope_chain=scope_chain,
                )
                await db.commit()
    except Exception:
        logger.exception("Failed to dispatch event.published notification")


async def dispatch_event_group_published(
    *,
    event_group_id: uuid.UUID,
    event_group_name: str,
) -> None:
    """Notify all active users that an event group was published."""
    try:
        from sqlalchemy import select
        from sqlmodel import col

        from app.models.user import User

        async with async_session() as db:
            result = await db.execute(
                select(User).where(col(User.is_active) == True)  # noqa: E712
            )
            users = result.scalars().all()
            user_ids = [u.id for u in users]

            if user_ids:
                svc = NotificationService(db)
                await svc.notify(
                    recipient_ids=user_ids,
                    type_code="event_group.published",
                    title="New Event Group Published",
                    body=f'Event group "{event_group_name}" has been published.',
                    data={"event_group_id": str(event_group_id)},
                    scope_chain=[("event_group", event_group_id)],
                )
                await db.commit()
    except Exception:
        logger.exception("Failed to dispatch event_group.published notification")


async def dispatch_user_registered(
    *,
    user_id: uuid.UUID,
    user_name: str | None,
    user_email: str | None,
) -> None:
    """Notify admins that a new user registered."""
    try:
        async with async_session() as db:
            svc = NotificationService(db)
            name = user_name or user_email or "Unknown"
            await svc.notify_admins(
                type_code="user.registered",
                title="New User Registered",
                body=f'A new user "{name}" has registered and is pending approval.',
                data={"user_id": str(user_id)},
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch user.registered notification")


async def dispatch_user_approved(
    *,
    user_id: uuid.UUID,
) -> None:
    """Notify user that their account was approved."""
    try:
        async with async_session() as db:
            svc = NotificationService(db)
            await svc.notify(
                recipient_ids=[user_id],
                type_code="user.approved",
                title="Account Approved",
                body="Your account has been approved! You can now access all features.",
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch user.approved notification")


async def dispatch_user_rejected(
    *,
    user_id: uuid.UUID,
    reason: str | None = None,
) -> None:
    """Notify user that their account was rejected."""
    try:
        async with async_session() as db:
            svc = NotificationService(db)
            detail = f" Reason: {reason}" if reason else ""
            await svc.notify(
                recipient_ids=[user_id],
                type_code="user.rejected",
                title="Account Rejected",
                body=f"Your account request has been rejected.{detail}",
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch user.rejected notification")


def _build_scope_chain(
    slot_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
    event_group_id: uuid.UUID | None = None,
) -> list[tuple[str, uuid.UUID]]:
    """Build a scope chain from most specific to least specific."""
    chain: list[tuple[str, uuid.UUID]] = []
    if slot_id:
        chain.append(("duty_slot", slot_id))
    if event_id:
        chain.append(("event", event_id))
    if event_group_id:
        chain.append(("event_group", event_group_id))
    return chain
