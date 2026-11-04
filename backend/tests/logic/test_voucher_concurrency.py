"""Two stands redeeming against the same balance at the same moment.

The balance is derived, so there is no row to lock; ``logic.vouchers.redeem``
serialises on a transaction-scoped advisory lock per (event, volunteer)
instead. Settling earned vouchers takes no lock at all, because it changes no
total; the cases at the end show a redemption and a settlement racing, and
two organisers changing the same correction (the routes, called directly,
since the stale read they guard against lives there). Proving that it holds
takes two real transactions on two connections,
so unlike the rest of the suite these tests do not run on ``db_session``: the
setup is committed for real, each redemption runs in its own session inside
``session.begin()``, and a ``finally`` block deletes everything that was
committed, because the test database is shared.
"""

import asyncio
import datetime as dt
import uuid
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlmodel import col

from app.api.routes.vouchers import (
    delete_voucher_adjustment,
    update_voucher_adjustment,
)
from app.logic import vouchers
from app.models.booking import Booking
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.models.voucher import VoucherEarning, VoucherEntry, VoucherPass
from app.schemas.voucher import VoucherAdjustmentUpdate, VoucherRedeemResult
from tests.fixtures.clock import fixed_clock

#: After the shift below has ended (event wall clock).
WALL_NOW = dt.datetime(2026, 6, 11, 20, 0)


@dataclass
class Committed:
    sessions: async_sessionmaker[AsyncSession]
    event_id: uuid.UUID
    volunteer: User
    redeemer: User
    point: Task
    work: Task


@pytest_asyncio.fixture
async def committed(test_engine: AsyncEngine) -> AsyncGenerator[Committed]:
    """A volunteer with 3 vouchers earned, a point and a redeemer, committed."""
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    key = uuid.uuid4().hex[:8]
    async with sessions() as setup:
        volunteer = User(
            subject=f"local|race-volunteer-{key}",
            email=f"race-volunteer-{key}@example.com",
            name="Race Volunteer",
            roles=[],
            is_active=True,
        )
        redeemer = User(
            subject=f"local|race-redeemer-{key}",
            email=f"race-redeemer-{key}@example.com",
            name="Race Redeemer",
            roles=[],
            is_active=True,
        )
        setup.add_all([volunteer, redeemer])
        await setup.flush()
        event = Event(
            name=f"Voucher race {key}",
            start_date=dt.date(2026, 6, 10),
            end_date=dt.date(2026, 6, 14),
            created_by_id=redeemer.id,
        )
        setup.add(event)
        await setup.flush()
        setup.add_all(
            [
                EventMembership(user_id=redeemer.id, event_id=event.id, role="owner"),
                EventMembership(user_id=volunteer.id, event_id=event.id, role="member"),
            ]
        )
        work = Task(
            name="Aufbau",
            start_date=dt.date(2026, 6, 11),
            end_date=dt.date(2026, 6, 11),
            status="published",
            created_by_id=redeemer.id,
            event_id=event.id,
            vouchers_per_shift=3,
        )
        point = Task(
            name="Theke",
            start_date=dt.date(2026, 6, 11),
            end_date=dt.date(2026, 6, 11),
            status="published",
            created_by_id=redeemer.id,
            event_id=event.id,
            is_voucher_point=True,
        )
        setup.add_all([work, point])
        await setup.flush()
        shift = Shift(
            task_id=work.id,
            title="Aufbau",
            date=dt.date(2026, 6, 11),
            start_time=dt.time(8),
            end_time=dt.time(12),
            max_bookings=2,
        )
        setup.add(shift)
        await setup.flush()
        setup.add(Booking(shift_id=shift.id, user_id=volunteer.id, status="confirmed"))
        await setup.commit()

    try:
        yield Committed(
            sessions=sessions,
            event_id=event.id,
            volunteer=volunteer,
            redeemer=redeemer,
            point=point,
            work=work,
        )
    finally:
        async with test_engine.begin() as conn:
            await conn.execute(
                delete(VoucherEntry).where(col(VoucherEntry.event_id) == event.id)
            )
            await conn.execute(
                delete(VoucherEarning).where(col(VoucherEarning.event_id) == event.id)
            )
            await conn.execute(
                delete(VoucherPass).where(col(VoucherPass.event_id) == event.id)
            )
            await conn.execute(delete(Booking).where(col(Booking.shift_id) == shift.id))
            await conn.execute(delete(Shift).where(col(Shift.task_id) == work.id))
            await conn.execute(
                delete(Task).where(col(Task.id).in_([work.id, point.id]))
            )
            await conn.execute(
                delete(EventMembership).where(col(EventMembership.event_id) == event.id)
            )
            await conn.execute(delete(Event).where(col(Event.id) == event.id))
            await conn.execute(
                delete(User).where(col(User.id).in_([volunteer.id, redeemer.id]))
            )


