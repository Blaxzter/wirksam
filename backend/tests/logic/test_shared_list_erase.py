"""Erasing guests (``shared_lists.erase.erase_guests``), several at once.

Every route that erases goes through here (``test_public_shared_lists.py``,
``test_shared_list_signups.py``, ``test_list_guests_admin.py``); these pin
the rule across guests side by side, that only a guest is ever erased, and
what erasing does to vouchers and guest accounts.
Both clocks stand at 1 June 2026, after ``test_shift`` (24 May) and before
the 11 June shifts.
"""

import datetime as dt
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic import clock
from app.logic.shared_lists.erase import erase_guests
from app.models.booking import Booking
from app.models.shared_list import SharedList, SharedListGuest, SharedListGuestAlias
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.models.voucher import VoucherEntry, VoucherPass
from tests.fixtures.guest_signups import add_shift, confirm_address, freeze_clocks
from tests.fixtures.shared_lists import ListGuest, ListGuestFactory


@pytest.fixture(autouse=True)
def _clocks(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_clocks(monkeypatch)


async def _booking_ids(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(col(Booking.id)).where(col(Booking.user_id) == user_id)
    )
    return list(result.scalars().all())


async def test_each_guest_keeps_only_what_they_worked(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_task: Task,
    test_shift: Shift,
) -> None:
    ahead = await add_shift(db_session, test_task)
    worked = await make_list_guest(
        test_shared_list,
        name="Worked",
        email="w@example.org",
        shifts=[test_shift, ahead],
    )
    idle = await make_list_guest(
        test_shared_list, name="Idle", email="i@example.org", shifts=[ahead]
    )
    idle_id = idle.user.id

    await erase_guests(
        db_session, user_ids=[worked.user.id, idle_id], now=clock.utc_now()
    )

    db_session.expunge_all()
    assert await _booking_ids(db_session, worked.user.id) == [worked.bookings[0].id]
    kept = await db_session.get(User, worked.user.id)
    assert kept is not None and kept.name is None
    contact = await db_session.scalar(
        select(SharedListGuest).where(col(SharedListGuest.user_id) == worked.user.id)
    )
    assert contact is not None
    assert (contact.email, contact.manage_nonce) == (None, None)
    assert await db_session.get(User, idle_id) is None


async def test_an_account_that_is_no_guest_is_left_alone(
    db_session: AsyncSession, test_user: User, test_booking: Booking, test_task: Task
) -> None:
    """Whatever id a caller hands in: nothing of a member's goes."""
    ahead = await add_shift(db_session, test_task)
    future = Booking(shift_id=ahead.id, user_id=test_user.id, status="confirmed")
    db_session.add(future)
    await db_session.flush()
    name = test_user.name

    await erase_guests(db_session, user_ids=[test_user.id], now=clock.utc_now())

    db_session.expunge_all()
    member = await db_session.get(User, test_user.id)
    assert member is not None and member.name == name
    assert set(await _booking_ids(db_session, test_user.id)) == {
        test_booking.id,
        future.id,
    }


# ── Vouchers and guest accounts ───────────────────────────────────


async def _worked_with_vouchers(
    db: AsyncSession,
    shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    task: Task,
    worked_shift: Shift,
) -> ListGuest:
    """A guest with a worked shift that earned, a spent code, a code still on
    a screen, and a correction whose note names them."""
    task.vouchers_per_shift = 2
    db.add(task)
    signed = await make_list_guest(
        shared_list,
        name="Tom Gast",
        email="w@example.org",
        phone="0170 2",
        shifts=[worked_shift],
    )
    now = clock.utc_now()
    db.add_all(
        [
            VoucherPass(
                event_id=shared_list.event_id,
                user_id=signed.user.id,
                code="ABCDEF",
                expires_at=now,
                used_at=now,
            ),
            VoucherPass(
                event_id=shared_list.event_id,
                user_id=signed.user.id,
                code="GHJKMN",
                expires_at=now + dt.timedelta(minutes=2),
            ),
            VoucherEntry(
                event_id=shared_list.event_id,
                user_id=signed.user.id,
                kind="adjustment",
                amount=-1,
                note="Für Tom Gast, Handy leer",
            ),
        ]
    )
    await db.flush()
    return signed


async def test_erasing_strips_vouchers_of_whatever_names_or_spends_them(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_task: Task,
    test_shift: Shift,
) -> None:
    """The amounts stay, so the books add up; the code on a screen stops
    working, the correction's note goes, and the kept booking's name and
    phone go with the user's."""
    signed = await _worked_with_vouchers(
        db_session, test_shared_list, make_list_guest, test_task, test_shift
    )

    await erase_guests(db_session, user_ids=[signed.user.id], now=clock.utc_now())

    db_session.expunge_all()
    codes = await db_session.execute(
        select(col(VoucherPass.code)).where(col(VoucherPass.user_id) == signed.user.id)
    )
    assert list(codes.scalars()) == ["ABCDEF"]
    [entry] = (
        await db_session.execute(
            select(VoucherEntry).where(col(VoucherEntry.user_id) == signed.user.id)
        )
    ).scalars()
    assert (entry.amount, entry.note) == (-1, None)
    [booking] = (
        await db_session.execute(
            select(Booking).where(col(Booking.user_id) == signed.user.id)
        )
    ).scalars()
    assert (booking.guest_name, booking.guest_phone) == (None, None)


async def test_a_guest_with_ledger_entries_is_never_deleted(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_task: Task,
) -> None:
    """Nothing worked, but a stand redeemed for them: deleting the user would
    take the redemption, and the stand's history, with it."""
    signed = await make_list_guest(
        test_shared_list, shifts=[await add_shift(db_session, test_task)]
    )
    db_session.add(
        VoucherEntry(
            event_id=test_shared_list.event_id,
            user_id=signed.user.id,
            kind="redemption",
            amount=-1,
            method="code",
        )
    )
    await db_session.flush()

    await erase_guests(db_session, user_ids=[signed.user.id], now=clock.utc_now())

    db_session.expunge_all()
    kept = await db_session.get(User, signed.user.id)
    assert kept is not None and kept.name is None
    assert await _booking_ids(db_session, signed.user.id) == []


async def test_erasing_an_account_frees_its_address_and_its_old_links(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_shift: Shift,
) -> None:
    account = await make_list_guest(
        test_shared_list, email="fam@example.org", shifts=[test_shift]
    )
    merged = await make_list_guest(test_shared_list, email="fam@example.org")
    await confirm_address(db_session, account.guest)
    await confirm_address(db_session, merged.guest)

    await erase_guests(db_session, user_ids=[account.user.id], now=clock.utc_now())

    assert (
        await db_session.scalar(select(func.count(col(SharedListGuestAlias.id)))) == 0
    )
    fresh = await make_list_guest(test_shared_list, email="fam@example.org")
    key = await confirm_address(db_session, fresh.guest)
    assert key.guest.user_id == fresh.user.id


async def test_erasing_an_account_leaves_unconfirmed_chains_of_its_address(
    db_session: AsyncSession,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    test_task: Task,
) -> None:
    """Its scope is what was confirmed into it: the other chain may be
    somebody else's who shares the address."""
    account = await make_list_guest(test_shared_list, email="fam@example.org")
    unconfirmed = await make_list_guest(
        test_shared_list,
        email="fam@example.org",
        shifts=[await add_shift(db_session, test_task)],
    )
    await confirm_address(db_session, account.guest)

    await erase_guests(db_session, user_ids=[account.user.id], now=clock.utc_now())

    db_session.expunge_all()
    contact = await db_session.scalar(
        select(SharedListGuest).where(
            col(SharedListGuest.user_id) == unconfirmed.user.id
        )
    )
    assert contact is not None
    assert (contact.email, contact.erased_at) == ("fam@example.org", None)
    assert await _booking_ids(db_session, unconfirmed.user.id) == [
        unconfirmed.bookings[0].id
    ]
