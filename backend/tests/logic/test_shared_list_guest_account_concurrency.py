"""Confirming a guest's address beside everything else that touches the same
rows: another confirmation, a sign-up continuing the chain, an organiser's
removal, deleting the event, erasing the account or the chain, the retention
sweep, a change that settles earnings, a correction, and the reminder poller.

Locks only mean something between transactions on separate connections, so
like ``test_shared_list_signup_concurrency.py`` these tests do not run on
``db_session``: the setup is committed, each request runs in its own session
inside ``session.begin()``, and a ``finally`` block deletes everything
committed, because the test database is shared. The daily ceilings are
switched on, so the production lock order runs in full. Both clocks stand
at 1 June 2026: the shift on 20 May has ended and earned, the June ones are
ahead.
"""

import asyncio
import datetime as dt
import uuid
from collections.abc import AsyncGenerator, Awaitable, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlmodel import col

from app.api.routes.shared_list_guests import erase_list_guest
from app.api.routes.vouchers import create_voucher_adjustment
from app.core.config import settings
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.crud.shared_list import shared_list as crud_shared_list
from app.crud.shared_list_guest import shared_list_guest as crud_guest
from app.logic import clock, vouchers
from app.logic.notifications import reminder_poller
from app.logic.shared_lists import (
    guest_account,
    guest_mail,
    guest_quota,
    guest_tokens,
    retention,
    signup,
)
from app.logic.shared_lists.erase import erase_guests
from app.logic.shared_lists.guest_mail import GUEST_REMINDER
from app.logic.shared_lists.guest_tokens import GuestKey
from app.logic.shared_lists.removal import remove_signups
from app.models.booking import Booking
from app.models.booking_reminder import BookingReminder
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shared_list import (
    GuestActivityLog,
    SharedList,
    SharedListGuest,
    SharedListGuestAlias,
)
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.models.voucher import VoucherEarning, VoucherEntry
from app.schemas.public_shared_list import PublicSignupRequest
from app.schemas.shared_list_guest import SharedListSignupRemoveRequest
from app.schemas.voucher import VoucherAdjustmentCreate
from tests.fixtures.guest_signups import (
    configure_smtp,
    confirm_address,
    disable_smtp,
    freeze_clocks,
)

T = TypeVar("T")

#: How long a transaction holds its locks before it commits.
HOLD = 0.3
ADDRESS = "family@example.org"
#: When the retention sweep runs: 30 days after the shift on 20 May are over,
#: those after the June ones are not.
SWEPT_AT = dt.datetime(2026, 6, 25, 3, 0)


@dataclass
class World:
    sessions: async_sessionmaker[AsyncSession]
    organiser_id: uuid.UUID
    event_id: uuid.UUID
    list_id: uuid.UUID
    list_code: str
    #: Earns 2 a shift.
    bar_id: uuid.UUID
    #: Earns nothing.
    cloakroom_id: uuid.UUID
    #: 20 May, over.
    ended: uuid.UUID
    #: 11, 12 and 13 June on the bar.
    ahead: list[uuid.UUID]
    #: 11 June in the cloakroom.
    cloakroom: uuid.UUID
    #: Every guest user made here, for the clean-up.
    guests: list[uuid.UUID] = field(default_factory=list)


async def _shift(
    session: AsyncSession, task: Task, day: dt.date, start: int = 10
) -> uuid.UUID:
    shift = Shift(
        task_id=task.id,
        title=f"{task.name} {day}",
        date=day,
        start_time=dt.time(start),
        end_time=dt.time(start + 2),
        max_bookings=5,
    )
    session.add(shift)
    await session.flush()
    return shift.id


