"""``crud.booking_reminder.replace_for_booking``: writing the reminders of a
booking that may have had some before.

Cancelling a booking leaves its reminder rows behind, cancelled, and
``uq_reminder_booking_offset`` allows one row per offset, so writing the same
offset again with a plain insert is an ``IntegrityError``: booking again after a
cancel, or a guest switching reminders off and on.
"""

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.models.booking import Booking
from app.models.booking_reminder import BookingReminder
from app.models.shift import Shift
from app.schemas.booking_reminder import ReminderOffsetEntry
from tests.fixtures.clock import set_instant

#: Three weeks before ``test_shift`` (2026-05-24 08:00, Berlin), so a reminder
#: a day ahead is still to come.
UTC_NOW = dt.datetime(2026, 5, 1, 6, 0)

DAY_BEFORE_BY_EMAIL = ReminderOffsetEntry(offset_minutes=1440, channels=["email"])
QUARTER_HOUR_BY_PUSH = ReminderOffsetEntry(offset_minutes=15, channels=["push"])

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _pinned_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    set_instant(monkeypatch, UTC_NOW)


def _slot_start(shift: Shift) -> dt.datetime:
    return dt.datetime.combine(shift.date, shift.start_time or dt.time())


async def _rows(db: AsyncSession, booking: Booking) -> list[tuple[int, str]]:
    result = await db.execute(
        select(col(BookingReminder.offset_minutes), col(BookingReminder.status))
        .where(col(BookingReminder.booking_id) == booking.id)
        .order_by(col(BookingReminder.offset_minutes))
    )
    return [(offset, status) for offset, status in result.all()]


async def _remind(
    db: AsyncSession, booking: Booking, shift: Shift, offset: int, status: str
) -> None:
    reminder = await crud_reminder.create_reminder(
        db,
        booking_id=booking.id,
        user_id=booking.user_id,
        shift_id=shift.id,
        offset_minutes=offset,
        slot_start=_slot_start(shift),
    )
    reminder.status = status
    await db.flush()


async def _replace(
    db: AsyncSession, booking: Booking, shift: Shift, entries: list[ReminderOffsetEntry]
) -> list[BookingReminder]:
    return await crud_reminder.replace_for_booking(
        db,
        booking_id=booking.id,
        user_id=booking.user_id,
        shift_id=shift.id,
        entries=entries,
        slot_start=_slot_start(shift),
        zone="Europe/Berlin",
    )


async def test_a_cancelled_row_gives_way_to_a_new_pending_one(
    db_session: AsyncSession, test_booking: Booking, test_shift: Shift
) -> None:
    await _remind(db_session, test_booking, test_shift, 1440, "cancelled")

    [written] = await _replace(
        db_session, test_booking, test_shift, [DAY_BEFORE_BY_EMAIL]
    )

    assert await _rows(db_session, test_booking) == [(1440, "pending")]
    assert written.channels == ["email"]
    # 08:00 in Berlin in May is 06:00 UTC, a day before.
    assert written.remind_at == dt.datetime(2026, 5, 23, 6, 0)


async def test_a_sent_reminder_is_kept_and_never_sent_again(
    db_session: AsyncSession, test_booking: Booking, test_shift: Shift
) -> None:
    await _remind(db_session, test_booking, test_shift, 1440, "sent")

    written = await _replace(
        db_session,
        test_booking,
        test_shift,
        [DAY_BEFORE_BY_EMAIL, QUARTER_HOUR_BY_PUSH],
    )

    assert [r.offset_minutes for r in written] == [15]
    assert await _rows(db_session, test_booking) == [(15, "pending"), (1440, "sent")]


async def test_no_entries_delete_everything_not_sent(
    db_session: AsyncSession, test_booking: Booking, test_shift: Shift
) -> None:
    await _remind(db_session, test_booking, test_shift, 15, "pending")
    await _remind(db_session, test_booking, test_shift, 60, "cancelled")
    await _remind(db_session, test_booking, test_shift, 120, "expired")
    await _remind(db_session, test_booking, test_shift, 1440, "sent")

    assert await _replace(db_session, test_booking, test_shift, []) == []
    assert await _rows(db_session, test_booking) == [(1440, "sent")]


async def test_switching_off_and_on_again_leaves_one_pending_row(
    db_session: AsyncSession, test_booking: Booking, test_shift: Shift
) -> None:
    for entries in (
        [DAY_BEFORE_BY_EMAIL],
        [],
        [DAY_BEFORE_BY_EMAIL],
        [DAY_BEFORE_BY_EMAIL],
    ):
        await _replace(db_session, test_booking, test_shift, entries)
    assert await _rows(db_session, test_booking) == [(1440, "pending")]


async def test_an_offset_given_twice_is_written_once(
    db_session: AsyncSession, test_booking: Booking, test_shift: Shift
) -> None:
    written = await _replace(
        db_session,
        test_booking,
        test_shift,
        [
            DAY_BEFORE_BY_EMAIL,
            ReminderOffsetEntry(offset_minutes=1440, channels=["push"]),
        ],
    )
    assert [(r.offset_minutes, r.channels) for r in written] == [(1440, ["email"])]