async def _redeem(
    c: Committed,
    *,
    amount: int,
    code: str | None = None,
    request_id: uuid.UUID | None = None,
    pause: float = 0.0,
) -> VoucherRedeemResult:
    """One redemption in its own session and transaction, as one request is.

    ``pause`` keeps the transaction open after redeeming, so the other one
    certainly reaches the lock while this one holds it.
    """
    async with c.sessions() as session, session.begin():
        redeemer = await session.get(User, c.redeemer.id)
        point = await session.get(Task, c.point.id)
        assert redeemer is not None and point is not None
        result = await vouchers.redeem(
            session,
            event_id=c.event_id,
            task=point,
            redeemer=redeemer,
            code=code,
            user_id=None if code else c.volunteer.id,
            amount=amount,
            request_id=request_id or uuid.uuid4(),
            wall_now=WALL_NOW,
            utc_now=dt.datetime.now(dt.UTC).replace(tzinfo=None),
        )
        await asyncio.sleep(pause)
        return result


async def _ledger(c: Committed) -> tuple[int, int]:
    """(number of entries, their sum) for the volunteer, as committed."""
    async with c.sessions() as session:
        row = (
            await session.execute(
                select(func.count(), func.coalesce(func.sum(VoucherEntry.amount), 0))
                .select_from(VoucherEntry)
                .where(
                    col(VoucherEntry.event_id) == c.event_id,
                    col(VoucherEntry.user_id) == c.volunteer.id,
                )
            )
        ).one()
    return int(row[0]), int(row[1])


async def _lower_rate(
    c: Committed, *, to: int, delay: float = 0.0, pause: float = 0.0
) -> int:
    """What ``PATCH /tasks/{id}`` does to the rate, in its own transaction:
    settle the work task's ended bookings, then change ``vouchers_per_shift``.
    Returns the earning rows written."""
    await asyncio.sleep(delay)
    async with c.sessions() as session, session.begin():
        written = await vouchers.settle_earnings(
            session, now=WALL_NOW, task_ids=[c.work.id], include_zero=True
        )
        await session.execute(
            update(Task).where(col(Task.id) == c.work.id).values(vouchers_per_shift=to)
        )
        await asyncio.sleep(pause)
        return written


async def _available(c: Committed) -> int:
    async with c.sessions() as session:
        return await vouchers.available_for(
            session, c.event_id, c.volunteer.id, now=WALL_NOW
        )


async def _earning_rows(c: Committed) -> list[tuple[int, uuid.UUID]]:
    async with c.sessions() as session:
        rows = await session.execute(
            select(col(VoucherEarning.amount), col(VoucherEarning.booking_id)).where(
                col(VoucherEarning.event_id) == c.event_id
            )
        )
        return [(int(a), b) for a, b in rows.all()]


async def _delayed_redeem(
    c: Committed, *, amount: int, delay: float
) -> VoucherRedeemResult:
    await asyncio.sleep(delay)
    return await _redeem(c, amount=amount, pause=0.3)


