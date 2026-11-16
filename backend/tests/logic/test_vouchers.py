"""How a voucher balance is worked out (``app.logic.vouchers``).

Earned vouchers are derived from bookings until something would change what an
ended booking earned; then they are settled (frozen) first. Most tests here
build shifts and bookings directly and pass ``now`` in: what matters is which
bookings count, and from when. The "earned is earned" tests make the changes
through the API, so they also prove that every route settles before it acts.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import AsyncClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.event_membership import event_membership as crud_membership
from app.crud.voucher import voucher as crud_voucher
from app.logic import clock, vouchers, work_hours
from app.logic.shared_lists.erase import erase_guests
from app.models.booking import Booking
from app.models.event import Event
from app.models.shared_list import SharedList
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User
from app.models.voucher import VoucherEarning, VoucherEntry, VoucherPass
from app.schemas.voucher import VoucherCheckResult, VoucherRedeemResult
from tests.fixtures.client import act_as
from tests.fixtures.clock import fixed_clock
from tests.fixtures.guest_signups import confirm_address
from tests.fixtures.shared_lists import ListGuest, ListGuestFactory, SharedListFactory

DAY = dt.date(2026, 6, 11)


def at(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute))


async def _voucher_task(
    db: AsyncSession, event: Event, creator: User, *, per_shift: int = 2, **cols: Any
) -> Task:
    task = Task(
        name=cols.pop("name", "Theke"),
        start_date=DAY,
        end_date=DAY + dt.timedelta(days=2),
        status="published",
        created_by_id=creator.id,
        event_id=event.id,
        vouchers_per_shift=per_shift,
        **cols,
    )
    db.add(task)
    await db.flush()
    return task


async def _booked(
    db: AsyncSession,
    task: Task,
    user: User,
    *,
    date: dt.date = DAY,
    start: dt.time | None = dt.time(8),
    end: dt.time | None = dt.time(12),
    status: str = "confirmed",
    batch: ShiftBatch | None = None,
) -> Shift:
    shift = Shift(
        task_id=task.id,
        batch_id=batch.id if batch else None,
        title=f"Shift {uuid.uuid4().hex[:6]}",
        date=date,
        start_time=start,
        end_time=end,
        max_bookings=5,
    )
    db.add(shift)
    await db.flush()
    db.add(Booking(shift_id=shift.id, user_id=user.id, status=status))
    await db.flush()
    return shift


async def _entry(
    db: AsyncSession, event: Event, user: User, amount: int, kind: str = "adjustment"
) -> None:
    db.add(
        VoucherEntry(
            event_id=event.id,
            user_id=user.id,
            kind=kind,
            amount=amount,
            note="Korrektur" if kind == "adjustment" else None,
        )
    )
    await db.flush()


async def _summary(
    db: AsyncSession, event: Event, user: User, now: dt.datetime
) -> dict[str, int]:
    acc = await vouchers.account(db, event.id, user, now=now)
    s = acc.summary
    return {
        "earned": s.earned,
        "upcoming": s.upcoming,
        "redeemed": s.redeemed,
        "adjusted": s.adjusted,
        "available": s.available,
    }


async def _earning_rows(db: AsyncSession, **where: Any) -> list[VoucherEarning]:
    query = select(VoucherEarning).execution_options(populate_existing=True)
    for name, value in where.items():
        query = query.where(getattr(VoucherEarning, name) == value)
    return list((await db.execute(query)).scalars())


# ── Pure helpers ──────────────────────────────────────────────────


class TestNormalizeCode:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("K7M4QX", "K7M4QX"),
            ("k7m-4qx", "K7M4QX"),
            ("  K7M 4QX ", "K7M4QX"),
            ("WV1:K7M4QX", "K7M4QX"),
            ("wv1:k7m-4qx", "K7M4QX"),
        ],
    )
    def test_accepts_what_a_screen_or_a_scanner_gives(
        self, raw: str, expected: str
    ) -> None:
        assert vouchers.normalize_code(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "K7M4Q",  # too short
            "K7M4QXX",  # too long
            "K7M4Q0",  # 0 is not in the alphabet
            "OIL123",  # O, I, L neither
            "WV2:K7M4QX",  # another prefix
            "K7M_4QX",
        ],
    )
    def test_refuses_anything_else(self, raw: str) -> None:
        assert vouchers.normalize_code(raw) is None

    def test_generated_codes_normalize_to_themselves(self) -> None:
        for _ in range(50):
            code = vouchers.generate_code()
            assert len(code) == vouchers.CODE_LENGTH
            assert vouchers.normalize_code(code) == code


class TestRedeemWindow:
    def test_thirty_minutes_either_side(self) -> None:
        assert vouchers.redeem_window(DAY, dt.time(18), dt.time(22)) == (
            at(DAY, 17, 30),
            at(DAY, 22, 30),
        )

    def test_an_untimed_shift_runs_all_day(self) -> None:
        nxt = DAY + dt.timedelta(days=1)
        assert vouchers.redeem_window(DAY, None, None) == (
            at(DAY - dt.timedelta(days=1), 23, 30),
            at(nxt, 0, 30),
        )

    def test_an_overnight_shift_closes_the_next_morning(self) -> None:
        nxt = DAY + dt.timedelta(days=1)
        assert vouchers.redeem_window(DAY, dt.time(22), dt.time(2)) == (
            at(DAY, 21, 30),
            at(nxt, 2, 30),
        )

    def test_late_evening_includes_tomorrow(self) -> None:
        """At 23:40 a shift tomorrow at 00:05 is already open."""
        first, last = vouchers.redeem_window_dates(at(DAY, 23, 40))
        assert last == DAY + dt.timedelta(days=1)
        assert first <= DAY
        assert vouchers.in_redeem_window(
            at(DAY, 23, 40), DAY + dt.timedelta(days=1), dt.time(0, 5), dt.time(4)
        )

    def test_early_morning_includes_yesterday(self) -> None:
        """At 01:00 yesterday's 22:00-02:00 shift is still running."""
        first, last = vouchers.redeem_window_dates(at(DAY, 1))
        assert first == DAY - dt.timedelta(days=1)
        assert last == DAY
        assert vouchers.in_redeem_window(
            at(DAY, 1), DAY - dt.timedelta(days=1), dt.time(22), dt.time(2)
        )


