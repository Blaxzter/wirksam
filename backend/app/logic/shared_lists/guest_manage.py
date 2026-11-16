"""What a guest can do through their manage link: see their sign-ups and
vouchers, take their name off a shift, and switch the reminder mail on or
off.

Erasing is ``erase.py``, confirming the address ``guest_account.py``, and a
voucher code ``guest_vouchers.py``. Every caller has resolved the token
(``guest_tokens.resolve``), which holds the guest row ``FOR UPDATE``; none of
this takes a shift lock, since cancelling only frees places.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import NoReturn, cast

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.core.errors import raise_problem
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.crud.shift import wall_clocks
from app.logic import clock
from app.logic.shared_lists import guest_quota, guest_vouchers, retention
from app.logic.shared_lists.guest_mail import GUEST_REMINDER
from app.logic.shared_lists.guest_tokens import GuestKey
from app.logic.shared_lists.offer import starts_at
from app.logic.shared_lists.public_page import event_ref
from app.logic.work_hours import shift_ends_at
from app.models.booking import Booking
from app.models.booking_reminder import BookingReminder
from app.models.event import Event
from app.models.shared_list import SharedListGuest
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.public_shared_list import GuestSignupBooking, GuestSignupManage

# The rows as they come back. Outer joins: a booking whose shift was removed
# has no shift, task or event, and a task without an event has no event.
_BookingRow = tuple[Booking, Shift | None, Task | None, Event | None, bool]
_ShiftRow = tuple[Booking, Shift | None, Event | None]
_FutureRow = tuple[Booking, Shift, Event | None]


def _zone(event: Event | None) -> str:
    """The zone a booking's shift is on: its event's, or the default."""
    return event.timezone if event is not None else settings.EVENT_TIMEZONE


async def bookings_of(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[tuple[Booking, GuestSignupBooking]]:
    """Every booking of a guest, confirmed and cancelled, by date and time,
    with how the manage page shows it.

    Each is read with its own task and event, since a moved task takes its
    bookings to another event. A booking whose shift was removed shows what
    the cancellation kept of it. Each shows the name of its own sign-up, and
    no phone: the operator's export adds that from the row.
    """
    reminder_pending = (
        exists()
        .where(
            col(BookingReminder.booking_id) == col(Booking.id),
            col(BookingReminder.status) == "pending",
        )
        .correlate(Booking)
    )
    rows = await session.execute(
        select(Booking, Shift, Task, Event, reminder_pending)
        .outerjoin(Shift, col(Shift.id) == col(Booking.shift_id))
        .outerjoin(Task, col(Task.id) == col(Shift.task_id))
        .outerjoin(Event, col(Event.id) == col(Task.event_id))
        .where(col(Booking.user_id) == user_id)
    )
    clocks = await wall_clocks(session)
    out: list[tuple[Booking, GuestSignupBooking]] = []
    for booking, shift, task, event, reminder_on in cast(
        Sequence[_BookingRow], rows.all()
    ):
        confirmed = booking.status == "confirmed"
        if shift is not None and task is not None:
            shown = GuestSignupBooking(
                booking_id=booking.id,
                status="confirmed" if confirmed else "cancelled",
                event_name=event.name if event is not None else None,
                task_name=task.name,
                date=shift.date,
                start_time=shift.start_time,
                end_time=shift.end_time,
                location=shift.location,
                can_cancel=confirmed
                and shift_ends_at(shift.date, shift.start_time, shift.end_time)
                > clocks[_zone(event)],
                reminder_on=bool(reminder_on),
                vouchers=task.vouchers_per_shift,
                show_first_name=booking.show_first_name,
                name=booking.guest_name,
            )
        elif booking.cancelled_shift_date is not None:
            shown = GuestSignupBooking(
                booking_id=booking.id,
                status="cancelled",
                task_name=booking.cancelled_task_name
                or booking.cancelled_shift_title
                or "",
                date=booking.cancelled_shift_date,
                start_time=booking.cancelled_shift_start_time,
                end_time=booking.cancelled_shift_end_time,
                can_cancel=False,
                reminder_on=False,
                show_first_name=booking.show_first_name,
                name=booking.guest_name,
            )
        else:
            continue
        out.append((booking, shown))
    out.sort(
        key=lambda pair: (
            pair[1].date,
            pair[1].start_time or dt.time(),
            pair[1].booking_id,
        )
    )
    return out


async def manage_view(session: AsyncSession, key: GuestKey) -> GuestSignupManage:
    """The manage page behind a token that resolved: a chain's, or a guest
    account's with every sign-up confirmed into it."""
    guest = key.guest
    user = await session.get(User, guest.user_id)
    event = await session.get(Event, guest.event_id)
    # Both are foreign keys of the guest row, which the caller holds.
    assert user is not None and event is not None
    rows = await bookings_of(session, user_id=guest.user_id)
    confirmed = guest.confirmed_at is not None
    can_reject = key.from_mail and not confirmed
    days = settings.GUEST_DATA_RETENTION_DAYS
    return GuestSignupManage(
        name=user.name,
        email=guest.email,
        event=event_ref(event),
        bookings=[shown for _, shown in rows],
        can_set_reminders=guest.email is not None,
        confirmed=confirmed,
        can_confirm=key.from_mail and not confirmed and guest.email is not None,
        can_reject=can_reject,
        # Asked only where the page offers it: whether an address has an
        # account at some event is nobody's business who merely typed it.
        reject_suppresses=can_reject
        and guest.email is not None
        and await guest_quota.rejection_suppresses(session, address=guest.email),
        has_phone=user.phone_number is not None
        or any(booking.guest_phone is not None for booking, _ in rows),
        retention_days=days,
        erase_on=await retention.erase_on(
            session, user_id=guest.user_id, retention_days=days
        ),
        vouchers=await guest_vouchers.guest_vouchers(
            session, user_id=guest.user_id, own_event_id=guest.event_id
        ),
    )


