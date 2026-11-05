"""Tell an event's organisers when a shift is about to start with places open.

Runs from the reminder poller (``reminder_poller``) every few minutes, so nothing
has to schedule it. Each shift is judged on the wall clock of its own event, and
the alert goes to that event's owners and admins: they are the ones who can still
find somebody, and it's not the platform admins' business.
"""

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.db import async_session
from app.core.logger import get_logger
from app.crud.event_membership import event_membership as crud_membership
from app.crud.shift import on_own_clock, shift_zone, wall_clocks
from app.logic import clock
from app.logic.notifications.messages import get_message
from app.logic.notifications.service import NotificationService
from app.models.booking import Booking
from app.models.event import Event
from app.models.notification import Notification
from app.models.shift import Shift
from app.models.task import Task

logger = get_logger(__name__)

TYPE_CODE = "shift.starting_soon_unfilled"
LOOKAHEAD_MINUTES = 30
#: A shift already alerted about within this long is left alone. Longer than the
#: lookahead, so one shift gets one alert however often the check runs.
REPEAT_AFTER = dt.timedelta(hours=1)


async def _already_alerted(db: AsyncSession, shift: Shift) -> bool:
    result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(
            col(Notification.notification_type_code) == TYPE_CODE,
            Notification.data["slot_id"].astext == str(shift.id),  # type: ignore[union-attr]
            col(Notification.created_at) >= clock.utc_now() - REPEAT_AFTER,
        )
    )
    return result.scalar_one() > 0


async def _alert(
    db: AsyncSession, shift: Shift, event_id: uuid.UUID, confirmed: int
) -> bool:
    """Tell the event's organisers about this shift. False if it has none."""
    organisers = await crud_membership.list_user_ids(
        db, event_id=event_id, minimum_role="admin"
    )
    if not organisers:
        return False
    await NotificationService(db).notify(
        recipient_ids=organisers,
        type_code=TYPE_CODE,
        message_factory=lambda lang: get_message(
            TYPE_CODE,
            lang,
            slot_title=shift.title,
            minutes=str(LOOKAHEAD_MINUTES),
            confirmed=str(confirmed),
            max_bookings=str(shift.max_bookings),
        ),
        data={
            "slot_id": str(shift.id),
            "task_id": str(shift.task_id),
            "open_spots": shift.max_bookings - confirmed,
            "confirmed": confirmed,
            "max_bookings": shift.max_bookings,
        },
        scope_chain=[
            ("shift", shift.id),
            ("task", shift.task_id),
            ("event", event_id),
        ],
    )
    return True


async def check_upcoming_shifts() -> int:
    """Alert about published shifts starting within ``LOOKAHEAD_MINUTES`` that
    aren't fully booked. Returns how many shifts were alerted about.

    A draft is the organisers' workbench and a demo nobody's real problem, and a
    task without an event has no organisers to tell.
    """
    lookahead = dt.timedelta(minutes=LOOKAHEAD_MINUTES)
    starts = col(Shift.date) + col(Shift.start_time)

    async with async_session() as db:
        result = await db.execute(
            select(Shift, col(Event.id))
            .join(Task, col(Task.id) == col(Shift.task_id))
            .join(Event, col(Event.id) == col(Task.event_id))
            .where(
                on_own_clock(
                    await wall_clocks(db),
                    shift_zone(),
                    lambda now: starts.between(now, now + lookahead),
                ),
                col(Task.status) == "published",
                col(Event.status) == "published",
                col(Event.is_sandbox).is_(False),
            )
        )

        sent = 0
        for shift, event_id in result.all():
            count = await db.execute(
                select(func.count())
                .select_from(Booking)
                .where(
                    col(Booking.shift_id) == shift.id,
                    col(Booking.status) == "confirmed",
                )
            )
            confirmed = count.scalar_one()
            if confirmed >= shift.max_bookings or await _already_alerted(db, shift):
                continue
            if await _alert(db, shift, event_id, confirmed):
                sent += 1

        await db.commit()

    if sent:
        logger.info(f"Alerted organisers about {sent} unfilled shift(s)")
    return sent