@pytest_asyncio.fixture
async def world(
    test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[World]:
    freeze_clocks(monkeypatch)
    disable_smtp(monkeypatch)
    monkeypatch.setattr(settings, "TESTING", False)
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    key = uuid.uuid4().hex[:8]
    async with sessions() as setup:
        organiser = User(
            subject=f"local|account-race-{key}",
            email=f"account-race-{key}@example.com",
            name="Olga",
            roles=[],
        )
        setup.add(organiser)
        await setup.flush()
        event = Event(
            name=f"Account race {key}",
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
        bar = Task(
            name="Bar",
            start_date=dt.date(2026, 5, 20),
            end_date=dt.date(2026, 6, 13),
            status="published",
            event_id=event.id,
            vouchers_per_shift=2,
        )
        cloakroom = Task(
            name="Garderobe",
            start_date=dt.date(2026, 6, 11),
            end_date=dt.date(2026, 6, 11),
            status="published",
            event_id=event.id,
        )
        setup.add_all([bar, cloakroom])
        await setup.flush()
        ended = await _shift(setup, bar, dt.date(2026, 5, 20))
        ahead = [
            await _shift(setup, bar, dt.date(2026, 6, day)) for day in (11, 12, 13)
        ]
        coats = await _shift(setup, cloakroom, dt.date(2026, 6, 11), start=14)
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
            setup, shared_list_id=shared_list.id, task_ids=[bar.id, cloakroom.id]
        )
        await setup.commit()

    w = World(
        sessions=sessions,
        organiser_id=organiser.id,
        event_id=event.id,
        list_id=shared_list.id,
        list_code=shared_list.code,
        bar_id=bar.id,
        cloakroom_id=cloakroom.id,
        ended=ended,
        ahead=ahead,
        cloakroom=coats,
    )
    try:
        yield w
    finally:
        async with test_engine.begin() as conn:
            # Everyone booked here, the sign-ups' own guests included; their
            # contact rows, aliases, bookings, reminders and voucher rows go
            # with them.
            booked = select(col(Booking.user_id)).where(
                col(Booking.shift_id).in_([ended, *ahead, coats])
            )
            await conn.execute(
                delete(User).where(
                    col(User.is_list_guest),
                    col(User.id).in_(booked) | col(User.id).in_(w.guests),
                )
            )
            await conn.execute(
                delete(GuestActivityLog).where(
                    col(GuestActivityLog.event_id) == event.id
                )
            )
            await conn.execute(
                delete(Task).where(col(Task.id).in_([bar.id, cloakroom.id]))
            )
            await conn.execute(delete(Event).where(col(Event.id) == event.id))
            await conn.execute(delete(User).where(col(User.id) == organiser.id))


async def _chain(
    w: World, *, name: str, shifts: Sequence[uuid.UUID], email: str | None = ADDRESS
) -> SharedListGuest:
    """A committed sign-up chain booked on ``shifts``."""
    async with w.sessions() as session, session.begin():
        shared_list = await session.get(SharedList, w.list_id)
        assert shared_list is not None
        guest = await crud_guest.create(
            session,
            shared_list=shared_list,
            name=name,
            email=email,
            phone=None,
            language="de",
            now=clock.utc_now(),
        )
        session.add_all(
            Booking(
                shift_id=shift_id,
                user_id=guest.user_id,
                status="confirmed",
                shared_list_id=w.list_id,
                guest_name=name,
            )
            for shift_id in shifts
        )
    w.guests.append(guest.user_id)
    return guest


async def _confirm(
    w: World,
    guest: SharedListGuest,
    *,
    done: asyncio.Event | None = None,
    hold: float = 0.0,
) -> GuestKey:
    """Press "Ja, das bin ich" in a request of its own; ``done`` is set once it has
    confirmed, while it still holds its locks for ``hold`` seconds."""
    async with w.sessions() as session, session.begin():
        key = await confirm_address(session, guest)
        if done is not None:
            done.set()
        await asyncio.sleep(hold)
        return key


async def _after(signal: asyncio.Event, call: Awaitable[T]) -> T:
    await signal.wait()
    return await call


async def _both(*calls: Awaitable[Any]) -> list[Any]:
    return await asyncio.wait_for(
        asyncio.gather(*calls, return_exceptions=True), timeout=30
    )


def _problem(result: object) -> tuple[int, str]:
    assert isinstance(result, HTTPException), result
    detail: Any = result.detail
    return result.status_code, str(detail["code"])


async def _scalar(w: World, query: Any) -> Any:
    async with w.sessions() as session:
        return await session.scalar(query)


async def _owners(
    w: World,
    model: type[Booking] | type[VoucherEarning] | type[VoucherEntry],
    **where: Any,
) -> list[uuid.UUID]:
    async with w.sessions() as session:
        query = select(col(model.user_id))
        for name, value in where.items():
            query = query.where(getattr(model, name) == value)
        return list((await session.execute(query)).scalars())


async def _accounts(w: World) -> list[uuid.UUID]:
    async with w.sessions() as session:
        rows = await session.execute(
            select(col(SharedListGuest.user_id)).where(
                col(SharedListGuest.event_id) == w.event_id,
                col(SharedListGuest.confirmed_at).is_not(None),
                func.lower(col(SharedListGuest.email)) == ADDRESS,
            )
        )
        return list(rows.scalars())


async def _slow_account_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hold the address's account lock a moment, so a second confirmation of
    the address certainly waits for it."""
    lock = guest_quota.lock_account

    async def slow(session: AsyncSession, event_id: uuid.UUID, hashed: str) -> None:
        await lock(session, event_id, hashed)
        await asyncio.sleep(HOLD)

    monkeypatch.setattr(guest_account.guest_quota, "lock_account", slow)


# ── Confirmations ─────────────────────────────────────────────────


async def test_two_chains_of_one_address_make_one_account(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _slow_account_lock(monkeypatch)
    maria = await _chain(world, name="Maria", shifts=[world.ahead[0]])
    tom = await _chain(world, name="Tom", shifts=[world.ahead[1]])

    keys = await _both(_confirm(world, maria), _confirm(world, tom))

    assert all(isinstance(key, GuestKey) for key in keys), keys
    [account] = await _accounts(world)
    assert {key.guest.user_id for key in keys} == {account}
    assert await _scalar(world, select(func.count(col(SharedListGuestAlias.id)))) == 1
    assert await _owners(world, Booking, shared_list_id=world.list_id) == [
        account,
        account,
    ]


@pytest.mark.parametrize("merges", [False, True])
async def test_the_same_link_twice_at_once_confirms_once(
    merges: bool, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A double click, or two tabs: both answer with the same account."""
    if merges:
        first = await _chain(world, name="Maria", shifts=[world.ahead[0]])
        await _confirm(world, first)
    await _slow_account_lock(monkeypatch)
    chain = await _chain(world, name="Tom", shifts=[world.ahead[1]])

    keys = await _both(_confirm(world, chain), _confirm(world, chain))

    assert all(isinstance(key, GuestKey) for key in keys), keys
    [account] = await _accounts(world)
    assert [key.guest.user_id for key in keys] == [account, account]
    aliases = await _scalar(world, select(func.count(col(SharedListGuestAlias.id))))
    assert aliases == (1 if merges else 0)


async def test_another_shift_with_the_retired_token_starts_a_new_chain(
    world: World,
) -> None:
    """Another shift ("Noch eine Schicht") waits for the confirmation on the chain's row, then
    finds its token retired."""
    chain = await _chain(world, name="Tom", shifts=[world.ahead[0]])
    response_token = guest_tokens.manage_token(chain)
    confirmed = asyncio.Event()

    async def another_shift(session: AsyncSession) -> Any:
        return await signup.sign_up(
            session,
            code=world.list_code,
            form=PublicSignupRequest(
                shift_id=world.ahead[1],
                name="Tom",
                email=ADDRESS,
                show_names="none",
                guest_token=response_token,
            ),
            now=clock.utc_now(),
        )

    async def in_request() -> Any:
        async with world.sessions() as session, session.begin():
            return await another_shift(session)

    key, outcome = await _both(
        _confirm(world, chain, done=confirmed, hold=HOLD),
        _after(confirmed, in_request()),
    )

    assert isinstance(key, GuestKey), key
    assert not isinstance(outcome, BaseException), outcome
    [new_owner] = await _owners(world, Booking, shift_id=world.ahead[1])
    assert new_owner != chain.user_id
    world.guests.append(new_owner)
    assert outcome.result.guest_token != response_token


# ── Removal, deleting the event, erasing the account ─────────────


async def _remove(w: World, booking_id: uuid.UUID) -> Any:
    async with w.sessions() as session, session.begin():
        organiser = await session.get(User, w.organiser_id)
        shared_list = await session.get(SharedList, w.list_id)
        event = await session.get(Event, w.event_id)
        assert organiser is not None and shared_list is not None and event is not None
        outcome = await remove_signups(
            session,
            user=organiser,
            shared_list=shared_list,
            event=event,
            access="admin",
            request=SharedListSignupRemoveRequest(
                booking_ids=[booking_id], notify=False, erase=True
            ),
            now=clock.utc_now(),
            now_wall=clock.wall_clock_now(event.timezone),
        )
        return outcome.result


async def test_a_removal_that_waited_for_a_merge_leaves_the_account_alone(
    world: World,
) -> None:
    """The removal locked the chain's row as its statement saw it; once the
    merge committed, the booking is the account's and that row is gone.
    Going on would erase the whole account without its lock."""
    maria = await _chain(world, name="Maria", shifts=[world.ahead[0]])
    await _confirm(world, maria)
    tom = await _chain(world, name="Tom", shifts=[world.ahead[1]])
    [tom_booking] = await _bookings_of(world, tom.user_id)
    merged = asyncio.Event()

    _, removed = await _both(
        _confirm(world, tom, done=merged, hold=HOLD),
        _after(merged, _remove(world, tom_booking)),
    )

    assert not isinstance(removed, BaseException), removed
    assert removed.removed == []
    assert [s.code for s in removed.skipped] == ["shared_list.signup_not_found"]
    assert removed.erased_guests == 0
    assert await _accounts(world) == [maria.user_id]

    retried = await _remove(world, tom_booking)

    assert retried.removed == [tom_booking]
    assert retried.erased_guests == 1
    assert (
        await _scalar(world, select(func.count()).where(col(User.id) == maria.user_id))
        == 0
    )


async def _bookings_of(w: World, user_id: uuid.UUID) -> list[uuid.UUID]:
    async with w.sessions() as session:
        rows = await session.execute(
            select(col(Booking.id)).where(col(Booking.user_id) == user_id)
        )
        return list(rows.scalars())


async def _held_by(w: World, booking_id: uuid.UUID) -> tuple[Any, ...]:
    """Whose a booking is, under which name, and whether it still counts."""
    async with w.sessions() as session:
        row = (
            await session.execute(
                select(
                    col(Booking.user_id), col(Booking.guest_name), col(Booking.status)
                ).where(col(Booking.id) == booking_id)
            )
        ).one()
        return tuple(row)


async def test_an_operator_erase_that_waited_for_a_merge_erases_nothing_silently(
    world: World,
) -> None:
    """The erase waited for the chain's row, which the merge deleted with its
    user: the sign-ups are the account's now. It answers 404, so the operator
    searches again, instead of 204 for an erasure that erased nothing."""
    maria = await _chain(world, name="Maria", shifts=[world.ahead[0]])
    await _confirm(world, maria)
    tom = await _chain(world, name="Tom", shifts=[world.ahead[1]])
    [tom_booking] = await _bookings_of(world, tom.user_id)
    merged = asyncio.Event()

    async def erase() -> None:
        async with world.sessions() as session, session.begin():
            operator = await session.get(User, world.organiser_id)
            assert operator is not None
            await erase_list_guest(tom.user_id, session, operator)

    _, erased = await _both(
        _confirm(world, tom, done=merged, hold=HOLD), _after(merged, erase())
    )

    assert _problem(erased) == (404, "guest_signup.not_found")
    assert await _held_by(world, tom_booking) == (maria.user_id, "Tom", "confirmed")


async def _sweep(w: World) -> None:
    async with w.sessions() as session, session.begin():
        await retention.sweep_guest_data(session, now=SWEPT_AT, retention_days=30)


async def test_the_sweep_leaves_an_account_that_a_merge_holds(world: World) -> None:
    """Maria's only shift is past retention when Tom's sign-up, still ahead,
    is merged into her account. The sweep skips the row the merge holds
    rather than waiting to anonymise the account under Tom's booking; by its
    next run the account's last day is Tom's shift."""
    maria = await _chain(world, name="Maria", shifts=[world.ended])
    await _confirm(world, maria)
    tom = await _chain(world, name="Tom", shifts=[world.ahead[1]])
    [tom_booking] = await _bookings_of(world, tom.user_id)
    merged = asyncio.Event()

    confirmed, swept = await _both(
        _confirm(world, tom, done=merged, hold=HOLD), _after(merged, _sweep(world))
    )
    await _sweep(world)

    assert isinstance(confirmed, GuestKey), confirmed
    assert swept is None
    assert await _accounts(world) == [maria.user_id]
    assert await _held_by(world, tom_booking) == (maria.user_id, "Tom", "confirmed")


async def test_the_sweep_judges_again_once_it_holds_the_rows(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A merge that commits between the sweep's first look and its lock gave
    the account a shift ahead: judged again, it is not due."""
    maria = await _chain(world, name="Maria", shifts=[world.ended])
    await _confirm(world, maria)
    tom = await _chain(world, name="Tom", shifts=[world.ahead[1]])
    [tom_booking] = await _bookings_of(world, tom.user_id)
    lock_unheld = crud_guest.lock_unheld

    async def merged_first(
        session: AsyncSession, *, user_ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]:
        await _confirm(world, tom)
        return await lock_unheld(session, user_ids=user_ids)

    monkeypatch.setattr(retention.crud_guest, "lock_unheld", merged_first)

    await _sweep(world)

    assert await _accounts(world) == [maria.user_id]
    assert await _held_by(world, tom_booking) == (maria.user_id, "Tom", "confirmed")


@pytest.mark.parametrize("first", ["confirm", "delete"])
async def test_confirm_beside_deleting_the_event(first: str, world: World) -> None:
    """Both start at the event row: the deletion waits, or the confirmation
    finds no event."""
    maria = await _chain(world, name="Maria", shifts=[world.ahead[0]])
    await _confirm(world, maria)
    tom = await _chain(world, name="Tom", shifts=[world.ahead[1]])
    started = asyncio.Event()

    async def delete_event(hold: float = 0.0) -> None:
        async with world.sessions() as session, session.begin():
            await session.execute(delete(Event).where(col(Event.id) == world.event_id))
            started.set()
            await asyncio.sleep(hold)

    if first == "confirm":
        confirmed, deleted = await _both(
            _confirm(world, tom, done=started, hold=HOLD),
            _after(started, delete_event()),
        )
        assert isinstance(confirmed, GuestKey), confirmed
    else:
        deleted, confirmed = await _both(
            delete_event(hold=HOLD), _after(started, _confirm(world, tom))
        )
        assert _problem(confirmed) == (404, "guest_signup.not_found")
    assert deleted is None
    assert (
        await _scalar(
            world, select(func.count()).where(col(Event.id) == world.event_id)
        )
        == 0
    )


@pytest.mark.parametrize("worked", [False, True])
async def test_confirm_beside_erasing_the_account(worked: bool, world: World) -> None:
    """The erase does not take the account lock, so it can commit between
    finding the account and locking it. Anonymised or deleted, it is no
    account any more: the confirming chain becomes the new one."""
    maria = await _chain(
        world, name="Maria", shifts=[world.ended] if worked else [world.ahead[0]]
    )
    await _confirm(world, maria)
    tom = await _chain(world, name="Tom", shifts=[world.ahead[1]])
    erased = asyncio.Event()

    async def erase() -> None:
        async with world.sessions() as session, session.begin():
            await crud_guest.get_for_update(session, user_id=maria.user_id)
            await erase_guests(session, user_ids=[maria.user_id], now=clock.utc_now())
            erased.set()
            await asyncio.sleep(HOLD)

    done, key = await _both(erase(), _after(erased, _confirm(world, tom)))

    assert done is None
    assert isinstance(key, GuestKey), key
    assert key.guest.user_id == tom.user_id
    assert await _accounts(world) == [tom.user_id]
    assert await _scalar(world, select(func.count(col(SharedListGuestAlias.id)))) == 0


# ── Earnings, corrections, reminders ──────────────────────────────


async def _settling_change(
    w: World, kind: str, *, done: asyncio.Event | None = None, hold: float = 0.0
) -> None:
    """A rate change or a shift delete, settling first as the routes do."""
    async with w.sessions() as session, session.begin():
        now = clock.wall_clock_now()
        if kind == "rate":
            await vouchers.settle_earnings(
                session, now=now, task_ids=[w.bar_id], include_zero=True
            )
            await session.execute(
                update(Task)
                .where(col(Task.id) == w.bar_id)
                .values(vouchers_per_shift=0)
            )
        else:
            await vouchers.settle_earnings(session, now=now, shift_ids=[w.ended])
            await session.execute(delete(Shift).where(col(Shift.id) == w.ended))
        if done is not None:
            done.set()
        await asyncio.sleep(hold)


@pytest.mark.parametrize("kind", ["rate", "delete"])
@pytest.mark.parametrize("first", ["change", "merge"])
async def test_no_earning_is_lost_to_a_merge(
    kind: str, first: str, world: World
) -> None:
    """``settle_earnings`` takes no lock, so the chain's ``users`` row orders
    it against the merge: an earning inserted first moves with the rest; one
    that comes later fails its foreign key, and the organiser's retry settles
    it on the account. Never one deleted with the chain's user."""
    maria = await _chain(world, name="Maria", shifts=[world.ahead[0]])
    await _confirm(world, maria)
    tom = await _chain(world, name="Tom", shifts=[world.ended])
    [worked] = await _bookings_of(world, tom.user_id)
    started = asyncio.Event()

    if first == "change":
        changed, merged = await _both(
            _settling_change(world, kind, done=started, hold=HOLD),
            _after(started, _confirm(world, tom)),
        )
        assert changed is None
    else:
        merged, changed = await _both(
            _confirm(world, tom, done=started, hold=HOLD),
            _after(started, _settling_change(world, kind)),
        )
        assert isinstance(changed, IntegrityError), changed
        await _settling_change(world, kind)
    assert isinstance(merged, GuestKey), merged

    assert await _owners(world, VoucherEarning, booking_id=worked) == [maria.user_id]
    amount = await _scalar(
        world,
        select(col(VoucherEarning.amount)).where(
            col(VoucherEarning.booking_id) == worked
        ),
    )
    assert amount == 2


@pytest.mark.parametrize("first", ["correction", "merge"])
async def test_a_correction_beside_a_merge_is_never_lost(
    first: str, world: World
) -> None:
    """The chain has a part in the event only through a shift without
    vouchers; that event's ledger lock is still in the merge's set. The
    correction lands first and moves, or finds the chain gone."""
    maria = await _chain(world, name="Maria", shifts=[world.ahead[0]])
    await _confirm(world, maria)
    tom = await _chain(world, name="Tom", shifts=[world.cloakroom])
    started = asyncio.Event()

    async def correct(*, hold: float = 0.0) -> None:
        async with world.sessions() as session, session.begin():
            organiser = await session.get(User, world.organiser_id)
            assert organiser is not None
            await create_voucher_adjustment(
                world.event_id,
                VoucherAdjustmentCreate(user_id=tom.user_id, amount=1, note="Kuchen"),
                session,
                organiser,
            )
            started.set()
            await asyncio.sleep(hold)

    if first == "correction":
        corrected, merged = await _both(
            correct(hold=HOLD), _after(started, _confirm(world, tom))
        )
        assert corrected is None
        assert await _owners(world, VoucherEntry, event_id=world.event_id) == [
            maria.user_id
        ]
    else:
        merged, corrected = await _both(
            _confirm(world, tom, done=started, hold=HOLD), _after(started, correct())
        )
        assert _problem(corrected) == (404, "event.member_not_found")
        assert await _owners(world, VoucherEntry, event_id=world.event_id) == []
    assert isinstance(merged, GuestKey), merged


async def test_the_reminder_poller_beside_a_merge(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The merge holds the chain's reminder row, which the poller skips
    rather than waits for; its next round sends the reminder once, about the
    account."""
    maria, tom, reminder_id = await _tom_with_a_reminder(world, monkeypatch)
    merged = asyncio.Event()

    with patch("app.logic.auth.emails._smtp_send", new_callable=AsyncMock) as smtp:
        confirmed, during = await _both(
            _confirm(world, tom, done=merged, hold=HOLD),
            _after(merged, _poll_ours(reminder_id)),
        )
        after = await _poll_ours(reminder_id)

    assert isinstance(confirmed, GuestKey), confirmed
    assert (during, after) == (False, True)
    assert smtp.await_count == 1
    async with world.sessions() as session:
        row = await session.get(BookingReminder, reminder_id)
        assert row is not None
        assert (row.user_id, row.status) == (maria.user_id, "sent")


async def _tom_with_a_reminder(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> tuple[SharedListGuest, SharedListGuest, uuid.UUID]:
    """Maria's account, and Tom's chain of the same address with a reminder
    due: the poller's world, mail switched on."""
    configure_smtp(monkeypatch)
    maria = await _chain(world, name="Maria", shifts=[world.ahead[0]])
    await _confirm(world, maria)
    tom = await _chain(world, name="Tom", shifts=[world.ahead[1]])
    [booking] = await _bookings_of(world, tom.user_id)
    async with world.sessions() as session, session.begin():
        event = await session.get(Event, world.event_id)
        assert event is not None
        [reminder] = await crud_reminder.replace_for_booking(
            session,
            booking_id=booking,
            user_id=tom.user_id,
            shift_id=world.ahead[1],
            entries=[GUEST_REMINDER],
            slot_start=dt.datetime(2026, 6, 12, 10),
            zone=event.timezone,
        )
    monkeypatch.setattr(reminder_poller, "async_session", world.sessions)
    monkeypatch.setattr(guest_mail, "async_session", world.sessions)
    return maria, tom, reminder.id


async def test_a_merge_between_the_poller_fetch_and_its_send(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The poller's round fetches Tom's reminder and commits; the merge
    commits before the reminder is processed. Acting on the snapshot, the
    notice would look for Tom's deleted user, find nobody, and the reminder
    would be marked sent without a mail. The fresh row names the account."""
    maria, tom, reminder_id = await _tom_with_a_reminder(world, monkeypatch)
    process = reminder_poller._process_reminder  # pyright: ignore[reportPrivateUsage]
    snapshots: list[BookingReminder] = []

    async def merge_first(reminder: BookingReminder) -> None:
        if reminder.id != reminder_id:
            return
        snapshots.append(reminder)
        await _confirm(world, tom)
        await process(reminder)

    with (
        patch("app.logic.auth.emails._smtp_send", new_callable=AsyncMock) as smtp,
        patch.object(reminder_poller, "_process_reminder", merge_first),
    ):
        await reminder_poller._poll_cycle()  # pyright: ignore[reportPrivateUsage]

    [snapshot] = snapshots
    assert snapshot.user_id == tom.user_id
    assert smtp.await_count == 1
    async with world.sessions() as session:
        row = await session.get(BookingReminder, reminder_id)
        assert row is not None
        assert (row.user_id, row.status) == (maria.user_id, "sent")


async def test_a_merge_while_the_poller_sends(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The poller holds no lock while it mails, so a confirmation pressed
    during the send neither waits for the mail server nor deadlocks with it.
    The reminder goes out once, to the address both chains share, and ends
    on the account, sent."""
    maria, tom, reminder_id = await _tom_with_a_reminder(world, monkeypatch)
    sending = asyncio.Event()

    async def slow_send(*_: Any, **__: Any) -> None:
        sending.set()
        await asyncio.sleep(HOLD)

    with patch("app.logic.auth.emails._smtp_send", new_callable=AsyncMock) as smtp:
        smtp.side_effect = slow_send
        polled, confirmed = await _both(
            _poll_ours(reminder_id), _after(sending, _confirm(world, tom))
        )

    assert polled is True
    assert isinstance(confirmed, GuestKey), confirmed
    assert smtp.await_count == 1
    async with world.sessions() as session:
        row = await session.get(BookingReminder, reminder_id)
        assert row is not None
        assert (row.user_id, row.status) == (maria.user_id, "sent")


async def _poll_ours(reminder_id: uuid.UUID) -> bool:
    """One poller round; whether it took this test's reminder. Other due
    reminders of the shared test database are sent along, which is harmless."""
    taken: list[uuid.UUID] = []
    process = reminder_poller._process_reminder  # pyright: ignore[reportPrivateUsage]

    async def record(reminder: BookingReminder) -> None:
        taken.append(reminder.id)
        if reminder.id == reminder_id:
            await process(reminder)

    with patch.object(reminder_poller, "_process_reminder", record):
        await reminder_poller._poll_cycle()  # pyright: ignore[reportPrivateUsage]
    return reminder_id in taken