def _not_found() -> NoReturn:
    raise_problem(
        404, code="guest_signup.not_found", detail="This link does not work (any more)"
    )


async def cancel(
    session: AsyncSession, *, guest: SharedListGuest, booking_id: uuid.UUID
) -> None:
    """Take the guest off one shift, until it is over, as members can.

    404 ``guest_signup.not_found`` for a booking that is not theirs, 409
    ``booking.shift_over`` once the shift has ended: hours are derived from
    shifts worked. Nobody is told; the guest did it. Cancelling twice is
    harmless.
    """
    row = cast(
        _ShiftRow | None,
        (
            await session.execute(
                select(Booking, Shift, Event)
                .outerjoin(Shift, col(Shift.id) == col(Booking.shift_id))
                .outerjoin(Task, col(Task.id) == col(Shift.task_id))
                .outerjoin(Event, col(Event.id) == col(Task.event_id))
                .where(col(Booking.id) == booking_id)
            )
        ).first(),
    )
    if row is None or row[0].user_id != guest.user_id:
        _not_found()
    booking, shift, event = row
    if booking.status != "confirmed":
        return
    if shift is not None and shift_ends_at(
        shift.date, shift.start_time, shift.end_time
    ) <= clock.wall_clock_now(event.timezone if event is not None else None):
        raise_problem(
            409, code="booking.shift_over", detail="This shift is already over"
        )
    booking.status = "cancelled"
    session.add(booking)
    await crud_reminder.cancel_by_booking(session, booking_id=booking.id)


async def set_reminders(
    session: AsyncSession, *, guest: SharedListGuest, enabled: bool
) -> None:
    """Switch the reminder mail on or off for every shift still ahead.

    409 ``guest_signup.no_email`` without an address to send it to. Rewritten
    whole each time (``replace_for_booking``), so switching back and forth
    leaves one reminder, and one that has gone out is not sent again.
    """
    if guest.email is None:
        raise_problem(
            409,
            code="guest_signup.no_email",
            detail="Reminders go by email, and this sign-up has no address",
        )
    rows = await session.execute(
        select(Booking, Shift, Event)
        .join(Shift, col(Shift.id) == col(Booking.shift_id))
        .join(Task, col(Task.id) == col(Shift.task_id))
        .outerjoin(Event, col(Event.id) == col(Task.event_id))
        .where(
            col(Booking.user_id) == guest.user_id,
            col(Booking.status) == "confirmed",
        )
    )
    clocks = await wall_clocks(session)
    for booking, shift, event in cast(Sequence[_FutureRow], rows.all()):
        zone = _zone(event)
        start = starts_at(shift.date, shift.start_time)
        if start <= clocks[zone]:
            continue
        await crud_reminder.replace_for_booking(
            session,
            booking_id=booking.id,
            user_id=guest.user_id,
            shift_id=shift.id,
            entries=[GUEST_REMINDER] if enabled else [],
            slot_start=start,
            zone=zone,
        )
