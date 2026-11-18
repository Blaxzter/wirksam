"""Organisers changing shared lists at the same moment as each other.

Two orders of locks are pinned here, each against the deadlock or the lost
emergency stop that the other order allowed:

- a removal reserves each guest's mail under the address's lock, so two
  removals take the addresses in the order of their hashes;
- every change to a list takes the event row before the list's, as the
  emergency stop does, so a person in charge cannot reopen a list beside a
  stop that locks them out.

Like ``test_shared_list_signup_concurrency.py`` these do not run on
``db_session``: the setup is committed, each request runs in its own session
inside ``session.begin()``, and a ``finally`` block deletes everything
committed, because the test database is shared.
"""

import asyncio
import datetime as dt
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlmodel import col

from app.api.routes.shared_lists import bulk_update_shared_lists, resume_shared_list
from app.crud.shared_list import shared_list as crud_shared_list
from app.crud.shared_list_guest import shared_list_guest as crud_guest
from app.logic import clock
from app.logic.shared_lists import guest_quota, manage
from app.logic.shared_lists.removal import remove_signups
from app.models.booking import Booking
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shared_list import GuestActivityLog, SharedList
from app.models.shift import Shift
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from app.schemas.shared_list import SharedListBulkRequest
from app.schemas.shared_list_guest import SharedListSignupRemoveRequest
from tests.fixtures.guest_signups import configure_smtp, freeze_clocks

T = TypeVar("T")

#: How long a transaction holds its locks before it goes on.
HOLD = 0.3


@dataclass
class Committed:
    sessions: async_sessionmaker[AsyncSession]
    event_id: uuid.UUID
    organiser_id: uuid.UUID
    #: In charge of the task, and so of every list made of it here.
    manager_id: uuid.UUID
    task_id: uuid.UUID
    shift_id: uuid.UUID


