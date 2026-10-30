"""How a voucher balance is worked out (``app.logic.vouchers``).

Earned vouchers are derived from bookings every time they are asked for, so
these tests build shifts and bookings directly and pass ``now`` in: what
matters is which bookings count, and from when.
"""

import datetime as dt
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.event_membership import event_membership as crud_membership
from app.crud.voucher import voucher as crud_voucher
from app.logic import vouchers
from app.models.booking import Booking
from app.models.event import Event
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.models.voucher import VoucherEntry, VoucherPass

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
) -> Shift:
    shift = Shift(
        task_id=task.id,
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
        "balance": s.balance,
        "available": s.available,
    }


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


class TestToUtc:
    def test_a_berlin_summer_evening_is_two_hours_earlier_in_utc(self) -> None:
        assert settings.EVENT_TIMEZONE == "Europe/Berlin"
        assert vouchers.to_utc(at(DAY, 18)) == at(DAY, 16)

    def test_follows_the_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "EVENT_TIMEZONE", "Etc/GMT-3")  # UTC+3
        assert vouchers.to_utc(at(DAY, 18)) == at(DAY, 15)


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
            "balance": 2,
            "available": 2,
        }
        assert (
            await vouchers.available_for(
                db_session, test_event.id, test_user.id, now=at(DAY, 20)
            )
            == 2
        )

    async def test_lowering_the_rate_after_spending_goes_negative(
        self, db_session: AsyncSession, test_event: Event, test_user: User
    ) -> None:
        task = await _voucher_task(db_session, test_event, test_user, per_shift=3)
        await _booked(db_session, task, test_user)
        await _entry(db_session, test_event, test_user, -3, kind="redemption")

        task.vouchers_per_shift = 1
        db_session.add(task)
        await db_session.flush()

        summary = await _summary(db_session, test_event, test_user, at(DAY, 20))
        assert summary["balance"] == -2
        assert summary["available"] == 0


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
        assert row.balance == -1
        assert row.available == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("as_event_admin")
async def test_deleting_a_past_shift_lowers_what_was_earned(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_event: Event,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Derived, not stored: an organiser deleting a worked shift takes its
    vouchers back with it, as it takes its hours."""
    monkeypatch.setattr("app.logic.clock.wall_clock_now", lambda: at(DAY, 20))
    task = await _voucher_task(db_session, test_event, test_user)
    shift = await _booked(db_session, task, test_user)
    assert (await _summary(db_session, test_event, test_user, at(DAY, 20)))[
        "earned"
    ] == 2

    r = await async_client.delete(f"/api/v1/shifts/{shift.id}")
    assert r.status_code == 204

    assert (await _summary(db_session, test_event, test_user, at(DAY, 20)))[
        "earned"
    ] == 0


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
