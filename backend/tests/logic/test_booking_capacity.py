"""``logic.booking_capacity.lock_shifts``: bookings of one shift take turns.

Advisory locks only mean something between two transactions on two
connections, so like ``test_voucher_concurrency.py`` these tests do not run on
``db_session``: each "request" gets its own session on ``test_engine``. The
locks are keyed by shift id and need no rows, so nothing is committed that
would have to be cleaned up.
"""

import asyncio
import uuid
from collections.abc import Sequence

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.logic.booking_capacity import lock_shifts

pytestmark = pytest.mark.asyncio

#: How long a transaction holds its locks before committing.
HOLD = 0.3


async def _lock_and_hold(
    sessions: async_sessionmaker[AsyncSession],
    shift_ids: Sequence[uuid.UUID],
    order: list[str],
    name: str,
) -> None:
    async with sessions() as session, session.begin():
        await lock_shifts(session, shift_ids)
        order.append(f"{name} locked")
        await asyncio.sleep(HOLD)
        order.append(f"{name} commits")


async def test_a_second_booking_of_the_shift_waits_for_the_first(
    test_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    shift_id = uuid.uuid4()
    order: list[str] = []

    first = asyncio.create_task(_lock_and_hold(sessions, [shift_id], order, "first"))
    while not order:
        await asyncio.sleep(0.01)
    await asyncio.wait_for(
        asyncio.gather(first, _lock_and_hold(sessions, [shift_id], order, "second")),
        timeout=10,
    )

    assert order == ["first locked", "first commits", "second locked", "second commits"]


async def test_other_shifts_do_not_wait(test_engine: AsyncEngine) -> None:
    """Both hold their lock until the other holds one too, which only works
    if neither waits for the other. Not a race on the clock: opening a
    connection can take longer than any hold time."""
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    both_locked = asyncio.Barrier(2)

    async def lock_and_meet() -> None:
        async with sessions() as session, session.begin():
            await lock_shifts(session, [uuid.uuid4()])
            await both_locked.wait()

    await asyncio.wait_for(asyncio.gather(lock_and_meet(), lock_and_meet()), timeout=10)


async def test_overlapping_shifts_in_any_order_cannot_deadlock(
    test_engine: AsyncEngine,
) -> None:
    """Both lock in sorted order, so whoever gets the first shift gets both.
    Taken as given, one would hold ``a``, the other ``b``, and PostgreSQL would
    abort one of them as a deadlock."""
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    a, b = sorted([uuid.uuid4(), uuid.uuid4()])
    order: list[str] = []

    await asyncio.wait_for(
        asyncio.gather(
            _lock_and_hold(sessions, [a, b], order, "one"),
            _lock_and_hold(sessions, [b, a, b], order, "two"),
        ),
        timeout=10,
    )

    assert len(order) == 4
    first = order[0].split()[0]
    assert order[:2] == [f"{first} locked", f"{first} commits"]
