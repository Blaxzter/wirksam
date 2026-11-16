"""Confirming a guest's address (``logic/shared_lists/guest_account.py``).

The first confirmation of an address at an event makes its chain the guest
account, in place; every later one merges its chain into that account. Both
clocks stand at 1 June 2026, so shifts dated in May have ended and earned.
"""

import datetime as dt
import uuid

import pytest
from fastapi import FastAPI, HTTPException
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.booking import booking as crud_booking
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.logic import clock, vouchers
from app.logic.shared_lists import guest_account, guest_tokens, guest_vouchers
from app.logic.shared_lists.guest_mail import GUEST_REMINDER
from app.logic.shared_lists.public_page import first_names
from app.logic.shared_lists.signups_query import list_signups
from app.models.booking import Booking
from app.models.booking_reminder import BookingReminder
from app.models.event import Event
from app.models.shared_list import (
    GuestActivityLog,
    SharedList,
    SharedListGuest,
    SharedListGuestAlias,
)
from app.models.task import Task
from app.models.user import User
from app.models.voucher import VoucherEarning, VoucherEntry, VoucherPass
from tests.fixtures.client import act_as
from tests.fixtures.guest_signups import add_shift, confirm_address, freeze_clocks
from tests.fixtures.shared_lists import (
    ListGuest,
    ListGuestFactory,
    SharedListFactory,
)

#: Ended by the frozen clocks.
MAY = dt.date(2026, 5, 20)
ADDRESS = "family@example.org"