def _split(
    results: Sequence[VoucherRedeemResult | BaseException],
) -> tuple[list[VoucherRedeemResult], list[HTTPException]]:
    ok = [r for r in results if isinstance(r, VoucherRedeemResult)]
    refused = [r for r in results if isinstance(r, HTTPException)]
    unexpected = [
        r for r in results if isinstance(r, BaseException) and r not in refused
    ]
    assert not unexpected, unexpected
    return ok, refused


def _code(exc: HTTPException) -> str:
    detail: Any = exc.detail
    return str(detail["code"])


@pytest.mark.asyncio
async def test_two_stands_cannot_spend_the_same_vouchers(committed: Committed) -> None:
    """3 available, two redemptions of 2 at once: exactly one goes through."""
    results = await asyncio.gather(
        _redeem(committed, amount=2, pause=0.3),
        _redeem(committed, amount=2, pause=0.3),
        return_exceptions=True,
    )

    ok, refused = _split(results)
    assert len(ok) == 1
    assert len(refused) == 1
    assert refused[0].status_code == 409
    assert _code(refused[0]) == "voucher.insufficient"
    assert ok[0].available == 1
    assert await _ledger(committed) == (1, -2)


@pytest.mark.asyncio
async def test_one_code_redeems_once(committed: Committed) -> None:
    """The same code at two stands at once: one redemption, one ``code_used``."""
    async with committed.sessions() as session, session.begin():
        issued = await vouchers.issue_pass(
            session,
            event_id=committed.event_id,
            user_id=committed.volunteer.id,
            now=dt.datetime.now(dt.UTC).replace(tzinfo=None),
        )
        code = issued.code

    results = await asyncio.gather(
        _redeem(committed, amount=1, code=code, pause=0.3),
        _redeem(committed, amount=1, code=code, pause=0.3),
        return_exceptions=True,
    )

    ok, refused = _split(results)
    assert len(ok) == 1
    assert len(refused) == 1
    assert refused[0].status_code == 409
    assert _code(refused[0]) == "voucher.code_used"
    assert await _ledger(committed) == (1, -1)


@pytest.mark.asyncio
async def test_a_retried_manual_redemption_debits_once(committed: Committed) -> None:
    """A redeemer whose response was lost sends the same ``request_id`` again,
    while the first is still in flight: one entry, and both get it back."""
    request_id = uuid.uuid4()
    results = await asyncio.gather(
        _redeem(committed, amount=1, request_id=request_id, pause=0.3),
        _redeem(committed, amount=1, request_id=request_id, pause=0.3),
        return_exceptions=True,
    )

    ok, refused = _split(results)
    assert refused == []
    assert len(ok) == 2
    assert {r.entry.id for r in ok} == {ok[0].entry.id}
    assert sorted(r.replayed for r in ok) == [False, True]
    assert await _ledger(committed) == (1, -1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("redeem_delay", "settle_delay"),
    [
        pytest.param(0.1, 0.0, id="redeem-while-settling"),
        pytest.param(0.0, 0.1, id="settle-while-redeeming"),
        pytest.param(0.6, 0.0, id="redeem-after-settled"),
    ],
)
async def test_redeeming_everything_while_the_rate_is_lowered(
    committed: Committed, redeem_delay: float, settle_delay: float
) -> None:
    """3 earned at 3 per shift. One stand redeems all 3 while an organiser
    lowers the rate to 1. Whichever way they interleave, the redemption reads
    one balance (the derived 3 or the settled 3, never 1 and never 6), so it
    goes through, nothing is left, and the booking has exactly one earning
    row."""
    redeemed, written = await asyncio.gather(
        _delayed_redeem(committed, amount=3, delay=redeem_delay),
        _lower_rate(committed, to=1, delay=settle_delay, pause=0.3),
        return_exceptions=True,
    )

    assert isinstance(redeemed, VoucherRedeemResult), redeemed
    assert redeemed.available == 0
    assert written == 1
    assert await _ledger(committed) == (1, -3)
    assert await _available(committed) == 0
    rows = await _earning_rows(committed)
    assert [amount for amount, _ in rows] == [3]


