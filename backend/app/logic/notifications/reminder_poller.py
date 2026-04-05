"""Background poller that dispatches due booking reminders.

Runs as an asyncio task started during the FastAPI lifespan.
Uses a PostgreSQL advisory lock so only one worker in a multi-process
deployment runs the poller.
"""

import asyncio

from sqlalchemy import text

from app.core.db import async_session
from app.core.logger import get_logger
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.logic.notifications.messages import get_message
from app.logic.notifications.service import NotificationService
from app.models.booking_reminder import BookingReminder
from app.models.duty_slot import DutySlot

logger = get_logger(__name__)

# Advisory lock key — arbitrary 64-bit int, unique to this poller
_ADVISORY_LOCK_KEY = 7_483_920_156

# Poll interval in seconds
_POLL_INTERVAL = 30

# Run cleanup every N poll cycles (~50 min at 30s interval)
_CLEANUP_EVERY_N_CYCLES = 100


def _format_time_until(offset_minutes: int, lang: str) -> str:
    """Human-readable time-until string for the reminder body."""
    if offset_minutes < 60:
        if lang == "de":
            return f"in {offset_minutes} Minuten"
        return f"in {offset_minutes} minutes"
    hours = offset_minutes // 60
    remaining_mins = offset_minutes % 60
    if offset_minutes < 1440:
        if lang == "de":
            if remaining_mins:
                return f"in {hours} Std. {remaining_mins} Min."
            return f"in {hours} Stunde{'n' if hours > 1 else ''}"
        if remaining_mins:
            return f"in {hours}h {remaining_mins}min"
        return f"in {hours} hour{'s' if hours > 1 else ''}"
    days = offset_minutes // 1440
    if lang == "de":
        return f"in {days} Tag{'en' if days > 1 else ''}"
    return f"in {days} day{'s' if days > 1 else ''}"


async def _process_reminder(reminder: BookingReminder) -> None:
    """Dispatch a single reminder through the notification service."""
    async with async_session() as db:
        try:
            # Load the slot for context
            from sqlalchemy import select
            from sqlmodel import col

            slot_query = select(DutySlot).where(
                col(DutySlot.id) == reminder.duty_slot_id
            )
            result = await db.execute(slot_query)
            slot = result.scalar_one_or_none()

            if not slot:
                # Slot was deleted; mark reminder as expired
                await crud_reminder.mark_sent(db, reminder_id=reminder.id)
                await db.commit()
                return

            # Load event name
            from app.models.event import Event

            event_query = select(Event).where(col(Event.id) == slot.event_id)
            event_result = await db.execute(event_query)
            event = event_result.scalar_one_or_none()
            event_group_id = event.event_group_id if event else None

            svc = NotificationService(db)

            # Build scope chain for preference resolution
            scope_chain: list[tuple[str, object]] = []
            if slot.id:
                scope_chain.append(("duty_slot", slot.id))
            if slot.event_id:
                scope_chain.append(("event", slot.event_id))
            if event_group_id:
                scope_chain.append(("event_group", event_group_id))

            def _factory(lang: str) -> tuple[str, str]:
                return get_message(
                    "booking.reminder",
                    lang,
                    slot_title=slot.title,
                    time_until=_format_time_until(reminder.offset_minutes, lang),
                    date=slot.date.strftime("%d.%m.%Y") if slot.date else "",
                    start_time=slot.start_time.strftime("%H:%M")
                    if slot.start_time
                    else "",
                    end_time=slot.end_time.strftime("%H:%M") if slot.end_time else "",
                    location=slot.location or "",
                )

            await svc.notify(
                recipient_ids=[reminder.user_id],
                type_code="booking.reminder",
                message_factory=_factory,
                data={
                    "booking_id": str(reminder.booking_id),
                    "slot_id": str(slot.id),
                    "event_id": str(slot.event_id),
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
                    duty_slot_id=r.duty_slot_id,
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