class TestPassRedeemable:
    def _pass(self, **cols: Any) -> VoucherPass:
        return VoucherPass(
            event_id=uuid.uuid4(), user_id=uuid.uuid4(), code="K7M4QX", **cols
        )

    def test_until_it_expires(self) -> None:
        now = at(DAY, 12)
        p = self._pass(expires_at=now + dt.timedelta(seconds=1))
        assert vouchers.pass_redeemable(p, now)
        assert not vouchers.pass_redeemable(p, now + dt.timedelta(seconds=1))

    def test_a_check_holds_it_for_a_minute_past_expiry(self) -> None:
        now = at(DAY, 12)
        p = self._pass(
            expires_at=now - dt.timedelta(seconds=30),
            checked_at=now - dt.timedelta(seconds=59),
        )
        assert vouchers.pass_redeemable(p, now)
        assert not vouchers.pass_redeemable(p, now + dt.timedelta(seconds=1))

    def test_never_once_used(self) -> None:
        now = at(DAY, 12)
        p = self._pass(expires_at=now + dt.timedelta(minutes=1), used_at=now)
        assert not vouchers.pass_redeemable(p, now)


# ── Derivation ────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestEarned:
    async def test_only_ended_shifts_earn(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user, per_shift=3)
        await _booked(db_session, task, test_user, start=dt.time(8), end=dt.time(12))

        before = await _summary(db_session, test_event, test_user, at(DAY, 11, 59))
        assert before["earned"] == 0
        assert before["upcoming"] == 3
        after = await _summary(db_session, test_event, test_user, at(DAY, 12))
        assert after["earned"] == 3
        assert after["upcoming"] == 0
        assert after["available"] == 3

    async def test_an_overnight_shift_earns_the_next_morning(
        self, db_session: AsyncSession, test_event: Event, test_user: User
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user)
        await _booked(db_session, task, test_user, start=dt.time(22), end=dt.time(2))
        nxt = DAY + dt.timedelta(days=1)

        assert (await _summary(db_session, test_event, test_user, at(nxt, 1, 59)))[
            "earned"
        ] == 0
        assert (await _summary(db_session, test_event, test_user, at(nxt, 2)))[
            "earned"
        ] == 2

    async def test_an_untimed_shift_earns_at_midnight(
        self, db_session: AsyncSession, test_event: Event, test_user: User
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user)
        await _booked(db_session, task, test_user, start=None, end=None)
        nxt = DAY + dt.timedelta(days=1)

        assert (await _summary(db_session, test_event, test_user, at(DAY, 23, 59)))[
            "earned"
        ] == 0
        assert (await _summary(db_session, test_event, test_user, at(nxt, 0)))[
            "earned"
        ] == 2

    async def test_a_start_only_shift_earns_at_midnight(
        self, db_session: AsyncSession, test_event: Event, test_user: User
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user)
        await _booked(db_session, task, test_user, start=dt.time(18), end=None)
        nxt = DAY + dt.timedelta(days=1)

        assert (await _summary(db_session, test_event, test_user, at(DAY, 23)))[
            "earned"
        ] == 0
        assert (await _summary(db_session, test_event, test_user, at(nxt, 0)))[
            "earned"
        ] == 2

    async def test_end_equal_to_start_is_a_whole_day(
        self, db_session: AsyncSession, test_event: Event, test_user: User
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user)
        await _booked(db_session, task, test_user, start=dt.time(6), end=dt.time(6))
        nxt = DAY + dt.timedelta(days=1)

        assert (await _summary(db_session, test_event, test_user, at(nxt, 5, 59)))[
            "earned"
        ] == 0
        assert (await _summary(db_session, test_event, test_user, at(nxt, 6)))[
            "earned"
        ] == 2

    async def test_cancelled_bookings_and_tasks_without_vouchers_do_not_count(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        earning = await _voucher_task(db_session, test_event, test_user)
        nothing = await _voucher_task(
            db_session, test_event, test_user, per_shift=0, name="Ohne"
        )
        await _booked(db_session, earning, test_user, status="cancelled")
        await _booked(db_session, nothing, test_user)

        acc = await vouchers.account(
            db_session, test_event.id, test_user, now=at(DAY, 20)
        )
        assert acc.summary.earned == 0
        assert acc.summary.upcoming == 0
        assert acc.shifts == []

    async def test_another_events_bookings_do_not_count(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_draft_event: Event,
        test_user: User,
    ) -> None:
        elsewhere = await _voucher_task(db_session, test_draft_event, test_user)
        await _booked(db_session, elsewhere, test_user)
        await _entry(db_session, test_draft_event, test_user, 5)

        summary = await _summary(db_session, test_event, test_user, at(DAY, 20))
        assert summary == dict.fromkeys(summary, 0)

    async def test_ends_at_is_utc(
        self, db_session: AsyncSession, test_event: Event, test_user: User
    ) -> None:
        """An 18:00 shift at a Berlin venue in June ends at 16:00 UTC, so the
        history sorts it on the same line as entries stamped in UTC."""
        task = await _voucher_task(db_session, test_event, test_user)
        await _booked(db_session, task, test_user, start=dt.time(14), end=dt.time(18))

        acc = await vouchers.account(
            db_session, test_event.id, test_user, now=at(DAY, 20)
        )
        (shift,) = acc.shifts
        assert shift.ends_at == at(DAY, 16)
        assert shift.completed
        assert shift.vouchers == 2
        assert shift.task_id == task.id


@pytest.mark.asyncio
class TestLedger:
    async def test_redemptions_lower_it_and_corrections_move_it_both_ways(
        self, db_session: AsyncSession, test_event: Event, test_user: User
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user, per_shift=4)
        await _booked(db_session, task, test_user)
        await _entry(db_session, test_event, test_user, -3, kind="redemption")
        await _entry(db_session, test_event, test_user, 2)
        await _entry(db_session, test_event, test_user, -1)

        assert await _summary(db_session, test_event, test_user, at(DAY, 20)) == {
            "earned": 4,
            "upcoming": 0,
            "redeemed": 3,
            "adjusted": 1,
            "available": 2,
        }
        assert (
            await vouchers.available_for(
                db_session, test_event.id, test_user.id, now=at(DAY, 20)
            )
            == 2
        )


@pytest.mark.asyncio
class TestBalances:
    async def test_former_members_appear_only_with_something_to_show(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        test_outsider_user: User,
        test_inactive_user: User,
    ) -> None:
        """Someone who worked and left still worked; someone who left with
        nothing at all is not a row the organisers need to see."""
        task = await _voucher_task(db_session, test_event, test_user)
        # Never members of test_event, but they worked there / were corrected.
        await _booked(db_session, task, test_outsider_user)
        await _booked(db_session, task, test_inactive_user, status="cancelled")

        rows = await vouchers.balances(db_session, test_event.id, now=at(DAY, 20))
        by_user = {r.user_id: r for r in rows}

        assert by_user[test_outsider_user.id].role is None
        assert by_user[test_outsider_user.id].earned == 2
        assert test_inactive_user.id not in by_user
        # Every member is listed, zero or not.
        assert by_user[test_user.id].role == "member"
        assert by_user[test_user.id].available == 0
        # Most available first.
        assert rows[0].user_id == test_outsider_user.id

    async def test_a_former_member_with_only_a_correction_is_listed(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_outsider_user: User,
    ) -> None:
        await _entry(db_session, test_event, test_outsider_user, -1)

        rows = await vouchers.balances(db_session, test_event.id, now=at(DAY, 20))
        row = next(r for r in rows if r.user_id == test_outsider_user.id)
        # Written straight to the ledger, past the API's cap: the guard keeps
        # what can be redeemed at zero.
        assert row.adjusted == -1
        assert row.available == 0


@pytest.mark.asyncio
async def test_leaving_keeps_what_was_earned(
    db_session: AsyncSession, test_event: Event, test_user: User
) -> None:
    """The derivation does not filter on membership: work done stays done."""
    task = await _voucher_task(db_session, test_event, test_user)
    await _booked(db_session, task, test_user)
    await crud_membership.remove(
        db_session, user_id=test_user.id, event_id=test_event.id
    )

    acc = await vouchers.account(db_session, test_event.id, test_user, now=at(DAY, 20))
    assert acc.summary.earned == 2
    assert acc.summary.role is None


@pytest.mark.asyncio
async def test_a_code_already_taken_is_drawn_again(
    db_session: AsyncSession,
    test_event: Event,
    test_user: User,
    test_event_admin_user: User,
) -> None:
    """Codes are unique across the installation; a collision retries."""
    now = at(DAY, 10)
    taken = VoucherPass(
        event_id=test_event.id,
        user_id=test_event_admin_user.id,
        code="K7M4QX",
        expires_at=now + vouchers.PASS_TTL,
    )
    db_session.add(taken)
    await db_session.flush()
    draws = iter(["K7M4QX", "K7M4QX", "Q2W3E4"])

    issued = await crud_voucher.issue_pass(
        db_session,
        event_id=test_event.id,
        user_id=test_user.id,
        now=now,
        ttl=vouchers.PASS_TTL,
        hold=vouchers.PASS_HOLD,
        new_code=lambda: next(draws),
    )

    assert issued.code == "Q2W3E4"
    assert issued.expires_at == now + vouchers.PASS_TTL
    # The other person's code was not touched.
    assert await db_session.get(VoucherPass, taken.id) is not None


# ── Settling ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSettle:
    """``settle_earnings`` on its own: which bookings it freezes, and how often."""

    async def test_twice_writes_one_row_per_booking(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        test_outsider_user: User,
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user)
        await _booked(db_session, task, test_user)
        other = await _booked(db_session, task, test_outsider_user)
        now = at(DAY, 20)

        first = await vouchers.settle_earnings(db_session, now=now, task_ids=[task.id])
        again = await vouchers.settle_earnings(db_session, now=now, task_ids=[task.id])
        by_shift = await vouchers.settle_earnings(
            db_session, now=now, shift_ids=[other.id]
        )
        assert (first, again, by_shift) == (2, 0, 0)

        rows = await _earning_rows(db_session, task_id=task.id)
        assert sorted(r.user_id for r in rows) == sorted(
            [test_user.id, test_outsider_user.id]
        )
        assert {(r.amount, r.event_id) for r in rows} == {(2, test_event.id)}
        # Settling turns a derived amount into the same stored one.
        assert (await _summary(db_session, test_event, test_user, now))["earned"] == 2

    async def test_only_ended_worked_bookings(
        self, db_session: AsyncSession, test_event: Event, test_user: User
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user)
        ended = await _booked(db_session, task, test_user)
        # Running at 20:00, tomorrow's, and a cancelled one: none has earned.
        await _booked(db_session, task, test_user, start=dt.time(19), end=dt.time(21))
        await _booked(db_session, task, test_user, date=DAY + dt.timedelta(days=1))
        await _booked(db_session, task, test_user, status="cancelled")

        written = await vouchers.settle_earnings(
            db_session, now=at(DAY, 20), task_ids=[task.id]
        )

        assert written == 1
        (row,) = await _earning_rows(db_session, task_id=task.id)
        assert row.shift_id == ended.id
        assert (row.task_name, row.shift_title) == ("Theke", ended.title)
        assert (row.shift_date, row.shift_start_time, row.shift_end_time) == (
            DAY,
            dt.time(8),
            dt.time(12),
        )

    async def test_an_overnight_shift_from_yesterday_once_it_is_over(
        self, db_session: AsyncSession, test_event: Event, test_user: User
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user)
        await _booked(db_session, task, test_user, start=dt.time(22), end=dt.time(2))
        nxt = DAY + dt.timedelta(days=1)

        running = await vouchers.settle_earnings(
            db_session, now=at(nxt, 1, 59), task_ids=[task.id]
        )
        over = await vouchers.settle_earnings(
            db_session, now=at(nxt, 2), task_ids=[task.id]
        )
        assert (running, over) == (0, 1)

    async def test_tasks_at_zero_only_with_include_zero(
        self, db_session: AsyncSession, test_event: Event, test_user: User
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user, per_shift=0)
        await _booked(db_session, task, test_user)
        now = at(DAY, 20)

        plain = await vouchers.settle_earnings(db_session, now=now, task_ids=[task.id])
        with_zero = await vouchers.settle_earnings(
            db_session, now=now, task_ids=[task.id], include_zero=True
        )
        assert (plain, with_zero) == (0, 1)
        (row,) = await _earning_rows(db_session, task_id=task.id)
        assert row.amount == 0
        # A zero row is no part of anyone's history.
        acc = await vouchers.account(db_session, test_event.id, test_user, now=now)
        assert acc.shifts == []

    async def test_needs_something_to_settle(self, db_session: AsyncSession) -> None:
        now = at(DAY, 20)
        with pytest.raises(TypeError):
            await vouchers.settle_earnings(db_session, now=now)
        assert await vouchers.settle_earnings(db_session, now=now, task_ids=[]) == 0
        assert await vouchers.settle_earnings(db_session, now=now, shift_ids=[]) == 0


@pytest.mark.asyncio
class TestSettledReads:
    """Reading a balance once some of it is settled."""

    async def test_a_settled_booking_keeps_its_amount_when_the_rate_rises(
        self, db_session: AsyncSession, test_event: Event, test_user: User
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user)
        await _booked(db_session, task, test_user)
        await vouchers.settle_earnings(db_session, now=at(DAY, 20), task_ids=[task.id])

        task.vouchers_per_shift = 5
        db_session.add(task)
        await db_session.flush()

        summary = await _summary(db_session, test_event, test_user, at(DAY, 20))
        assert summary["earned"] == 2

    async def test_a_settled_shift_moved_into_the_future_does_not_earn_twice(
        self, db_session: AsyncSession, test_event: Event, test_user: User
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user)
        shift = await _booked(db_session, task, test_user)
        await vouchers.settle_earnings(db_session, now=at(DAY, 20), task_ids=[task.id])

        shift.date = DAY + dt.timedelta(days=2)
        db_session.add(shift)
        await db_session.flush()

        now = await _summary(db_session, test_event, test_user, at(DAY, 20))
        assert (now["earned"], now["upcoming"]) == (2, 0)
        later = await _summary(
            db_session, test_event, test_user, at(DAY + dt.timedelta(days=4), 12)
        )
        assert (later["earned"], later["upcoming"]) == (2, 0)

    async def test_a_settled_row_reads_from_its_snapshot(
        self, db_session: AsyncSession, test_event: Event, test_user: User
    ) -> None:
        """Renaming afterwards changes nothing, and ``ends_at`` is UTC like the
        derived rows: 12:00 at a Berlin venue in June is 10:00 UTC."""
        task = await _voucher_task(db_session, test_event, test_user)
        shift = await _booked(db_session, task, test_user)
        title = shift.title
        await vouchers.settle_earnings(db_session, now=at(DAY, 20), task_ids=[task.id])

        task.name = "Bar"
        shift.title = "Renamed"
        db_session.add_all([task, shift])
        await db_session.flush()

        acc = await vouchers.account(
            db_session, test_event.id, test_user, now=at(DAY, 20)
        )
        (row,) = acc.shifts
        assert row.settled
        assert row.completed
        assert (row.task_name, row.title) == ("Theke", title)
        assert (row.shift_id, row.task_id) == (shift.id, task.id)
        assert row.ends_at == at(DAY, 10)
        assert row.vouchers == 2


@dataclass
class _Guested:
    """A guest booked on an ended shift that earns 2, beside a member on it,
    and a point that takes vouchers."""

    task: Task
    shift: Shift
    shared_list: SharedList
    guest: ListGuest
    point: Task


@pytest_asyncio.fixture
async def guested(
    db_session: AsyncSession,
    test_event: Event,
    test_user: User,
    make_shared_list: SharedListFactory,
    make_list_guest: ListGuestFactory,
) -> _Guested:
    task = await _voucher_task(db_session, test_event, test_user)
    shift = await _booked(db_session, task, test_user)
    shared_list = await make_shared_list(tasks=[task])
    guest = await make_list_guest(
        shared_list, name="Gast Gastmann", email="gast@example.org", shifts=[shift]
    )
    point = await _voucher_task(
        db_session,
        test_event,
        test_user,
        per_shift=0,
        name="Bar",
        is_voucher_point=True,
    )
    return _Guested(
        task=task, shift=shift, shared_list=shared_list, guest=guest, point=point
    )


async def _guest_code(
    db: AsyncSession, event: Event, user_id: uuid.UUID
) -> VoucherPass:
    return await vouchers.issue_pass(
        db, event_id=event.id, user_id=user_id, now=clock.utc_now()
    )


async def _redeem(
    db: AsyncSession,
    event: Event,
    g: _Guested,
    redeemer: User,
    *,
    code: str | None = None,
    user_id: uuid.UUID | None = None,
    amount: int = 1,
    request_id: uuid.UUID | None = None,
) -> VoucherRedeemResult:
    return await vouchers.redeem(
        db,
        event_id=event.id,
        task=g.point,
        redeemer=redeemer,
        code=code,
        user_id=user_id,
        amount=amount,
        request_id=request_id or uuid.uuid4(),
        wall_now=at(DAY, 20),
        utc_now=clock.utc_now(),
    )


async def _check(
    db: AsyncSession,
    event: Event,
    *,
    code: str | None = None,
    user_id: uuid.UUID | None = None,
) -> VoucherCheckResult:
    return await vouchers.check(
        db,
        event_id=event.id,
        code=code,
        user_id=user_id,
        wall_now=at(DAY, 20),
        utc_now=clock.utc_now(),
    )


def _refused(exc: pytest.ExceptionInfo[HTTPException]) -> tuple[int, str]:
    detail: Any = exc.value.detail
    return exc.value.status_code, detail["code"]


@pytest.mark.asyncio
class TestListGuests:
    """A guest who signed up through a shared list earns like a member. They
    redeem by showing a code, never by being picked from a list: showing it is
    their consent to be named at the stand."""

    async def test_an_ended_guest_booking_earns_the_rate(
        self, db_session: AsyncSession, test_event: Event, guested: _Guested
    ) -> None:
        await _booked(
            db_session,
            guested.task,
            guested.guest.user,
            date=DAY + dt.timedelta(days=1),
        )

        summary = await _summary(
            db_session, test_event, guested.guest.user, at(DAY, 20)
        )

        assert (summary["earned"], summary["upcoming"]) == (2, 2)

    async def test_a_guest_booking_is_settled_at_the_rate(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        guested: _Guested,
    ) -> None:
        written = await vouchers.settle_earnings(
            db_session, now=at(DAY, 20), task_ids=[guested.task.id], include_zero=True
        )

        assert written == 2
        rows = await _earning_rows(db_session, task_id=guested.task.id)
        assert {r.user_id: r.amount for r in rows} == {
            test_user.id: 2,
            guested.guest.user.id: 2,
        }
        guested.task.vouchers_per_shift = 0
        db_session.add(guested.task)
        await db_session.flush()
        summary = await _summary(
            db_session, test_event, guested.guest.user, at(DAY, 20)
        )
        assert summary["earned"] == 2

    async def test_a_guest_shows_in_the_overview_tagged_with_their_address(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        guested: _Guested,
    ) -> None:
        rows = {
            r.user_id: r
            for r in await vouchers.balances(db_session, test_event.id, now=at(DAY, 20))
        }

        guest = rows[guested.guest.user.id]
        assert (guest.is_guest, guest.role, guest.name, guest.email) == (
            True,
            None,
            "Gast Gastmann",
            "gast@example.org",
        )
        assert guest.available == 2
        assert rows[test_user.id].is_guest is False

    async def test_the_redeem_picker_never_lists_a_guest(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        guested: _Guested,
    ) -> None:
        available = await vouchers.available_for_members(
            db_session, test_event.id, now=at(DAY, 20)
        )

        assert available[test_user.id] == 2
        assert guested.guest.user.id not in available

    async def test_check_by_code_names_a_guest_as_a_guest(
        self, db_session: AsyncSession, test_event: Event, guested: _Guested
    ) -> None:
        p = await _guest_code(db_session, test_event, guested.guest.user.id)

        result = await _check(db_session, test_event, code=p.code)

        assert (result.user_id, result.name, result.is_guest, result.available) == (
            guested.guest.user.id,
            "Gast Gastmann",
            True,
            2,
        )

    async def test_redeem_by_code_takes_from_a_live_guest(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_event_admin_user: User,
        guested: _Guested,
    ) -> None:
        p = await _guest_code(db_session, test_event, guested.guest.user.id)

        result = await _redeem(
            db_session, test_event, guested, test_event_admin_user, code=p.code
        )

        assert (result.user_id, result.available) == (guested.guest.user.id, 1)
        assert result.entry.method == "code"

    async def test_redeem_by_hand_refuses_a_guest(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_event_admin_user: User,
        guested: _Guested,
    ) -> None:
        user_id = guested.guest.user.id
        with pytest.raises(HTTPException) as checked:
            await _check(db_session, test_event, user_id=user_id)
        with pytest.raises(HTTPException) as redeemed:
            await _redeem(
                db_session, test_event, guested, test_event_admin_user, user_id=user_id
            )

        assert _refused(checked) == (404, "event.member_not_found")
        assert _refused(redeemed) == (404, "event.member_not_found")

    async def test_an_erased_guest_cannot_redeem(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_event_admin_user: User,
        guested: _Guested,
    ) -> None:
        """Erasing deletes the unused code; the worked shift and its vouchers
        stay on the anonymous row, which no code can reach any more."""
        p = await _guest_code(db_session, test_event, guested.guest.user.id)
        await erase_guests(
            db_session, user_ids=[guested.guest.user.id], now=clock.utc_now()
        )

        with pytest.raises(HTTPException) as refused:
            await _redeem(
                db_session, test_event, guested, test_event_admin_user, code=p.code
            )

        assert _refused(refused) == (404, "voucher.code_invalid")

    async def test_a_replay_for_an_erased_guest_is_refused(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_event_admin_user: User,
        guested: _Guested,
    ) -> None:
        """As for a member who left: the holder is checked before the replay."""
        p = await _guest_code(db_session, test_event, guested.guest.user.id)
        request_id = uuid.uuid4()
        await _redeem(
            db_session,
            test_event,
            guested,
            test_event_admin_user,
            code=p.code,
            request_id=request_id,
        )
        await erase_guests(
            db_session, user_ids=[guested.guest.user.id], now=clock.utc_now()
        )

        with pytest.raises(HTTPException) as refused:
            await _redeem(
                db_session,
                test_event,
                guested,
                test_event_admin_user,
                code=p.code,
                request_id=request_id,
            )

        assert _refused(refused) == (404, "event.member_not_found")

    async def test_a_guest_with_no_part_left_in_the_event_cannot_redeem(
        self,
        db_session: AsyncSession,
        test_event: Event,
        make_list_guest: ListGuestFactory,
        guested: _Guested,
    ) -> None:
        """A code asked for while a shift was ahead, then the shift given up:
        nothing in the event is theirs any more."""
        upcoming = await _booked(
            db_session,
            guested.task,
            guested.guest.user,
            date=DAY + dt.timedelta(days=1),
        )
        later = await make_list_guest(guested.shared_list, name="Spät")
        booking = Booking(shift_id=upcoming.id, user_id=later.user.id)
        db_session.add(booking)
        await db_session.flush()
        p = await _guest_code(db_session, test_event, later.user.id)
        booking.status = "cancelled"
        db_session.add(booking)
        await db_session.flush()

        with pytest.raises(HTTPException) as refused:
            await _check(db_session, test_event, code=p.code)

        assert _refused(refused) == (404, "event.member_not_found")

    async def test_a_guest_of_another_event_cannot_redeem_here(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_draft_event: Event,
        guested: _Guested,
    ) -> None:
        p = await _guest_code(db_session, test_event, guested.guest.user.id)

        with pytest.raises(HTTPException) as refused:
            await _check(db_session, test_draft_event, code=p.code)

        assert _refused(refused) == (409, "voucher.code_other_event")

    @pytest.mark.parametrize("merged", [False, True])
    async def test_a_code_issued_before_a_confirmation_is_invalid_after_it(
        self,
        merged: bool,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        test_event_admin_user: User,
        guested: _Guested,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """Whoever only typed the address may hold that code: it must never
        spend what the confirmation pools."""
        chain = guested.guest
        if merged:
            account = await make_list_guest(
                guested.shared_list,
                email="gast@example.org",
                shifts=[await _booked(db_session, guested.task, test_user)],
            )
            await confirm_address(db_session, account.guest)
        p = await _guest_code(db_session, test_event, chain.user.id)
        holder = (await confirm_address(db_session, chain.guest)).guest.user_id
        pooled = await vouchers.available_for(
            db_session, test_event.id, holder, now=at(DAY, 20)
        )

        with pytest.raises(HTTPException) as refused:
            await _redeem(
                db_session, test_event, guested, test_event_admin_user, code=p.code
            )

        assert _refused(refused) == (404, "voucher.code_invalid")
        assert pooled == (4 if merged else 2)
        assert (
            await vouchers.available_for(
                db_session, test_event.id, holder, now=at(DAY, 20)
            )
            == pooled
        )

    async def test_check_answers_code_invalid_for_a_pass_deleted_after_its_read(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        test_event: Event,
        guested: _Guested,
    ) -> None:
        """A confirmation deleting the chain's codes commits while the check
        waits in ``hold_pass``: the check must not then name the chain."""
        p = await _guest_code(db_session, test_event, guested.guest.user.id)
        hold = crud_voucher.hold_pass

        async def deleted_first(
            session: AsyncSession, *, pass_id: uuid.UUID, now: dt.datetime
        ) -> bool:
            await session.execute(
                delete(VoucherPass).where(col(VoucherPass.id) == pass_id)
            )
            return await hold(session, pass_id=pass_id, now=now)

        monkeypatch.setattr(crud_voucher, "hold_pass", deleted_first)

        with pytest.raises(HTTPException) as refused:
            await _check(db_session, test_event, code=p.code)

        assert _refused(refused) == (404, "voucher.code_invalid")

    async def test_check_refuses_a_pass_that_changed_hands_after_its_read(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        test_event: Event,
        test_user: User,
        guested: _Guested,
    ) -> None:
        p = await _guest_code(db_session, test_event, guested.guest.user.id)
        hold = crud_voucher.hold_pass

        async def moved_first(
            session: AsyncSession, *, pass_id: uuid.UUID, now: dt.datetime
        ) -> bool:
            await session.execute(
                update(VoucherPass)
                .where(col(VoucherPass.id) == pass_id)
                .values(user_id=test_user.id)
            )
            return await hold(session, pass_id=pass_id, now=now)

        monkeypatch.setattr(crud_voucher, "hold_pass", moved_first)

        with pytest.raises(HTTPException) as refused:
            await _check(db_session, test_event, code=p.code)

        assert _refused(refused) == (409, "voucher.code_expired")

    async def test_a_redemption_retried_after_a_merge_replays(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        test_event_admin_user: User,
        guested: _Guested,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """The entry moved with the chain; the retry finds it under the
        account and answers with the first result, naming the account."""
        account = await make_list_guest(
            guested.shared_list,
            name="Konto Inhaberin",
            email="gast@example.org",
            shifts=[await _booked(db_session, guested.task, test_user)],
        )
        await confirm_address(db_session, account.guest)
        p = await _guest_code(db_session, test_event, guested.guest.user.id)
        request_id = uuid.uuid4()
        first = await _redeem(
            db_session,
            test_event,
            guested,
            test_event_admin_user,
            code=p.code,
            request_id=request_id,
        )
        await confirm_address(db_session, guested.guest.guest)

        again = await _redeem(
            db_session,
            test_event,
            guested,
            test_event_admin_user,
            code=p.code,
            request_id=request_id,
        )

        assert again.replayed
        assert again.entry.id == first.entry.id
        assert (again.user_id, again.name) == (account.user.id, "Konto Inhaberin")
        assert again.available == 3
        entries = await db_session.scalar(
            select(func.count()).where(col(VoucherEntry.user_id) == account.user.id)
        )
        assert entries == 1


# ── Earned is earned, through the API ────────────────────────────


@pytest.mark.asyncio
@pytest.mark.usefixtures("as_event_admin")
class TestEarnedIsEarned:
    """Every change that could take back what an ended shift earned settles
    it first. The wall clock stands at 20:00 on the day of the shifts: the
    08:00-12:00 shift is over, a 19:00-21:00 one is running."""

    @pytest.fixture(autouse=True)
    def _evening(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.logic.clock.wall_clock_now", fixed_clock(at(DAY, 20)))

    async def test_lowering_the_rate_keeps_what_ended_shifts_earned(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        """2 to 0 after two were spent: the ended shift keeps its 2, so the
        balance stays at 0 instead of going below it; the running shift and
        the one still to come count at the new rate."""
        task = await _voucher_task(db_session, test_event, test_user)
        await _booked(db_session, task, test_user)
        await _booked(db_session, task, test_user, start=dt.time(19), end=dt.time(21))
        await _booked(db_session, task, test_user, date=DAY + dt.timedelta(days=1))
        await _entry(db_session, test_event, test_user, -2, kind="redemption")

        r = await async_client.patch(
            f"/api/v1/tasks/{task.id}", json={"vouchers_per_shift": 0}
        )
        assert r.status_code == 200, r.text

        assert await _summary(db_session, test_event, test_user, at(DAY, 20)) == {
            "earned": 2,
            "upcoming": 0,
            "redeemed": 2,
            "adjusted": 0,
            "available": 0,
        }
        later = await _summary(
            db_session, test_event, test_user, at(DAY + dt.timedelta(days=3), 0)
        )
        assert later["earned"] == 2

    async def test_raising_the_rate_from_zero_pays_only_shifts_not_over(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user, per_shift=0)
        ended = await _booked(db_session, task, test_user)
        await _booked(db_session, task, test_user, start=dt.time(19), end=dt.time(21))
        await _booked(db_session, task, test_user, date=DAY + dt.timedelta(days=1))

        r = await async_client.patch(
            f"/api/v1/tasks/{task.id}", json={"vouchers_per_shift": 3}
        )
        assert r.status_code == 200, r.text

        now = await _summary(db_session, test_event, test_user, at(DAY, 20))
        assert (now["earned"], now["upcoming"]) == (0, 6)
        later = await _summary(
            db_session, test_event, test_user, at(DAY + dt.timedelta(days=3), 0)
        )
        assert later["earned"] == 6
        # The ended shift was frozen at 0, so the new rate never reaches it.
        (row,) = await _earning_rows(db_session, task_id=task.id)
        assert (row.shift_id, row.amount) == (ended.id, 0)

    async def test_the_rate_sent_unchanged_settles_nothing(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user)
        await _booked(db_session, task, test_user)

        r = await async_client.patch(
            f"/api/v1/tasks/{task.id}",
            json={"vouchers_per_shift": 2, "description": "Neu"},
        )
        assert r.status_code == 200, r.text
        assert await _earning_rows(db_session, task_id=task.id) == []

    async def test_deleting_a_worked_shift_keeps_its_vouchers_not_its_hours(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        """Hours are a record the organisers keep correcting; vouchers are a
        promise, and may already be spent at a stand."""
        task = await _voucher_task(db_session, test_event, test_user)
        shift = await _booked(db_session, task, test_user)
        title = shift.title

        r = await async_client.delete(f"/api/v1/shifts/{shift.id}")
        assert r.status_code == 204

        acc = await vouchers.account(
            db_session, test_event.id, test_user, now=at(DAY, 20)
        )
        assert acc.summary.earned == 2
        (row,) = acc.shifts
        assert row.settled
        assert (row.shift_id, row.task_id) == (None, task.id)
        assert (row.task_name, row.title, row.date) == ("Theke", title, DAY)
        assert (row.start_time, row.end_time) == (dt.time(8), dt.time(12))
        assert row.ends_at == at(DAY, 10)
        hours = await work_hours.volunteer_hours(
            db_session, test_event.id, test_user, now=at(DAY, 20)
        )
        assert hours.summary.shift_count == 0

    async def test_deleting_the_task_keeps_them_under_its_old_name(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user)
        ended = await _booked(db_session, task, test_user)
        await _booked(db_session, task, test_user, date=DAY + dt.timedelta(days=1))

        r = await async_client.delete(f"/api/v1/tasks/{task.id}")
        assert r.status_code == 204

        acc = await vouchers.account(
            db_session, test_event.id, test_user, now=at(DAY, 20)
        )
        assert (acc.summary.earned, acc.summary.upcoming) == (2, 0)
        (row,) = acc.shifts
        assert (row.task_id, row.shift_id, row.task_name) == (None, None, "Theke")
        # Only the ended shift was frozen; the one to come had earned nothing.
        rows = await _earning_rows(db_session, user_id=test_user.id)
        assert [r.shift_id for r in rows] == [ended.id]

    async def test_deleting_a_batch_keeps_them(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user)
        batch = ShiftBatch(task_id=task.id, start_date=DAY, end_date=DAY)
        db_session.add(batch)
        await db_session.flush()
        await _booked(db_session, task, test_user, batch=batch)

        r = await async_client.delete(f"/api/v1/tasks/{task.id}/batches/{batch.id}")
        assert r.status_code == 204

        summary = await _summary(db_session, test_event, test_user, at(DAY, 20))
        assert summary["earned"] == 2

    async def test_regenerating_away_an_ended_shift_keeps_them(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        """The dry run writes nothing; the real run settles before it deletes."""
        task = await _voucher_task(db_session, test_event, test_user)
        await _booked(db_session, task, test_user)
        payload = {
            "start_date": DAY.isoformat(),
            "end_date": DAY.isoformat(),
            "schedule": {
                "default_start_time": "14:00",
                "default_end_time": "16:00",
                "shift_duration_minutes": 120,
            },
        }
        url = f"/api/v1/tasks/{task.id}/regenerate-shifts"

        r = await async_client.post(f"{url}?dry_run=true", json=payload)
        assert r.status_code == 200, r.text
        assert await _earning_rows(db_session, task_id=task.id) == []

        r = await async_client.post(url, json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["shifts_removed"] == 1
        summary = await _summary(db_session, test_event, test_user, at(DAY, 20))
        assert summary["earned"] == 2

    async def test_moving_an_ended_shift_into_the_future_keeps_them_once(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user)
        shift = await _booked(db_session, task, test_user)

        r = await async_client.patch(
            f"/api/v1/shifts/{shift.id}",
            json={"date": (DAY + dt.timedelta(days=2)).isoformat()},
        )
        assert r.status_code == 200, r.text

        now = await _summary(db_session, test_event, test_user, at(DAY, 20))
        assert (now["earned"], now["upcoming"]) == (2, 0)
        # When it ends again it does not count a second time.
        later = await _summary(
            db_session, test_event, test_user, at(DAY + dt.timedelta(days=4), 0)
        )
        assert later["earned"] == 2

    async def test_moving_the_event_dates_keeps_them(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user)
        await _booked(db_session, task, test_user)

        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/shift-dates",
            json={"new_start_date": "2026-06-24"},
        )
        assert r.status_code == 200, r.text

        now = await _summary(db_session, test_event, test_user, at(DAY, 20))
        assert (now["earned"], now["upcoming"]) == (2, 0)

    async def test_moving_the_task_keeps_them_in_the_source_event(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_draft_event: Event,
        test_user: User,
    ) -> None:
        """Balances and points are per event, and the volunteer may not even be
        in the target: what was earned stays where it was earned, and only the
        shifts still to come go along."""
        task = await _voucher_task(db_session, test_event, test_user)
        await _booked(db_session, task, test_user)
        await _booked(db_session, task, test_user, date=DAY + dt.timedelta(days=1))

        r = await async_client.patch(
            f"/api/v1/tasks/{task.id}", json={"event_id": str(test_draft_event.id)}
        )
        assert r.status_code == 200, r.text

        source = await _summary(db_session, test_event, test_user, at(DAY, 20))
        assert (source["earned"], source["upcoming"]) == (2, 0)
        target = await _summary(db_session, test_draft_event, test_user, at(DAY, 20))
        assert (target["earned"], target["upcoming"]) == (0, 2)
        (row,) = await _earning_rows(db_session, task_id=task.id)
        assert row.event_id == test_event.id

    async def test_deleting_the_tasks_creator_keeps_what_others_earned(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        """``tasks.created_by_id`` cascades: the task and its shifts go with
        the account, but not what volunteers earned on them."""
        creator = User(
            subject="local|voucher-task-creator",
            email="creator.vouchers@example.com",
            name="Creator",
            roles=[],
            is_active=True,
        )
        db_session.add(creator)
        await db_session.flush()
        task = await _voucher_task(db_session, test_event, creator)
        task_id = task.id
        await _booked(db_session, task, test_user)

        with act_as(app, creator):
            r = await async_client.delete("/api/v1/users/me")
        assert r.status_code == 204

        assert await db_session.get(Task, task_id, populate_existing=True) is None
        summary = await _summary(db_session, test_event, test_user, at(DAY, 20))
        assert summary["earned"] == 2
        count = await db_session.execute(
            select(func.count())
            .select_from(VoucherEarning)
            .where(col(VoucherEarning.user_id) == test_user.id)
        )
        assert count.scalar_one() == 1
