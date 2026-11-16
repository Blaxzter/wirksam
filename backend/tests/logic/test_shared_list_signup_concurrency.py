"""Sign-ups through a shared list racing each other, a pause, and deleting
the event.

Locks only mean something between transactions on separate connections, so
like ``test_invitation_concurrency.py`` these tests do not run on
``db_session``: the setup is committed, each request runs ``signup.sign_up`` in
its own session inside ``session.begin()``, and a ``finally`` block deletes
everything committed, because the test database is shared. The daily
ceilings are switched on, so the production lock order runs in full.
"""

import asyncio
import datetime as dt
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlmodel import col

from app.core.config import settings
from app.crud.shared_list import shared_list as crud_shared_list
from app.logic import clock
from app.logic.booking_capacity import lock_shifts
from app.logic.shared_lists import signup
from app.models.booking import Booking
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shared_list import GuestActivityLog, SharedList
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.public_shared_list import PublicSignupRequest
from tests.fixtures.guest_signups import disable_smtp, freeze_clocks

T = TypeVar("T")

#: How long a transaction holds its locks before it commits.
HOLD = 0.3


@dataclass
class Committed:
    sessions: async_sessionmaker[AsyncSession]
    shared_list: SharedList
    #: One place left.
    last_place: Shift


@pytest_asyncio.fixture
async def committed(
    test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[Committed]:
    freeze_clocks(monkeypatch)
    disable_smtp(monkeypatch)
    monkeypatch.setattr(settings, "TESTING", False)
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    key = uuid.uuid4().hex[:8]
    async with sessions() as setup:
        organiser = User(
            subject=f"local|race-{key}", email=f"race-{key}@example.com", roles=[]
        )
        setup.add(organiser)
        await setup.flush()
        event = Event(
            name=f"Signup race {key}",
            start_date=dt.date(2026, 6, 10),
            end_date=dt.date(2026, 6, 14),
            status="published",
            created_by_id=organiser.id,
        )
        setup.add(event)
        await setup.flush()
        setup.add(
            EventMembership(user_id=organiser.id, event_id=event.id, role="owner")
        )
        task = Task(
            name="Bar",
            start_date=dt.date(2026, 6, 11),
            end_date=dt.date(2026, 6, 11),
            status="published",
            event_id=event.id,
        )
        setup.add(task)
        await setup.flush()
        shift = Shift(
            task_id=task.id,
            title="Bar 10-12",
            date=dt.date(2026, 6, 11),
            start_time=dt.time(10),
            end_time=dt.time(12),
            max_bookings=1,
        )
        setup.add(shift)
        shared_list = await crud_shared_list.create(
            setup,
            event_id=event.id,
            created_by=organiser,
            title="Race",
            intro=None,
            share_note=None,
            ask_email="optional",
            ask_phone="off",
            show_names="none",
            max_per_person=None,
            ends_mode="last_shift",
            ends_on=None,
        )
        await crud_shared_list.set_tasks(
            setup, shared_list_id=shared_list.id, task_ids=[task.id]
        )
        await setup.commit()

    try:
        yield Committed(sessions=sessions, shared_list=shared_list, last_place=shift)
    finally:
        async with test_engine.begin() as conn:
            # By their bookings: a test that deletes the event takes the
            # contact rows with it. Bookings, contact rows and reminders go
            # with the guests.
            guests = select(col(Booking.user_id)).where(
                col(Booking.shared_list_id) == shared_list.id
            )
            await conn.execute(delete(User).where(col(User.id).in_(guests)))
            await conn.execute(
                delete(GuestActivityLog).where(
                    col(GuestActivityLog.shared_list_id) == shared_list.id
                )
            )
            # The list and its links go with the event, the shift with the task.
            await conn.execute(delete(Task).where(col(Task.id) == task.id))
            await conn.execute(delete(Event).where(col(Event.id) == event.id))
            await conn.execute(delete(User).where(col(User.id) == organiser.id))


async def _request(
    c: Committed, call: Callable[[AsyncSession], Awaitable[T]], *, delay: float = 0.0
) -> T:
    await asyncio.sleep(delay)
    async with c.sessions() as session, session.begin():
        return await call(session)


def _sign_up(
    c: Committed, *, email: str | None
) -> Callable[[AsyncSession], Awaitable[Any]]:
    async def call(session: AsyncSession) -> Any:
        return await signup.sign_up(
            session,
            code=c.shared_list.code,
            form=PublicSignupRequest(
                shift_id=c.last_place.id, name="Racer", email=email, show_names="none"
            ),
            now=clock.utc_now(),
        )

    return call


def _codes(results: Sequence[object]) -> list[str]:
    codes: list[str] = []
    for result in results:
        if isinstance(result, HTTPException):
            detail: Any = result.detail
            codes.append(str(detail["code"]))
        else:
            assert not isinstance(result, BaseException), result
            codes.append("ok")
    return sorted(codes)


async def _confirmed(c: Committed) -> int:
    async with c.sessions() as session:
        return (
            await session.scalar(
                select(func.count()).where(
                    col(Booking.shift_id) == c.last_place.id,
                    col(Booking.status) == "confirmed",
                )
            )
        ) or 0


async def test_one_of_many_gets_the_last_place(committed: Committed) -> None:
    results = await asyncio.wait_for(
        asyncio.gather(
            *(
                _request(committed, _sign_up(committed, email=f"r{n}@example.org"))
                for n in range(6)
            ),
            return_exceptions=True,
        ),
        timeout=30,
    )
    assert _codes(results) == ["booking.slot_full"] * 5 + ["ok"]
    assert await _confirmed(committed) == 1


async def test_one_address_twice_at_once_gets_one_place(committed: Committed) -> None:
    async with committed.sessions() as session, session.begin():
        shift = await session.get(Shift, committed.last_place.id)
        assert shift is not None
        shift.max_bookings = 5
    results = await asyncio.wait_for(
        asyncio.gather(
            *(
                _request(committed, _sign_up(committed, email="twin@example.org"))
                for _ in range(2)
            ),
            return_exceptions=True,
        ),
        timeout=30,
    )
    assert _codes(results) == ["ok", "shared_list.already_signed_up"]
    assert await _confirmed(committed) == 1


async def _pause(c: Committed, locked_event: asyncio.Event | None = None) -> int:
    """A pause as the transitions make it: the row ``FOR UPDATE``, then the
    status, held a moment before the commit.

    Returns the confirmed bookings on the shift as the pause sees them once
    it holds the row: whatever a sign-up committed before.
    """
    async with c.sessions() as session, session.begin():
        locked = await crud_shared_list.get_for_update(
            session, shared_list_id=c.shared_list.id
        )
        assert locked is not None
        seen = (
            await session.scalar(
                select(func.count()).where(
                    col(Booking.shift_id) == c.last_place.id,
                    col(Booking.status) == "confirmed",
                )
            )
        ) or 0
        if locked_event is not None:
            locked_event.set()
        locked.status = "paused"
        locked.paused_at = clock.utc_now()
        await session.flush()
        await asyncio.sleep(HOLD)
    return seen


async def test_a_sign_up_after_a_pause_is_refused(committed: Committed) -> None:
    """The sign-up waits for the pause's commit, then reads "paused"."""
    locked = asyncio.Event()
    pause = asyncio.create_task(_pause(committed, locked))
    await locked.wait()
    late = await asyncio.wait_for(
        asyncio.gather(
            _request(committed, _sign_up(committed, email="late@example.org")),
            return_exceptions=True,
        ),
        timeout=30,
    )
    assert await pause == 0
    assert _codes(late) == ["shared_list.paused"]
    assert await _confirmed(committed) == 0


async def test_a_pause_waits_for_a_sign_up_in_flight(
    committed: Committed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sign-up holds the list ``FOR KEY SHARE`` until it commits, so the
    pause's ``FOR UPDATE`` gets the row only once the booking is committed:
    none can be committed after the pause."""
    in_flight = asyncio.Event()

    async def slow_lock(session: AsyncSession, shift_ids: Sequence[uuid.UUID]) -> None:
        await lock_shifts(session, shift_ids)
        in_flight.set()
        await asyncio.sleep(HOLD)

    monkeypatch.setattr(signup, "lock_shifts", slow_lock)

    async def pause() -> int:
        await in_flight.wait()
        return await _pause(committed)

    _, seen = await asyncio.wait_for(
        asyncio.gather(
            _request(committed, _sign_up(committed, email="early@example.org")),
            pause(),
        ),
        timeout=30,
    )

    assert seen == 1
    assert await _confirmed(committed) == 1


async def test_deleting_the_event_waits_for_a_sign_up_in_flight(
    committed: Committed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both take the event row first: the sign-up ``FOR KEY SHARE``, the
    delete before the CASCADE reaches the list the sign-up holds. Taken the
    other way round, the sign-up's insert of the contact row (a foreign key
    to the event) and the delete's CASCADE to the list each waited for the
    other, and one of them died of a deadlock."""
    in_flight = asyncio.Event()

    async def slow_lock(session: AsyncSession, shift_ids: Sequence[uuid.UUID]) -> None:
        await lock_shifts(session, shift_ids)
        in_flight.set()
        await asyncio.sleep(HOLD)

    monkeypatch.setattr(signup, "lock_shifts", slow_lock)

    async def delete_event() -> None:
        await in_flight.wait()
        async with committed.sessions() as session, session.begin():
            await session.execute(
                delete(Event).where(col(Event.id) == committed.shared_list.event_id)
            )

    results = await asyncio.wait_for(
        asyncio.gather(
            _request(committed, _sign_up(committed, email="eve@example.org")),
            delete_event(),
            return_exceptions=True,
        ),
        timeout=30,
    )

    assert _codes(results) == ["ok", "ok"]
    assert await _confirmed(committed) == 1
    async with committed.sessions() as session:
        assert await session.get(SharedList, committed.shared_list.id) is None
