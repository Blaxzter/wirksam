"""The retention sweep of guest data (``shared_lists.retention``).

A guest is due ``retention_days`` after their own last shift, judged by the
guest user's bookings, not by the event the guest signed up in: a task can
move to another event, and an event can be deleted while its tasks, and the
bookings on them, stay.
"""

import asyncio
import datetime as dt
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic.notifications import reminder_poller
from app.logic.shared_lists import retention
from app.logic.shared_lists.retention import sweep_guest_data
from app.models.booking import Booking
from app.models.event import Event
from app.models.shared_list import (
    GuestActivityLog,
    SharedList,
    SharedListGuest,
    SharedListGuestAlias,
)
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.models.voucher import VoucherEarning, VoucherEntry, VoucherPass
from tests.fixtures.guest_signups import add_shift, confirm_address
from tests.fixtures.shared_lists import ListGuest, ListGuestFactory
from tests.fixtures.storage import SessionsStub

RETENTION = 30


async def _sweep(db: AsyncSession, day: dt.date) -> None:
    await sweep_guest_data(
        db, now=dt.datetime.combine(day, dt.time(3, 0)), retention_days=RETENTION
    )


# Read back from the database: the sweep and the cascades it relies on work
# in SQL, behind the objects this session holds.


async def _user(db: AsyncSession, signed: ListGuest) -> User | None:
    return await db.scalar(
        select(User)
        .where(col(User.id) == signed.user.id)
        .execution_options(populate_existing=True)
    )


async def _contact(db: AsyncSession, signed: ListGuest) -> SharedListGuest | None:
    return await db.scalar(
        select(SharedListGuest)
        .where(col(SharedListGuest.user_id) == signed.user.id)
        .execution_options(populate_existing=True)
    )


async def _bookings(db: AsyncSession, signed: ListGuest) -> list[str]:
    rows = await db.execute(
        select(col(Booking.status)).where(col(Booking.user_id) == signed.user.id)
    )
    return sorted(rows.scalars())


async def test_due_by_the_guests_last_shift_not_the_events_end(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_task: Task,
) -> None:
    """The event ends on 14 June; the guest's shifts are on the 11th."""
    worked = await add_shift(db_session, test_task)
    dropped = await add_shift(db_session, test_task, start=dt.time(14), end=dt.time(15))
    signed = await make_list_guest(
        test_shared_list,
        name="Olga",
        email="olga@example.org",
        phone="0170 3",
        shifts=[worked, dropped],
    )
    signed.bookings[1].status = "cancelled"
    db_session.add(signed.bookings[1])
    await db_session.flush()

    await _sweep(db_session, dt.date(2026, 7, 11))
    user = await _user(db_session, signed)
    assert user is not None and user.name == "Olga"

    await _sweep(db_session, dt.date(2026, 7, 12))
    user = await _user(db_session, signed)
    contact = await _contact(db_session, signed)
    assert user is not None and contact is not None
    assert (user.name, user.phone_number) == (None, None)
    assert (contact.email, contact.manage_nonce) == (None, None)
    assert contact.erased_at == dt.datetime(2026, 7, 12, 3, 0)
    assert await _bookings(db_session, signed) == ["confirmed"]


async def test_a_guest_without_bookings_goes_by_their_last_sign_up(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
) -> None:
    signed = await make_list_guest(test_shared_list, email="p@example.org")
    signed.guest.last_signup_at = dt.datetime(2026, 5, 1, 12, 0)
    db_session.add(signed.guest)
    await db_session.flush()

    await _sweep(db_session, dt.date(2026, 5, 31))
    assert await _user(db_session, signed) is not None

    # Anonymised and, with nothing left, deleted in the same sweep.
    await _sweep(db_session, dt.date(2026, 6, 1))
    assert await _user(db_session, signed) is None
    assert await _contact(db_session, signed) is None