async def _committed_correction(c: Committed, *, amount: int) -> uuid.UUID:
    async with c.sessions() as session, session.begin():
        entry = VoucherEntry(
            event_id=c.event_id,
            user_id=c.volunteer.id,
            kind="adjustment",
            amount=amount,
            note="Papiermarken",
        )
        session.add(entry)
    return entry.id


async def _edit_correction(
    c: Committed,
    entry_id: uuid.UUID,
    *,
    amount: int | None,
    delay: float = 0.0,
    pause: float = 0.0,
) -> int | None:
    """An organiser's ``PATCH`` (``amount``) or ``DELETE`` (``None``) of a
    correction, as one request: the route in its own session and
    transaction. ``delay`` starts it later, ``pause`` keeps its transaction
    (and so the ledger lock) open afterwards. Returns the stored amount."""
    await asyncio.sleep(delay)
    async with c.sessions() as session, session.begin():
        organiser = await session.get(User, c.redeemer.id)
        assert organiser is not None
        if amount is None:
            await delete_voucher_adjustment(
                event_id=c.event_id,
                entry_id=entry_id,
                session=session,
                current_user=organiser,
            )
            result = None
        else:
            entry = await update_voucher_adjustment(
                event_id=c.event_id,
                entry_id=entry_id,
                body=VoucherAdjustmentUpdate(amount=amount),
                session=session,
                current_user=organiser,
            )
            result = entry.amount
        await asyncio.sleep(pause)
        return result


@pytest.mark.asyncio
async def test_two_organisers_changing_one_correction(
    committed: Committed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """3 earned and a correction of -1: 2 left. One organiser changes it to
    +5 (8 left), while another, who read the -1 before that committed, changes
    it to -5. Checked against the -1 that would take 4; against the +5 now
    stored it takes 10, more than the 8 left, so the second is refused and
    the balance never goes below zero."""
    monkeypatch.setattr("app.logic.clock.wall_clock_now", fixed_clock(WALL_NOW))
    entry_id = await _committed_correction(committed, amount=-1)

    results = await asyncio.gather(
        _edit_correction(committed, entry_id, amount=5, pause=0.3),
        _edit_correction(committed, entry_id, amount=-5, delay=0.1),
        return_exceptions=True,
    )

    assert results[0] == 5, results
    refused = results[1]
    assert isinstance(refused, HTTPException), refused
    assert refused.status_code == 409
    assert _code(refused) == "voucher.correction_exceeds_available"
    assert await _ledger(committed) == (1, 5)
    assert await _available(committed) == 8


@pytest.mark.asyncio
async def test_changing_a_correction_another_organiser_deleted(
    committed: Committed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One organiser deletes a correction while another, who read it before
    that committed, changes it: the change finds it gone (404), rather than
    updating a row that no longer exists."""
    monkeypatch.setattr("app.logic.clock.wall_clock_now", fixed_clock(WALL_NOW))
    entry_id = await _committed_correction(committed, amount=-1)

    results = await asyncio.gather(
        _edit_correction(committed, entry_id, amount=None, pause=0.3),
        _edit_correction(committed, entry_id, amount=-2, delay=0.1),
        return_exceptions=True,
    )

    assert results[0] is None, results
    gone = results[1]
    assert isinstance(gone, HTTPException), gone
    assert gone.status_code == 404
    assert _code(gone) == "voucher.entry_not_found"
    assert await _ledger(committed) == (0, 0)
    assert await _available(committed) == 3


@pytest.mark.asyncio
async def test_two_settlements_at_once_write_one_row(committed: Committed) -> None:
    """Two organisers changing the rate at the same moment: the second insert
    waits on the unique booking id and then does nothing."""
    results = await asyncio.gather(
        _lower_rate(committed, to=2, pause=0.3),
        _lower_rate(committed, to=1, pause=0.3),
        return_exceptions=True,
    )

    written = [r for r in results if isinstance(r, int)]
    assert sorted(written) == [0, 1], results
    rows = await _earning_rows(committed)
    assert [amount for amount, _ in rows] == [3]
    assert await _available(committed) == 3
