"""Notification trigger helpers called from route handlers via BackgroundTasks.

Each function opens its own DB session since BackgroundTasks run after
the request session is closed.
"""

import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session
from app.core.logger import get_logger
from app.logic.notifications.messages import get_message
from app.logic.notifications.service import NotificationService

logger = get_logger(__name__)


async def dispatch_booking_confirmed(
    *,
    booking_id: uuid.UUID,
    user_id: uuid.UUID,
    slot_title: str,
    slot_date: dt.date | None = None,
    slot_start_time: dt.time | None = None,
    slot_end_time: dt.time | None = None,
    slot_location: str | None = None,
    task_name: str | None = None,
    slot_id: uuid.UUID,
    task_id: uuid.UUID,
    event_id: uuid.UUID | None = None,
) -> None:
    """Notify user that their booking was confirmed."""
    try:
        async with async_session() as db:
            svc = NotificationService(db)
            scope_chain = _build_scope_chain(slot_id, task_id, event_id)

            def _factory(lang: str) -> tuple[str, str]:
                return get_message(
                    "booking.confirmed",
                    lang,
                    slot_title=slot_title,
                    task_name=task_name or "",
                    date=slot_date.strftime("%d.%m.%Y") if slot_date else "",
                    start_time=slot_start_time.strftime("%H:%M")
                    if slot_start_time
                    else "",
                    end_time=slot_end_time.strftime("%H:%M") if slot_end_time else "",
                    location=slot_location or "",
                )

            await svc.notify(
                recipient_ids=[user_id],
                type_code="booking.confirmed",
                message_factory=_factory,
                data={
                    "booking_id": str(booking_id),
                    "slot_id": str(slot_id),
                    "task_id": str(task_id),
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
    task_id: uuid.UUID,
    event_id: uuid.UUID | None = None,
    new_user_name: str | None,
    existing_user_ids: list[uuid.UUID],
) -> None:
    """Notify existing bookers that someone else also booked their shift."""
    if not existing_user_ids:
        return
    try:
        async with async_session() as db:
            svc = NotificationService(db)
            scope_chain = _build_scope_chain(slot_id, task_id, event_id)
            name = new_user_name or "Someone"
            await svc.notify(
                recipient_ids=existing_user_ids,
                type_code="booking.shift_cobooked",
                message_factory=lambda lang, _name=name: get_message(
                    "booking.shift_cobooked", lang, name=_name, slot_title=slot_title
                ),
                data={
                    "slot_id": str(slot_id),
                    "task_id": str(task_id),
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
    task_id: uuid.UUID,
    event_id: uuid.UUID | None = None,
) -> None:
    """Notify user that their booking cancellation was processed."""
    try:
        async with async_session() as db:
            svc = NotificationService(db)
            scope_chain = _build_scope_chain(slot_id, task_id, event_id)
            await svc.notify(
                recipient_ids=[user_id],
                type_code="booking.cancelled_by_user",
                message_factory=lambda lang: get_message(
                    "booking.cancelled_by_user", lang, slot_title=slot_title
                ),
                data={
                    "booking_id": str(booking_id),
                    "slot_id": str(slot_id),
                    "task_id": str(task_id),
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
    task_name: str | None = None,
    task_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> None:
    """Notify users that their bookings were cancelled by admin action."""
    if not user_ids:
        return
    try:
        async with async_session() as db:
            svc = NotificationService(db)

            def _factory(lang: str) -> tuple[str, str]:
                if lang == "de":
                    task_label = f' für das Task „{task_name}"' if task_name else ""
                    detail = f" (Grund: {reason})" if reason else ""
                else:
                    task_label = f' for task "{task_name}"' if task_name else ""
                    detail = f" (Reason: {reason})" if reason else ""
                return get_message(
                    "booking.cancelled_by_admin",
                    lang,
                    slot_title=slot_title,
                    task_label=task_label,
                    detail=detail,
                )

            await svc.notify(
                recipient_ids=user_ids,
                type_code="booking.cancelled_by_admin",
                message_factory=_factory,
                data={
                    "task_id": str(task_id) if task_id else None,
                    "event_id": str(event_id) if event_id else None,
                },
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch booking.cancelled_by_admin notification")


async def dispatch_shift_time_changed(
    *,
    slot_id: uuid.UUID,
    slot_title: str,
    task_id: uuid.UUID,
    event_id: uuid.UUID | None = None,
    booked_user_ids: list[uuid.UUID],
) -> None:
    """Notify bookers that a shift's time was changed."""
    if not booked_user_ids:
        return
    try:
        async with async_session() as db:
            svc = NotificationService(db)
            scope_chain = _build_scope_chain(slot_id, task_id, event_id)
            await svc.notify(
                recipient_ids=booked_user_ids,
                type_code="shift.time_changed",
                message_factory=lambda lang: get_message(
                    "shift.time_changed", lang, slot_title=slot_title
                ),
                data={
                    "slot_id": str(slot_id),
                    "task_id": str(task_id),
                },
                scope_chain=scope_chain,
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch shift.time_changed notification")


async def dispatch_task_published(
    *,
    task_id: uuid.UUID,
    task_name: str,
    event_id: uuid.UUID | None = None,
    is_sandbox: bool = False,
) -> None:
    """Notify all active users that a task was published.

    ``is_sandbox`` is a hard stop rather than a filter on the recipient list.
    This fans out to *every active account on the installation*, and a demo
    guest flipping a seeded task from draft to published - which the manager
    tour walks them through - would otherwise put the name of their throwaway
    task in front of the entire user base.
    """
    if is_sandbox:
        return
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
                scope_chain: list[tuple[str, uuid.UUID]] = [("task", task_id)]
                if event_id:
                    scope_chain.append(("event", event_id))
                await svc.notify(
                    recipient_ids=user_ids,
                    type_code="task.published",
                    message_factory=lambda lang: get_message(
                        "task.published", lang, task_name=task_name
                    ),
                    data={"task_id": str(task_id)},
                    scope_chain=scope_chain,
                )
                await db.commit()
    except Exception:
        logger.exception("Failed to dispatch task.published notification")


async def dispatch_event_published(
    *,
    event_id: uuid.UUID,
    event_name: str,
) -> None:
    """Notify the event's members that it was published.

    Deliberately not everyone on the platform: with open signup and private
    events, a global announcement would leak event names to strangers and
    spam accounts that have nothing to do with it.
    """
    try:
        from app.crud.event_membership import event_membership as crud_membership

        async with async_session() as db:
            user_ids = await crud_membership.list_user_ids(db, event_id=event_id)

            if user_ids:
                svc = NotificationService(db)
                await svc.notify(
                    recipient_ids=user_ids,
                    type_code="event.published",
                    message_factory=lambda lang: get_message(
                        "event.published",
                        lang,
                        event_name=event_name,
                    ),
                    data={"event_id": str(event_id)},
                    scope_chain=[("event", event_id)],
                )
                await db.commit()
    except Exception:
        logger.exception("Failed to dispatch event.published notification")


async def dispatch_event_cloned(
    *,
    event_id: uuid.UUID,
    note: str | None = None,
    exclude_user_id: uuid.UUID | None = None,
) -> None:
    """Tell the new event's members it was set up from an existing one.

    Scoped to the clone's own roster for the same reason
    ``dispatch_event_published`` is: a platform-wide announcement would leak
    event names to strangers.

    ``exclude_user_id`` is whoever pressed clone: they are the clone's owner
    and therefore on its roster, and mailing someone the announcement they just
    wrote is noise. Suspended accounts are filtered out the way
    ``dispatch_task_published`` does — they cannot open the event they would be
    invited into.
    """
    try:
        from sqlalchemy import select
        from sqlmodel import col

        from app.crud.event_membership import event_membership as crud_membership
        from app.models.user import User

        async with async_session() as db:
            member_ids = await crud_membership.list_user_ids(db, event_id=event_id)
            member_ids = [uid for uid in member_ids if uid != exclude_user_id]
            if not member_ids:
                return

            active = await db.execute(
                select(col(User.id)).where(
                    col(User.id).in_(member_ids),
                    col(User.is_active) == True,  # noqa: E712
                )
            )
            user_ids = list(active.scalars().all())
            if not user_ids:
                return

            event_name = await _event_name(db, event_id)
            clean_note = (note or "").strip()

            def _factory(lang: str) -> tuple[str, str]:
                # The note block is its own locale entry so its label travels
                # with the wording it prefixes, the way ``role.*`` does for
                # ``event.role_changed``. The note itself stays a format
                # *value*, never part of the format string: an admin typing a
                # stray brace must not be able to break — or steer — either
                # template.
                note_block = (
                    get_message("event.cloned.note", lang, note=clean_note)[1]
                    if clean_note
                    else ""
                )
                return get_message(
                    "event.cloned",
                    lang,
                    event_name=event_name,
                    note=note_block,
                )

            svc = NotificationService(db)
            await svc.notify(
                recipient_ids=user_ids,
                type_code="event.cloned",
                message_factory=_factory,
                data={"event_id": str(event_id)},
                scope_chain=[("event", event_id)],
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch event.cloned notification")


async def dispatch_user_reinstated(
    *,
    user_id: uuid.UUID,
) -> None:
    """Notify a user that their suspended account was restored."""
    try:
        async with async_session() as db:
            svc = NotificationService(db)
            await svc.notify(
                recipient_ids=[user_id],
                type_code="user.reinstated",
                message_factory=lambda lang: get_message("user.reinstated", lang),
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch user.reinstated notification")


async def dispatch_user_suspended(
    *,
    user_id: uuid.UUID,
    reason: str | None = None,
) -> None:
    """Notify a user that their account was suspended."""
    try:
        async with async_session() as db:
            svc = NotificationService(db)

            def _factory(lang: str) -> tuple[str, str]:
                if lang == "de":
                    detail = f" Grund: {reason}" if reason else ""
                else:
                    detail = f" Reason: {reason}" if reason else ""
                return get_message("user.suspended", lang, detail=detail)

            await svc.notify(
                recipient_ids=[user_id],
                type_code="user.suspended",
                message_factory=_factory,
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch user.suspended notification")


# ── Event membership ──────────────────────────────────────────────


async def _event_name(db: AsyncSession, event_id: uuid.UUID) -> str:
    from app.crud.event import event as crud_event

    db_event = await crud_event.get(db, event_id)
    return db_event.name if db_event else "an event"


async def dispatch_event_invitation(
    *,
    invitation_id: uuid.UUID,
) -> None:
    """Tell an invitee they have been invited to an event.

    Only fires for people who already have an account — an invitation to an
    address with no user behind it is picked up at first sign-in instead.
    """
    try:
        from app.crud.event_invitation import event_invitation as crud_invitation
        from app.crud.user import user as crud_user

        async with async_session() as db:
            invitation = await crud_invitation.get(db, invitation_id=invitation_id)
            if not invitation or not invitation.email:
                return
            invitee = await crud_user.get_by_email(db, email=invitation.email)
            if not invitee:
                return

            name = await _event_name(db, invitation.event_id)
            svc = NotificationService(db)
            await svc.notify(
                recipient_ids=[invitee.id],
                type_code="event.invitation",
                message_factory=lambda lang: get_message(
                    "event.invitation", lang, event_name=name
                ),
                data={
                    "event_id": str(invitation.event_id),
                    "token": invitation.token,
                },
                scope_chain=[("event", invitation.event_id)],
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch event.invitation notification")


async def dispatch_event_invitation_accepted(
    *,
    event_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Tell the event's admins that an invitee joined."""
    try:
        from app.crud.event_membership import event_membership as crud_membership
        from app.crud.user import user as crud_user

        async with async_session() as db:
            admins = await crud_membership.list_user_ids(
                db, event_id=event_id, minimum_role="admin"
            )
            recipients = [a for a in admins if a != user_id]
            if not recipients:
                return

            joiner = await crud_user.get(db, id=user_id)
            joiner_name = (
                (joiner.name or joiner.email or "Someone") if joiner else "Someone"
            )
            name = await _event_name(db, event_id)

            svc = NotificationService(db)
            await svc.notify(
                recipient_ids=recipients,
                type_code="event.invitation_accepted",
                message_factory=lambda lang: get_message(
                    "event.invitation_accepted",
                    lang,
                    name=joiner_name,
                    event_name=name,
                ),
                data={"event_id": str(event_id), "user_id": str(user_id)},
                scope_chain=[("event", event_id)],
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch event.invitation_accepted notification")


async def dispatch_event_join_requested(
    *,
    event_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Tell the event's admins that someone asked to join."""
    try:
        from app.crud.event_membership import event_membership as crud_membership
        from app.crud.user import user as crud_user

        async with async_session() as db:
            recipients = await crud_membership.list_user_ids(
                db, event_id=event_id, minimum_role="admin"
            )
            if not recipients:
                return

            applicant = await crud_user.get(db, id=user_id)
            applicant_name = (
                (applicant.name or applicant.email or "Someone")
                if applicant
                else "Someone"
            )
            name = await _event_name(db, event_id)

            svc = NotificationService(db)
            await svc.notify(
                recipient_ids=recipients,
                type_code="event.join_requested",
                message_factory=lambda lang: get_message(
                    "event.join_requested",
                    lang,
                    name=applicant_name,
                    event_name=name,
                ),
                data={"event_id": str(event_id), "user_id": str(user_id)},
                scope_chain=[("event", event_id)],
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch event.join_requested notification")


async def dispatch_event_join_decided(
    *,
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    approved: bool,
) -> None:
    """Tell an applicant whether they were let in."""
    type_code = "event.join_approved" if approved else "event.join_declined"
    try:
        async with async_session() as db:
            name = await _event_name(db, event_id)
            svc = NotificationService(db)
            await svc.notify(
                recipient_ids=[user_id],
                type_code=type_code,
                message_factory=lambda lang: get_message(
                    type_code, lang, event_name=name
                ),
                data={"event_id": str(event_id)},
                scope_chain=[("event", event_id)],
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch %s notification", type_code)


async def dispatch_event_role_changed(
    *,
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
) -> None:
    """Tell a member their role in an event changed."""
    try:
        async with async_session() as db:
            name = await _event_name(db, event_id)
            svc = NotificationService(db)
            await svc.notify(
                recipient_ids=[user_id],
                type_code="event.role_changed",
                message_factory=lambda lang: get_message(
                    "event.role_changed",
                    lang,
                    event_name=name,
                    role=get_message(f"role.{role}", lang)[0],
                ),
                data={"event_id": str(event_id), "role": role},
                scope_chain=[("event", event_id)],
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to dispatch event.role_changed notification")


def _build_scope_chain(
    slot_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
) -> list[tuple[str, uuid.UUID]]:
    """Build a scope chain from most specific to least specific."""
    chain: list[tuple[str, uuid.UUID]] = []
    if slot_id:
        chain.append(("shift", slot_id))
    if task_id:
        chain.append(("task", task_id))
    if event_id:
        chain.append(("event", event_id))
    return chain
