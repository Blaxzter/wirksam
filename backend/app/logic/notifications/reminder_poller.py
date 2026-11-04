"""Background poller that dispatches due booking reminders.

It also runs the check for shifts about to start with places open
(``unfilled_shifts``), for the same one worker.

Runs as an asyncio task started during the FastAPI lifespan.
Uses a PostgreSQL advisory lock so only one worker in a multi-process
deployment runs the poller.
"""

import asyncio

from sqlalchemy import text

from app.core.db import async_session
from app.core.logger import get_logger
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.crud.event import event as crud_event
from app.logic.notifications.messages import (
    format_time_until,
    get_message,
    shift_times,
)
from app.logic.notifications.service import NotificationService
from app.logic.notifications.unfilled_shifts import check_upcoming_shifts
from app.models.booking_reminder import BookingReminder
from app.models.shift import Shift

logger = get_logger(__name__)

# Advisory lock key — arbitrary 64-bit int, unique to this poller
_ADVISORY_LOCK_KEY = 7_483_920_156

# Poll interval in seconds
_POLL_INTERVAL = 30

# Run cleanup every N poll cycles (~50 min at 30s interval)
_CLEANUP_EVERY_N_CYCLES = 100

# Look for shifts about to start with places open every N poll cycles (~5 min)
_UNFILLED_EVERY_N_CYCLES = 10


async def _process_reminder(reminder: BookingReminder) -> None:
    """Dispatch a single reminder through the notification service."""
    async with async_session() as db:
        try:
            # Load the shift for context
            from sqlalchemy import select
            from sqlmodel import col

            slot_query = select(Shift).where(col(Shift.id) == reminder.shift_id)
            result = await db.execute(slot_query)
            shift = result.scalar_one_or_none()

            if not shift:
                # Shift was deleted; mark reminder as expired
                await crud_reminder.mark_sent(db, reminder_id=reminder.id)
                await db.commit()
                return

            # Load task name
            from app.models.task import Task

            task_query = select(Task).where(col(Task.id) == shift.task_id)
            task_result = await db.execute(task_query)
            task = task_result.scalar_one_or_none()
            event_id = task.event_id if task else None
            zone = await crud_event.zone_of(db, event_id)

            svc = NotificationService(db)

            # Build scope chain for preference resolution
            scope_chain: list[tuple[str, object]] = []
            if shift.id:
                scope_chain.append(("shift", shift.id))
            if shift.task_id:
                scope_chain.append(("task", shift.task_id))
            if event_id:
                scope_chain.append(("event", event_id))

            def _factory(lang: str) -> tuple[str, str]:
                return get_message(
                    "booking.reminder",
                    lang,
                    slot_title=shift.title,
                    time_until=format_time_until(reminder.offset_minutes, lang),
                    date=shift.date.strftime("%d.%m.%Y") if shift.date else "",
                    **shift_times(shift.start_time, shift.end_time, zone),
                    location=shift.location or "",
                )

            await svc.notify(
                recipient_ids=[reminder.user_id],
                type_code="booking.reminder",
                message_factory=_factory,
                data={
                    "booking_id": str(reminder.booking_id),
                    "slot_id": str(shift.id),
                    "task_id": str(shift.task_id),
                },
                scope_chain=scope_chain,  # type: ignore[arg-type]
                force_channels=reminder.channels,
            )

            # Mark as sent
            await crud_reminder.mark_sent(db, reminder_id=reminder.id)
            await db.commit()

        except Exception:
            logger.exception(
                f"Failed to process reminder {reminder.id} for booking {reminder.booking_id}"
            )
            await db.rollback()


async def _poll_cycle() -> int:
    """Run one poll cycle. Returns number of reminders processed."""
    async with async_session() as db:
        try:
            reminders = await crud_reminder.fetch_due_reminders(db, limit=50)
            if not reminders:
                await db.commit()
                return 0

            # Snapshot IDs and data before committing (releases FOR UPDATE locks)
            reminder_data = [
                BookingReminder(
                    id=r.id,
                    booking_id=r.booking_id,
                    user_id=r.user_id,
                    shift_id=r.shift_id,
                    remind_at=r.remind_at,
                    offset_minutes=r.offset_minutes,
                    status=r.status,
                    channels=r.channels,
                )
                for r in reminders
            ]
            await db.commit()
        except Exception:
            logger.exception("Failed to fetch due reminders")
            await db.rollback()
            return 0

    # Process each reminder in its own session
    for reminder in reminder_data:
        await _process_reminder(reminder)

    return len(reminder_data)


async def _cleanup_cycle() -> None:
    """Expire stale pending reminders and clean up old records."""
    async with async_session() as db:
        try:
            expired = await crud_reminder.expire_past_pending(db)
            deleted = await crud_reminder.cleanup_old(db, days=30)
            await db.commit()
            if expired or deleted:
                logger.info(f"Reminder cleanup: expired={expired}, deleted={deleted}")
        except Exception:
            logger.exception("Failed during reminder cleanup")
            await db.rollback()


async def _unfilled_cycle() -> None:
    """Alert organisers about unfilled shifts; a failure waits for the next turn."""
    try:
        await check_upcoming_shifts()
    except Exception:
        logger.exception("Failed to check for unfilled shifts")


async def run_reminder_poller() -> None:
    """Main poller loop. Acquires advisory lock, then polls forever."""
    # Try to acquire advisory lock (non-blocking)
    async with async_session() as db:
        result = await db.execute(
            text(f"SELECT pg_try_advisory_lock({_ADVISORY_LOCK_KEY})")
        )
        acquired = result.scalar()
        await db.commit()

    if not acquired:
        logger.info("Another worker holds the reminder poller lock; skipping")
        return

    logger.info("Reminder poller started (advisory lock acquired)")
    cycle_count = 0

    try:
        while True:
            try:
                processed = await _poll_cycle()
                if processed:
                    logger.debug(f"Processed {processed} reminders")

                cycle_count += 1
                if cycle_count % _UNFILLED_EVERY_N_CYCLES == 0:
                    await _unfilled_cycle()
                if cycle_count >= _CLEANUP_EVERY_N_CYCLES:
                    await _cleanup_cycle()
                    cycle_count = 0

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error in reminder poller cycle")

            await asyncio.sleep(_POLL_INTERVAL)

    except asyncio.CancelledError:
        logger.info("Reminder poller shutting down")
    finally:
        # Release advisory lock
        async with async_session() as db:
            await db.execute(text(f"SELECT pg_advisory_unlock({_ADVISORY_LOCK_KEY})"))
            await db.commit()
        logger.info("Reminder poller advisory lock released")