async def test_a_moved_task_keeps_its_guests_bookings_after_the_old_event_goes(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_task: Task,
    test_event: Event,
    test_private_event: Event,
) -> None:
    """The task moves to an event in September, then the June event is
    deleted: the guest loses their contact row with it, but their booking in
    September stays until 30 days after that shift."""
    september = await add_shift(db_session, test_task, day=dt.date(2026, 9, 2))
    signed = await make_list_guest(
        test_shared_list, name="Paul", email="paul@example.org", shifts=[september]
    )
    test_task.event_id = test_private_event.id
    db_session.add(test_task)
    await db_session.flush()
    await db_session.execute(delete(Event).where(col(Event.id) == test_event.id))
    assert await _contact(db_session, signed) is None

    await _sweep(db_session, dt.date(2026, 8, 1))
    user = await _user(db_session, signed)
    assert user is not None and user.name == "Paul"

    await _sweep(db_session, dt.date(2026, 10, 3))
    user = await _user(db_session, signed)
    assert user is not None and user.name is None
    assert await _bookings(db_session, signed) == ["confirmed"]


async def test_a_due_orphan_is_anonymised_and_kept_while_it_has_bookings(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_shift: Shift,
    test_event: Event,
) -> None:
    """``test_shift`` (24 May) stays with its task when the event goes."""
    signed = await make_list_guest(
        test_shared_list, name="Quinn", phone="0170 4", shifts=[test_shift]
    )
    await db_session.execute(delete(Event).where(col(Event.id) == test_event.id))

    await _sweep(db_session, dt.date(2026, 7, 1))

    user = await _user(db_session, signed)
    assert user is not None
    assert (user.name, user.phone_number) == (None, None)
    assert await _bookings(db_session, signed) == ["confirmed"]


async def test_an_anonymous_guest_with_nothing_left_is_deleted(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_shift: Shift,
) -> None:
    signed = await make_list_guest(test_shared_list, name="Rita", shifts=[test_shift])
    await _sweep(db_session, dt.date(2026, 7, 1))
    assert await _user(db_session, signed) is not None

    # The worked shift is deleted later; its cancelled booking goes, then
    # the guest.
    signed.bookings[0].status = "cancelled"
    db_session.add(signed.bookings[0])
    await db_session.flush()
    await _sweep(db_session, dt.date(2026, 7, 2))
    assert await _user(db_session, signed) is None


@pytest.mark.usefixtures("test_booking")
async def test_members_are_never_touched(
    db_session: AsyncSession, test_user: User
) -> None:
    name = test_user.name
    await _sweep(db_session, dt.date(2027, 1, 1))
    await db_session.refresh(test_user)
    assert test_user.name == name


async def test_the_activity_log_keeps_a_week(db_session: AsyncSession) -> None:
    now = dt.datetime(2026, 6, 20, 3, 0)
    db_session.add_all(
        [
            GuestActivityLog(kind="signup", created_at=now - dt.timedelta(days=8)),
            GuestActivityLog(kind="reminder", created_at=now - dt.timedelta(days=6)),
        ]
    )
    await db_session.flush()

    result = await sweep_guest_data(db_session, now=now, retention_days=RETENTION)

    assert result.log_rows_pruned == 1
    kinds = (
        (await db_session.execute(select(col(GuestActivityLog.kind)))).scalars().all()
    )
    assert kinds == ["reminder"]


