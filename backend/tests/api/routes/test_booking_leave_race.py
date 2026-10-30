"""Booking a shift while leaving the event, at the same moment.

Leaving cancels the person's unfinished bookings
(``crud_booking.cancel_unfinished_bookings_in_event``). A booking that checked
membership but had not been inserted yet when the leave ran its clean-up would
survive it: a former member on a future rota, earning hours and vouchers.
``POST /bookings/`` therefore holds the caller's membership row ``FOR KEY
SHARE`` until it commits, as putting someone in charge of a task does.

Proving that takes two real transactions on two connections, so, like
``tests/logic/test_voucher_concurrency.py``, these tests do not run on
``db_session``: the setup is committed for real, each request runs in its own
session inside a transaction, and a ``finally`` block deletes everything that
was committed, because the test database is shared. The route functions are
called directly with those sessions.
"""

import asyncio
import datetime as dt
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlmodel import col

from app.api.routes.bookings import create_booking
from app.api.routes.events import remove_member
from app.models.booking import Booking
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.booking import BookingCreate
from tests.fixtures.clock import set_wall_clock

#: Long enough for the other transaction to reach the lock and wait on it.
SETTLE = 0.5


@dataclass
class Committed:
    sessions: async_sessionmaker[AsyncSession]
    event_id: uuid.UUID
    member_id: uuid.UUID
    shift_id: uuid.UUID


@pytest_asyncio.fixture
async def committed(
    test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[Committed]:
    """A member of an event with a free place on next week's shift, committed."""
    set_wall_clock(monkeypatch, dt.datetime(2026, 6, 1, 8, 0))
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    key = uuid.uuid4().hex[:8]
    async with sessions() as setup:
        owner = User(
            subject=f"local|leave-race-owner-{key}",
            email=f"leave-race-owner-{key}@example.com",
            name="Race Owner",
            roles=[],
            is_active=True,
        )
        member = User(
            subject=f"local|leave-race-member-{key}",
            email=f"leave-race-member-{key}@example.com",
            name="Race Member",
            roles=[],
            is_active=True,
        )
        setup.add_all([owner, member])
        await setup.flush()
        event = Event(
            name=f"Leave race {key}",
            start_date=dt.date(2026, 6, 10),
            end_date=dt.date(2026, 6, 14),
            created_by_id=owner.id,
        )
        setup.add(event)
        await setup.flush()
        setup.add_all(
            [
                EventMembership(user_id=owner.id, event_id=event.id, role="owner"),
                EventMembership(user_id=member.id, event_id=event.id, role="member"),
            ]
        )
        task = Task(
            name="Theke",
            start_date=dt.date(2026, 6, 12),
            end_date=dt.date(2026, 6, 12),
            status="published",
            created_by_id=owner.id,
            event_id=event.id,
        )
        setup.add(task)
        await setup.flush()
        shift = Shift(
            task_id=task.id,
            title="Theke",
            date=dt.date(2026, 6, 12),
            start_time=dt.time(18),
            end_time=dt.time(22),
            max_bookings=4,
        )
        setup.add(shift)
        await setup.commit()

    try:
        yield Committed(
            sessions=sessions,
            event_id=event.id,
            member_id=member.id,
            shift_id=shift.id,
        )
    finally:
        async with test_engine.begin() as conn:
            await conn.execute(delete(Booking).where(col(Booking.shift_id) == shift.id))
            await conn.execute(delete(Shift).where(col(Shift.id) == shift.id))
            await conn.execute(delete(Task).where(col(Task.id) == task.id))
            await conn.execute(
                delete(EventMembership).where(col(EventMembership.event_id) == event.id)
            )
            await conn.execute(delete(Event).where(col(Event.id) == event.id))
            await conn.execute(
                delete(User).where(col(User.id).in_([owner.id, member.id]))
            )


async def _member(session: AsyncSession, c: Committed) -> User:
    user = await session.get(User, c.member_id)
    assert user is not None
    return user


async def _book(session: AsyncSession, c: Committed) -> None:
    await create_booking(
        BookingCreate(shift_id=c.shift_id),
        session,
        await _member(session, c),
        BackgroundTasks(),
    )


async def _leave(session: AsyncSession, c: Committed) -> None:
    await remove_member(c.event_id, c.member_id, session, await _member(session, c))


async def _booking_status(c: Committed) -> str | None:
    async with c.sessions() as session:
        return await session.scalar(
            select(col(Booking.status)).where(
                col(Booking.shift_id) == c.shift_id,
                col(Booking.user_id) == c.member_id,
            )
        )


async def _in_own_transaction(c: Committed, step: Any) -> None:
    async with c.sessions() as session, session.begin():
        await step(session, c)


def _code(exc: HTTPException) -> str:
    detail: Any = exc.detail
    return str(detail["code"])


@pytest.mark.asyncio
async def test_a_leave_waits_for_a_booking_in_flight(committed: Committed) -> None:
    """The booking holds the membership row, so the leave's DELETE waits for
    it, and the leave's clean-up then sees the booking and cancels it."""
    async with committed.sessions() as booking:
        await booking.begin()
        await _book(booking, committed)

        leave = asyncio.create_task(_in_own_transaction(committed, _leave))
        await asyncio.sleep(SETTLE)
        assert not leave.done(), "the leave did not wait for the booking"
        await booking.commit()

    await asyncio.wait_for(leave, timeout=10)
    assert await _booking_status(committed) == "cancelled"


@pytest.mark.asyncio
async def test_a_booking_waits_for_a_leave_in_flight_and_is_refused(
    committed: Committed,
) -> None:
    """The other way round: the leave has deleted the row but not committed.
    The booking still reads the membership, then waits on the row lock, and
    once the leave commits the row is gone and the booking refused."""
    async with committed.sessions() as leaving:
        await leaving.begin()
        await _leave(leaving, committed)

        book = asyncio.create_task(_in_own_transaction(committed, _book))
        await asyncio.sleep(SETTLE)
        assert not book.done(), "the booking did not wait for the leave"
        await leaving.commit()

    with pytest.raises(HTTPException) as refused:
        await asyncio.wait_for(book, timeout=10)
    assert refused.value.status_code == 403
    assert _code(refused.value) == "event.forbidden"
    assert await _booking_status(committed) is None