@pytest_asyncio.fixture
async def committed(
    test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[Committed]:
    freeze_clocks(monkeypatch)
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    key = uuid.uuid4().hex[:8]
    async with sessions() as setup:
        organiser, manager = (
            User(
                subject=f"local|{role}-{key}",
                email=f"{role}-{key}@example.com",
                roles=[],
            )
            for role in ("organiser", "manager")
        )
        setup.add_all([organiser, manager])
        await setup.flush()
        event = Event(
            name=f"Change race {key}",
            start_date=dt.date(2026, 6, 10),
            end_date=dt.date(2026, 6, 14),
            status="published",
            created_by_id=organiser.id,
        )
        setup.add(event)
        await setup.flush()
        setup.add_all(
            [
                EventMembership(user_id=organiser.id, event_id=event.id, role="owner"),
                EventMembership(user_id=manager.id, event_id=event.id, role="member"),
            ]
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
        setup.add(TaskManager(task_id=task.id, user_id=manager.id))
        shift = Shift(
            task_id=task.id,
            title="Bar 10-12",
            date=dt.date(2026, 6, 11),
            start_time=dt.time(10),
            end_time=dt.time(12),
            max_bookings=10,
        )
        setup.add(shift)
        await setup.commit()

    try:
        yield Committed(
            sessions=sessions,
            event_id=event.id,
            organiser_id=organiser.id,
            manager_id=manager.id,
            task_id=task.id,
            shift_id=shift.id,
        )
    finally:
        async with test_engine.begin() as conn:
            # Bookings, contact rows and reminders go with the guests.
            await conn.execute(
                delete(User).where(
                    col(User.id).in_(
                        select(col(Booking.user_id)).where(
                            col(Booking.shift_id) == shift.id
                        )
                    )
                )
            )
            await conn.execute(
                delete(GuestActivityLog).where(
                    col(GuestActivityLog.event_id) == event.id
                )
            )
            # The lists go with the event, the shift with the task.
            await conn.execute(delete(Task).where(col(Task.id) == task.id))
            await conn.execute(delete(Event).where(col(Event.id) == event.id))
            await conn.execute(
                delete(User).where(col(User.id).in_([organiser.id, manager.id]))
            )


async def _in_own_transaction(
    c: Committed, call: Callable[[AsyncSession], Awaitable[T]]
) -> T:
    async with c.sessions() as session, session.begin():
        return await call(session)


async def _list(c: Committed, *, status: str) -> uuid.UUID:
    """A list of the task, made by the person in charge."""

    async def make(session: AsyncSession) -> uuid.UUID:
        manager = await session.get(User, c.manager_id)
        assert manager is not None
        shared_list = await crud_shared_list.create(
            session,
            event_id=c.event_id,
            created_by=manager,
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
            session, shared_list_id=shared_list.id, task_ids=[c.task_id]
        )
        shared_list.status = status
        return shared_list.id

    return await _in_own_transaction(c, make)


async def _status(c: Committed, list_id: uuid.UUID) -> str:
    async with c.sessions() as session:
        shared_list = await session.get(SharedList, list_id)
        assert shared_list is not None
        return shared_list.status


def _outcome(result: object) -> str:
    if isinstance(result, HTTPException):
        detail: Any = result.detail
        return str(detail["code"])
    assert not isinstance(result, BaseException), result
    return "ok"


# ── Removal ───────────────────────────────────────────────────────


async def _guests(
    c: Committed, list_id: uuid.UUID, addresses: list[str]
) -> list[uuid.UUID]:
    """One chain per address, each on the shift; their booking ids."""

    async def make(session: AsyncSession) -> list[uuid.UUID]:
        shared_list = await session.get(SharedList, list_id)
        assert shared_list is not None
        bookings: list[Booking] = []
        for address in addresses:
            guest = await crud_guest.create(
                session,
                shared_list=shared_list,
                name="Gast",
                email=address,
                phone=None,
                language="de",
                now=clock.utc_now(),
            )
            bookings.append(
                Booking(
                    shift_id=c.shift_id,
                    user_id=guest.user_id,
                    status="confirmed",
                    shared_list_id=list_id,
                )
            )
        session.add_all(bookings)
        await session.flush()
        return [booking.id for booking in bookings]

    return await _in_own_transaction(c, make)


async def test_two_removals_take_shared_addresses_in_one_order(
    committed: Committed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anyone can type an address, so chains share them: here the first
    request names A then B, the second B then A. Each mail holds its
    address's lock until commit; taken in the order the bookings were named,
    each request held one address and waited for the other's."""
    configure_smtp(monkeypatch)
    list_id = await _list(committed, status="live")
    a, b = "a@example.org", "b@example.org"
    g1, g2, g3, g4 = await _guests(committed, list_id, [a, b, b, a])
    reserve = guest_quota.reserve_mail

    async def slow_reserve(session: AsyncSession, **kwargs: Any) -> bool:
        reserved = await reserve(session, **kwargs)
        await asyncio.sleep(HOLD)
        return reserved

    monkeypatch.setattr(guest_quota, "reserve_mail", slow_reserve)

    def remove(
        booking_ids: list[uuid.UUID],
    ) -> Callable[[AsyncSession], Awaitable[Any]]:
        async def call(session: AsyncSession) -> Any:
            organiser = await session.get(User, committed.organiser_id)
            shared_list = await session.get(SharedList, list_id)
            event = await session.get(Event, committed.event_id)
            assert organiser and shared_list and event
            return await remove_signups(
                session,
                user=organiser,
                shared_list=shared_list,
                event=event,
                access="admin",
                request=SharedListSignupRemoveRequest(booking_ids=booking_ids),
                now=clock.utc_now(),
                now_wall=clock.wall_clock_now(event.timezone),
            )

        return call

    results = await asyncio.wait_for(
        asyncio.gather(
            _in_own_transaction(committed, remove([g1, g2])),
            _in_own_transaction(committed, remove([g3, g4])),
            return_exceptions=True,
        ),
        timeout=30,
    )

    assert [_outcome(r) for r in results] == ["ok", "ok"]
    async with committed.sessions() as session:
        mails = await session.scalar(
            select(func.count()).where(
                col(GuestActivityLog.kind) == "removed",
                col(GuestActivityLog.event_id) == committed.event_id,
            )
        )
    assert mails == 4


# ── An emergency stop and a person in charge ──────────────────────


async def _stop_and_hold(c: Committed, stopped: asyncio.Event) -> None:
    """``pause-all`` with ``lock_managers``, held a moment before the commit."""
    async with c.sessions() as session, session.begin():
        event = await session.get(Event, c.event_id)
        assert event is not None
        await manage.pause_all(
            session, event=event, now_utc=clock.utc_now(), lock_managers=True
        )
        stopped.set()
        await asyncio.sleep(HOLD)


async def test_a_person_in_charge_cannot_reopen_a_list_beside_the_stop(
    committed: Committed,
) -> None:
    """The list was paused already, so the stop does not lock its row. The
    resume waits for the event row the stop holds, then reads the switch it
    turned off."""
    list_id = await _list(committed, status="paused")
    stopped = asyncio.Event()

    async def resume(session: AsyncSession) -> Any:
        manager = await session.get(User, committed.manager_id)
        assert manager is not None
        return await resume_shared_list(list_id, session, manager)

    async def resume_after_the_stop() -> Any:
        await stopped.wait()
        return await _in_own_transaction(committed, resume)

    _, resumed = await asyncio.wait_for(
        asyncio.gather(
            _stop_and_hold(committed, stopped),
            resume_after_the_stop(),
            return_exceptions=True,
        ),
        timeout=30,
    )

    assert _outcome(resumed) == "shared_list.managers_disabled"
    assert await _status(committed, list_id) == "paused"


async def test_nor_in_a_batch(committed: Committed) -> None:
    """The batch had read the event before it waited for the lists, and kept
    reading that copy."""
    list_id = await _list(committed, status="paused")
    stopped = asyncio.Event()

    async def resume(session: AsyncSession) -> Any:
        manager = await session.get(User, committed.manager_id)
        assert manager is not None
        return await bulk_update_shared_lists(
            committed.event_id,
            SharedListBulkRequest(action="resume", list_ids=[list_id]),
            session,
            manager,
        )

    async def resume_after_the_stop() -> Any:
        await stopped.wait()
        return await _in_own_transaction(committed, resume)

    _, result = await asyncio.wait_for(
        asyncio.gather(
            _stop_and_hold(committed, stopped),
            resume_after_the_stop(),
        ),
        timeout=30,
    )

    assert result.changed == []
    assert [(s.id, s.code) for s in result.skipped] == [
        (list_id, "shared_list.managers_disabled")
    ]
    assert await _status(committed, list_id) == "paused"


async def test_editing_a_live_list_beside_the_stop_waits_and_does_not_deadlock(
    committed: Committed,
) -> None:
    """The stop holds the event and then the list; a change takes them in
    the same order, so it waits rather than holding the list while it waits
    for the event."""
    list_id = await _list(committed, status="live")
    stopped = asyncio.Event()

    async def lock_and_read(session: AsyncSession) -> tuple[str, bool]:
        shared_list = await manage.lock_for_change(session, list_id)
        event = await session.get(Event, committed.event_id)
        assert shared_list is not None and event is not None
        return shared_list.status, event.managers_share_lists

    async def change_after_the_stop() -> tuple[str, bool]:
        await stopped.wait()
        return await _in_own_transaction(committed, lock_and_read)

    _, seen = await asyncio.wait_for(
        asyncio.gather(
            _stop_and_hold(committed, stopped),
            change_after_the_stop(),
        ),
        timeout=30,
    )

    assert seen == ("paused", False)