@pytest.fixture(autouse=True)
def _clocks(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_clocks(monkeypatch)


async def _earning_task(db: AsyncSession, task: Task, per_shift: int = 2) -> Task:
    task.vouchers_per_shift = per_shift
    db.add(task)
    await db.flush()
    return task


async def _pass(
    db: AsyncSession, guest: ListGuest, event: Event, *, used: bool = False
) -> VoucherPass:
    p = VoucherPass(
        event_id=event.id,
        user_id=guest.user.id,
        code=uuid.uuid4().hex[:6].upper(),
        expires_at=clock.utc_now() + dt.timedelta(minutes=2),
        used_at=clock.utc_now() if used else None,
    )
    db.add(p)
    await db.flush()
    return p


async def _available(db: AsyncSession, event: Event, user_id: uuid.UUID) -> int:
    return await vouchers.available_for(
        db, event.id, user_id, now=clock.wall_clock_now(event.timezone)
    )


async def _owner(
    db: AsyncSession, model: type[Booking] | type[VoucherPass], row_id: uuid.UUID
) -> uuid.UUID:
    row = (
        await db.execute(
            select(model)
            .where(col(model.id) == row_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return row.user_id


async def _gone(db: AsyncSession, model: type[VoucherPass], row_id: uuid.UUID) -> bool:
    return (await db.scalar(select(func.count()).where(col(model.id) == row_id))) == 0


@pytest.mark.asyncio
class TestPromote:
    async def test_the_first_confirmation_makes_the_chain_the_account(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        shift = await add_shift(db_session, await _earning_task(db_session, test_task))
        chain = await make_list_guest(test_shared_list, email=ADDRESS, shifts=[shift])
        response_token = guest_tokens.manage_token(chain.guest)
        unused = await _pass(db_session, chain, test_event)
        used = await _pass(db_session, chain, test_event, used=True)

        key = await confirm_address(db_session, chain.guest)

        assert key.from_mail
        assert key.guest.user_id == chain.user.id
        assert key.guest.confirmed_at == clock.utc_now()
        assert (
            await db_session.scalar(select(func.count(col(SharedListGuestAlias.id))))
            == 0
        )
        assert await _gone(db_session, VoucherPass, unused.id)
        assert not await _gone(db_session, VoucherPass, used.id)
        # Whoever typed the address loses the chain; the mailbox keeps it.
        assert await guest_tokens.resolve(db_session, response_token) is None
        assert await guest_tokens.retired_response_token(db_session, response_token)
        reopened = await guest_tokens.resolve(
            db_session, guest_tokens.mail_token(chain.guest)
        )
        assert reopened is not None
        assert (reopened.guest.user_id, reopened.from_mail) == (chain.user.id, True)

    async def test_confirming_again_answers_with_the_account(
        self,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        account = await make_list_guest(test_shared_list, email=ADDRESS)
        merged = await make_list_guest(test_shared_list, email=ADDRESS)
        await confirm_address(db_session, account.guest)
        merged_link = guest_tokens.mail_token(merged.guest)
        await confirm_address(db_session, merged.guest)

        again = await confirm_address(db_session, account.guest)
        assert again.guest.user_id == account.user.id
        peeked = await guest_tokens.peek(db_session, merged_link)
        assert peeked is not None
        through_alias = await guest_account.confirm(
            db_session, peeked=peeked, token=merged_link, now=clock.utc_now()
        )
        assert through_alias.guest.user_id == account.user.id

    async def test_the_same_address_at_another_event_is_another_account(
        self,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_event_admin_user: User,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
    ) -> None:
        other_event = Event(
            name="Anderes Fest",
            start_date=dt.date(2026, 7, 1),
            end_date=dt.date(2026, 7, 2),
            status="published",
            created_by_id=test_event_admin_user.id,
        )
        db_session.add(other_event)
        await db_session.flush()
        here = await make_list_guest(test_shared_list, email=ADDRESS)
        there = await make_list_guest(
            await make_shared_list(event=other_event, tasks=[]), email=ADDRESS
        )

        await confirm_address(db_session, here.guest)
        key = await confirm_address(db_session, there.guest)

        assert key.guest.user_id == there.user.id
        assert there.guest.confirmed_at is not None
        assert here.guest.confirmed_at is not None


@pytest.mark.asyncio
class TestRefusals:
    async def test_only_a_mail_link_confirms(
        self,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        chain = await make_list_guest(test_shared_list, email=ADDRESS)
        token = guest_tokens.manage_token(chain.guest)
        peeked = await guest_tokens.peek(db_session, token)
        assert peeked is not None and not peeked.from_mail

        with pytest.raises(HTTPException) as refused:
            await guest_account.confirm(
                db_session, peeked=peeked, token=token, now=clock.utc_now()
            )

        assert refused.value.status_code == 403
        assert chain.guest.confirmed_at is None

    async def test_a_chain_without_an_address_has_nothing_to_confirm(
        self,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        chain = await make_list_guest(test_shared_list)

        with pytest.raises(HTTPException) as refused:
            await confirm_address(db_session, chain.guest)

        assert refused.value.status_code == 404
        assert chain.guest.confirmed_at is None

    async def test_a_chain_erased_after_the_token_was_read(
        self,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        chain = await make_list_guest(test_shared_list, email=ADDRESS)
        token = guest_tokens.mail_token(chain.guest)
        peeked = await guest_tokens.peek(db_session, token)
        assert peeked is not None
        chain.guest.manage_nonce = None
        db_session.add(chain.guest)
        await db_session.flush()

        with pytest.raises(HTTPException) as refused:
            await guest_account.confirm(
                db_session, peeked=peeked, token=token, now=clock.utc_now()
            )

        assert refused.value.status_code == 404
        assert chain.guest.confirmed_at is None


@pytest.mark.asyncio
class TestMerge:
    async def test_a_later_chain_moves_into_the_account(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        task = await _earning_task(db_session, test_task)
        maria = await make_list_guest(
            test_shared_list,
            name="Maria",
            email=ADDRESS,
            shifts=[await add_shift(db_session, task, day=MAY)],
        )
        tom_shifts = [
            await add_shift(db_session, task, day=MAY + dt.timedelta(days=1)),
            await add_shift(db_session, task),
        ]
        tom = await make_list_guest(
            test_shared_list, name="Tom", email=ADDRESS, shifts=tom_shifts
        )
        ended, ahead = tom.bookings
        await crud_reminder.replace_for_booking(
            db_session,
            booking_id=ahead.id,
            user_id=tom.user.id,
            shift_id=ahead.shift_id,  # type: ignore[arg-type]
            entries=[GUEST_REMINDER],
            slot_start=dt.datetime(2026, 6, 11, 10),
            zone=test_event.timezone,
        )
        await vouchers.settle_earnings(
            db_session,
            now=clock.wall_clock_now(),
            shift_ids=[ended.shift_id],  # type: ignore[list-item]
        )
        db_session.add(
            VoucherEntry(
                event_id=test_event.id,
                user_id=tom.user.id,
                kind="adjustment",
                amount=1,
                note="Kuchen gebacken",
            )
        )
        used = await _pass(db_session, tom, test_event, used=True)
        unused = await _pass(db_session, tom, test_event)
        await db_session.flush()
        tom_nonce = tom.guest.manage_nonce
        assert await _available(db_session, test_event, maria.user.id) == 2
        assert await _available(db_session, test_event, tom.user.id) == 3

        await confirm_address(db_session, maria.guest)
        key = await confirm_address(db_session, tom.guest)

        assert key.guest.user_id == maria.user.id
        for booking in tom.bookings:
            assert await _owner(db_session, Booking, booking.id) == maria.user.id
        reminders = await db_session.execute(
            select(col(BookingReminder.user_id)).where(
                col(BookingReminder.booking_id) == ahead.id
            )
        )
        assert set(reminders.scalars()) == {maria.user.id}
        earned = await db_session.execute(
            select(col(VoucherEarning.user_id)).where(
                col(VoucherEarning.booking_id) == ended.id
            )
        )
        assert set(earned.scalars()) == {maria.user.id}
        assert await _owner(db_session, VoucherPass, used.id) == maria.user.id
        assert await _gone(db_session, VoucherPass, unused.id)
        assert (
            await db_session.scalar(
                select(func.count()).where(col(VoucherEntry.user_id) == maria.user.id)
            )
            == 1
        )
        assert (
            await db_session.scalar(
                select(func.count()).where(col(User.id) == tom.user.id)
            )
            == 0
        )
        assert (
            await db_session.scalar(
                select(func.count()).where(col(SharedListGuest.user_id) == tom.user.id)
            )
            == 0
        )
        [alias] = (await db_session.execute(select(SharedListGuestAlias))).scalars()
        assert (alias.user_id, alias.manage_nonce, alias.account_user_id) == (
            tom.user.id,
            tom_nonce,
            maria.user.id,
        )
        assert await _available(db_session, test_event, maria.user.id) == 5

    async def test_the_account_keeps_its_own_name_and_the_latest_sign_up(
        self,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        maria = await make_list_guest(
            test_shared_list, name="Maria", email=ADDRESS, phone="0170 1"
        )
        tom = await make_list_guest(
            test_shared_list, name="Tom", email=ADDRESS, phone="0170 2", language="en"
        )
        tom.guest.last_signup_at = clock.utc_now() + dt.timedelta(hours=1)
        db_session.add(tom.guest)
        await db_session.flush()
        await confirm_address(db_session, maria.guest)

        await confirm_address(db_session, tom.guest)

        await db_session.refresh(maria.user)
        assert (
            maria.user.name,
            maria.user.phone_number,
            maria.user.preferred_language,
        ) == ("Maria", "0170 1", "de")
        assert maria.guest.last_signup_at == clock.utc_now() + dt.timedelta(hours=1)

    async def test_the_activity_log_is_left_alone(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        maria = await make_list_guest(test_shared_list, email=ADDRESS)
        tom = await make_list_guest(
            test_shared_list,
            email=ADDRESS,
            shifts=[await add_shift(db_session, test_task)],
        )
        db_session.add(
            GuestActivityLog(
                kind="signup",
                address_hash=guest_tokens.address_hash(ADDRESS),
                event_id=test_shared_list.event_id,
                shared_list_id=test_shared_list.id,
                booking_id=tom.bookings[0].id,
            )
        )
        await db_session.flush()

        async def log() -> list[tuple[str, uuid.UUID | None]]:
            rows = await db_session.execute(
                select(col(GuestActivityLog.kind), col(GuestActivityLog.booking_id))
            )
            return sorted(((kind, booking) for kind, booking in rows.all()), key=str)

        before = await log()
        await confirm_address(db_session, maria.guest)
        await confirm_address(db_session, tom.guest)
        assert await log() == before


@pytest.mark.asyncio
class TestCollisions:
    """Both users have a booking on one shift (``uq_booking_shift_user`` covers
    every status): one goes."""

    @pytest.mark.parametrize(
        ("source", "target", "kept"),
        [
            ("cancelled", "confirmed", "target"),
            ("confirmed", "cancelled", "source"),
            ("cancelled", "cancelled", "target"),
        ],
    )
    async def test_one_booking_per_shift_is_kept(
        self,
        source: str,
        target: str,
        kept: str,
        db_session: AsyncSession,
        test_task: Task,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        shift = await add_shift(db_session, test_task)
        account = await make_list_guest(test_shared_list, email=ADDRESS, shifts=[shift])
        chain = await make_list_guest(test_shared_list, email=ADDRESS, shifts=[shift])
        account.bookings[0].status = target
        chain.bookings[0].status = source
        db_session.add_all([*account.bookings, *chain.bookings])
        await db_session.flush()
        await confirm_address(db_session, account.guest)

        await confirm_address(db_session, chain.guest)

        rows = (
            await db_session.execute(
                select(col(Booking.id), col(Booking.user_id), col(Booking.status))
                .where(col(Booking.shift_id) == shift.id)
                .execution_options(populate_existing=True)
            )
        ).all()
        expected = (account if kept == "target" else chain).bookings[0]
        assert [(r.id, r.user_id, r.status) for r in rows] == [
            (expected.id, account.user.id, target if kept == "target" else source)
        ]

    async def test_confirmed_on_both_sides_keeps_what_was_earned(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """Cannot arise through sign-ups, which refuse an address twice on a
        shift. Should it, the ended shift's earning survives the dropped
        booking, so the pooled total does not change."""
        shift = await add_shift(
            db_session, await _earning_task(db_session, test_task), day=MAY
        )
        account = await make_list_guest(test_shared_list, email=ADDRESS, shifts=[shift])
        chain = await make_list_guest(test_shared_list, email=ADDRESS, shifts=[shift])
        await confirm_address(db_session, account.guest)
        before = await _available(
            db_session, test_event, account.user.id
        ) + await _available(db_session, test_event, chain.user.id)

        await confirm_address(db_session, chain.guest)

        assert (
            await db_session.scalar(
                select(func.count()).where(col(Booking.shift_id) == shift.id)
            )
            == 1
        )
        earned = await db_session.execute(
            select(col(VoucherEarning.user_id), col(VoucherEarning.amount)).where(
                col(VoucherEarning.shift_id) == shift.id
            )
        )
        assert sorted([tuple(row) for row in earned.all()]) == [
            (account.user.id, 2),
            (account.user.id, 2),
        ]
        assert await _available(db_session, test_event, account.user.id) == before == 4


@pytest.mark.asyncio
class TestEachSignUpKeepsItsPerson:
    async def test_names_phones_and_consent_stay_with_their_bookings(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event_admin_user: User,
        test_task: Task,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """Maria signs up on a list that names nobody and confirms; Tom signs
        up with the same address on one that shows first names. Pooled, each
        shift still shows its own person, and only Tom's is named."""
        silent = await make_shared_list(show_names="none")
        naming = await make_shared_list(show_names="first", title="Mit Namen")
        maria_shift = await add_shift(db_session, test_task)
        tom_shift = await add_shift(db_session, test_task, day=dt.date(2026, 6, 12))
        maria = await make_list_guest(
            silent,
            name="Maria Muster",
            email=ADDRESS,
            phone="0170 1",
            shifts=[maria_shift],
        )
        tom = await make_list_guest(
            naming, name="Tom Muster", email=ADDRESS, phone="0170 2", shifts=[tom_shift]
        )
        await confirm_address(db_session, maria.guest)
        await confirm_address(db_session, tom.guest)

        assert await first_names(db_session, [maria_shift.id, tom_shift.id]) == {
            tom_shift.id: ["Tom"]
        }
        bookers = await crud_booking.confirmed_bookers(
            db_session, slot_ids=[maria_shift.id, tom_shift.id]
        )
        assert bookers == {
            maria_shift.id: [(maria.user.id, "Maria Muster", True)],
            tom_shift.id: [(maria.user.id, "Tom Muster", True)],
        }
        with act_as(app, test_event_admin_user):
            roster = (
                await async_client.get(f"/api/v1/shifts/{tom_shift.id}/bookings")
            ).json()
            task_roster = (
                await async_client.get(f"/api/v1/tasks/{test_task.id}/bookings")
            ).json()
        assert [(e["user_name"], e["user_phone_number"]) for e in roster] == [
            ("Tom Muster", "0170 2")
        ]
        assert sorted(
            (e["user_name"], e["user_phone_number"]) for e in task_roster
        ) == [("Maria Muster", "0170 1"), ("Tom Muster", "0170 2")]
        signups, _, _ = await list_signups(
            db_session,
            shared_list=naming,
            task_ids=None,
            q="tom",
            sort_by="name",
            sort_dir=None,
            skip=0,
            limit=10,
            now_wall=clock.wall_clock_now(),
        )
        assert [(s.name, s.phone, s.email) for s in signups] == [
            ("Tom Muster", "0170 2", ADDRESS)
        ]
        await db_session.refresh(maria.user)
        assert (maria.user.name, maria.user.phone_number) == ("Maria Muster", "0170 1")

    async def test_a_guest_without_a_contact_row_is_never_named(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_event_admin_user: User,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """The guest's event is deleted after their task moved to another one:
        the booking lives on there, and the contact row is gone."""
        first_event = Event(
            name="Erstes Fest",
            start_date=dt.date(2026, 6, 10),
            end_date=dt.date(2026, 6, 14),
            status="published",
            created_by_id=test_event_admin_user.id,
        )
        db_session.add(first_event)
        await db_session.flush()
        task = Task(
            name="Grill",
            start_date=dt.date(2026, 6, 11),
            end_date=dt.date(2026, 6, 11),
            status="published",
            event_id=first_event.id,
        )
        db_session.add(task)
        await db_session.flush()
        shift = await add_shift(db_session, task)
        await make_list_guest(
            await make_shared_list(event=first_event, tasks=[task], show_names="first"),
            name="Lena",
            shifts=[shift],
        )
        task.event_id = test_event.id
        db_session.add(task)
        await db_session.flush()
        assert await first_names(db_session, [shift.id]) == {shift.id: ["Lena"]}

        await db_session.execute(delete(Event).where(col(Event.id) == first_event.id))

        assert await first_names(db_session, [shift.id]) == {}


@pytest.mark.asyncio
class TestEventIds:
    async def test_the_ledger_locks_cover_bookings_without_vouchers(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """A correction is allowed wherever the guest has a booking, Marken or
        not, so a merge must hold that event's ledger lock; the vouchers on
        the manage page only show where something earns."""
        chain = await make_list_guest(
            test_shared_list, shifts=[await add_shift(db_session, test_task)]
        )

        assert await guest_vouchers.ledger_event_ids(
            db_session, user_id=chain.user.id
        ) == [test_event.id]
        assert (
            await guest_vouchers.voucher_event_ids(db_session, user_id=chain.user.id)
            == []
        )
        await _earning_task(db_session, test_task)
        assert await guest_vouchers.voucher_event_ids(
            db_session, user_id=chain.user.id
        ) == [test_event.id]


@pytest.mark.asyncio
async def test_a_merge_can_target_any_user(
    db_session: AsyncSession,
    test_user: User,
    test_task: Task,
    test_shared_list: SharedList,
    make_list_guest: ListGuestFactory,
) -> None:
    """Claiming sign-ups into a real account will reuse the merge."""
    chain = await make_list_guest(
        test_shared_list, shifts=[await add_shift(db_session, test_task)]
    )

    result = await guest_account.merge_guest(
        db_session, source=chain.guest, target_user_id=test_user.id
    )

    assert (result.moved, result.dropped, result.passes_deleted) == (1, 0, 0)
    assert await _owner(db_session, Booking, chain.bookings[0].id) == test_user.id