async def test_the_poller_runs_the_sweep_with_the_configured_days(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.logic.clock.utc_now", lambda: dt.datetime(2026, 7, 1))
    monkeypatch.setattr(reminder_poller.settings, "GUEST_DATA_RETENTION_DAYS", 12)
    sweep = AsyncMock(wraps=sweep_guest_data)
    with (
        patch.object(reminder_poller, "async_session", SessionsStub(db_session)),
        patch.object(reminder_poller, "sweep_guest_data", sweep),
    ):
        await reminder_poller._guest_sweep_cycle()  # pyright: ignore[reportPrivateUsage]
    sweep.assert_awaited_once_with(
        db_session, now=dt.datetime(2026, 7, 1), retention_days=12
    )


async def test_the_poller_logs_what_the_sweep_did_and_survives_a_failure(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_shift: Shift,
) -> None:
    await make_list_guest(test_shared_list, shifts=[test_shift])
    db_session.add(GuestActivityLog(kind="signup", created_at=dt.datetime(2026, 8, 1)))
    await db_session.flush()
    monkeypatch.setattr("app.logic.clock.utc_now", lambda: dt.datetime(2026, 9, 1))
    logger = MagicMock()
    with (
        patch.object(reminder_poller, "async_session", SessionsStub(db_session)),
        patch.object(reminder_poller, "logger", logger),
    ):
        await reminder_poller._guest_sweep_cycle()  # pyright: ignore[reportPrivateUsage]
        logger.info.assert_called_once_with(
            "Guest retention: anonymised=1, deleted=0, log_rows_pruned=1"
        )
        with patch.object(
            reminder_poller, "sweep_guest_data", AsyncMock(side_effect=RuntimeError)
        ):
            await reminder_poller._guest_sweep_cycle()  # pyright: ignore[reportPrivateUsage]
    logger.exception.assert_called_once_with("Failed during the guest retention sweep")


async def test_the_sweep_has_a_turn_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every second cycle here; the cleanup's turn is not the sweep's."""
    sweep = AsyncMock()
    lock_result = MagicMock()
    lock_result.scalar.return_value = True
    lock = MagicMock(execute=AsyncMock(return_value=lock_result), commit=AsyncMock())
    # Four cycles, then the task is cancelled; only the real CancelledError
    # still matches the poller's except clauses.
    sleep = AsyncMock(side_effect=[None, None, None, asyncio.CancelledError])
    monkeypatch.setattr(reminder_poller, "_GUEST_SWEEP_EVERY_N_CYCLES", 2)
    monkeypatch.setattr(reminder_poller, "_CLEANUP_EVERY_N_CYCLES", 3)
    monkeypatch.setattr(reminder_poller, "_guest_sweep_cycle", sweep)
    monkeypatch.setattr(reminder_poller, "_cleanup_cycle", AsyncMock())
    monkeypatch.setattr(reminder_poller, "_poll_cycle", AsyncMock(return_value=0))
    monkeypatch.setattr(reminder_poller, "async_session", SessionsStub(lock))
    monkeypatch.setattr(
        reminder_poller,
        "asyncio",
        SimpleNamespace(sleep=sleep, CancelledError=asyncio.CancelledError),
    )

    await reminder_poller.run_reminder_poller()

    assert sweep.await_count == 2


async def test_erase_on_is_the_first_day_the_sweep_takes_the_guest(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_task: Task,
) -> None:
    """What the manage page promises is what the sweep does."""
    signed = await make_list_guest(
        test_shared_list, name="Sami", shifts=[await add_shift(db_session, test_task)]
    )
    erase_on = await retention.erase_on(
        db_session, user_id=signed.user.id, retention_days=RETENTION
    )
    assert erase_on == dt.date(2026, 7, 12)

    await _sweep(db_session, erase_on - dt.timedelta(days=1))
    user = await _user(db_session, signed)
    assert user is not None and user.name == "Sami"
    await _sweep(db_session, erase_on)
    user = await _user(db_session, signed)
    assert user is not None and user.name is None


async def test_the_days_are_counted_on_the_clock_of_the_guests_event(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_task: Task,
    test_event: Event,
) -> None:
    """New York is behind UTC. On the evening before the day the manage page
    names, UTC has that day already; the data stays until it has begun in
    New York."""
    test_event.timezone = "America/New_York"
    db_session.add(test_event)
    signed = await make_list_guest(
        test_shared_list, name="Nia", shifts=[await add_shift(db_session, test_task)]
    )
    erase_on = await retention.erase_on(
        db_session, user_id=signed.user.id, retention_days=RETENTION
    )
    assert erase_on == dt.date(2026, 7, 12)

    # 22:00 on 11 July in New York.
    await sweep_guest_data(
        db_session, now=dt.datetime(2026, 7, 12, 2, 0), retention_days=RETENTION
    )
    user = await _user(db_session, signed)
    assert user is not None and user.name == "Nia"
    # 01:00 on 12 July in New York.
    await sweep_guest_data(
        db_session, now=dt.datetime(2026, 7, 12, 5, 0), retention_days=RETENTION
    )
    user = await _user(db_session, signed)
    assert user is not None and user.name is None


async def test_the_sweep_takes_what_names_a_guest_and_what_spends_their_vouchers(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_shift: Shift,
) -> None:
    """Unredeemed vouchers expire: the manage link, the code on a screen and
    the merged chains' old links go. The kept booking loses its sign-up's
    name and phone, the correction its note; the amounts stay."""
    account = await make_list_guest(
        test_shared_list,
        name="Uta",
        email="fam@example.org",
        phone="0170 5",
        shifts=[test_shift],
    )
    merged = await make_list_guest(test_shared_list, email="fam@example.org")
    await confirm_address(db_session, account.guest)
    await confirm_address(db_session, merged.guest)
    db_session.add_all(
        [
            VoucherPass(
                event_id=test_shared_list.event_id,
                user_id=account.user.id,
                code="PQRSTU",
                expires_at=dt.datetime(2026, 6, 1),
            ),
            VoucherEntry(
                event_id=test_shared_list.event_id,
                user_id=account.user.id,
                kind="adjustment",
                amount=2,
                note="Für Uta, Kuchen",
            ),
        ]
    )
    await db_session.flush()

    await _sweep(db_session, dt.date(2026, 7, 1))

    [booking] = (
        await db_session.execute(
            select(Booking)
            .where(col(Booking.user_id) == account.user.id)
            .execution_options(populate_existing=True)
        )
    ).scalars()
    assert (booking.guest_name, booking.guest_phone) == (None, None)
    assert (
        await db_session.scalar(select(func.count(col(SharedListGuestAlias.id)))) == 0
    )
    assert (
        await db_session.scalar(
            select(func.count()).where(col(VoucherPass.user_id) == account.user.id)
        )
        == 0
    )
    entry = await db_session.scalar(
        select(VoucherEntry)
        .where(col(VoucherEntry.user_id) == account.user.id)
        .execution_options(populate_existing=True)
    )
    assert entry is not None and (entry.amount, entry.note) == (2, None)


async def test_a_guest_whose_only_name_is_on_a_booking_is_still_due(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_shift: Shift,
) -> None:
    signed = await make_list_guest(test_shared_list, name="Vera", shifts=[test_shift])
    signed.user.name = None
    db_session.add(signed.user)
    await db_session.flush()

    await _sweep(db_session, dt.date(2026, 7, 1))

    booking = await db_session.scalar(
        select(Booking)
        .where(col(Booking.user_id) == signed.user.id)
        .execution_options(populate_existing=True)
    )
    assert booking is not None and booking.guest_name is None


async def test_a_guest_with_vouchers_is_anonymised_but_never_deleted(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
) -> None:
    """No booking left, but a stand's redemption and an earning worth
    something name them: a CASCADE would rewrite the stand's history."""
    redeemed = await make_list_guest(test_shared_list, name="Wim")
    earned = await make_list_guest(test_shared_list, name="Xaver")
    for signed in (redeemed, earned):
        signed.guest.last_signup_at = dt.datetime(2026, 5, 1, 12, 0)
        db_session.add(signed.guest)
    db_session.add_all(
        [
            VoucherEntry(
                event_id=test_shared_list.event_id,
                user_id=redeemed.user.id,
                kind="redemption",
                amount=-1,
                method="code",
            ),
            VoucherEarning(
                event_id=test_shared_list.event_id,
                user_id=earned.user.id,
                booking_id=uuid.uuid4(),
                amount=2,
                task_name="Theke",
                shift_title="Theke",
                shift_date=dt.date(2026, 4, 30),
            ),
        ]
    )
    await db_session.flush()

    await _sweep(db_session, dt.date(2026, 7, 1))

    for signed in (redeemed, earned):
        user = await _user(db_session, signed)
        assert user is not None and user.name is None
