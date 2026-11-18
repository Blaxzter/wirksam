"""``crud.shared_list``: list codes, the tasks and excluded shifts of a list, and
what happens to them when tasks, shifts or event dates move."""

import datetime as dt
import uuid
from collections.abc import Callable, Iterator
from itertools import chain, repeat

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.shared_list import (
    CODE_ALPHABET,
    CODE_LENGTH,
    CodeLock,
    generate_code,
)
from app.crud.shared_list import shared_list as crud_shared_list
from app.models.booking import Booking
from app.models.event import Event
from app.models.shared_list import (
    GuestActivityLog,
    SharedList,
    SharedListExcludedShift,
    SharedListGuest,
    SharedListTask,
)
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from tests.fixtures.shared_lists import ListGuestFactory, SharedListFactory


async def _task(db: AsyncSession, event: Event, creator: User, name: str) -> Task:
    task = Task(
        name=name,
        start_date=dt.date(2026, 6, 11),
        end_date=dt.date(2026, 6, 12),
        status="published",
        created_by_id=creator.id,
        event_id=event.id,
    )
    db.add(task)
    await db.flush()
    return task


async def _shift(db: AsyncSession, task: Task, day: int = 11) -> Shift:
    shift = Shift(
        task_id=task.id,
        title=task.name,
        date=dt.date(2026, 6, day),
        start_time=dt.time(10),
        max_bookings=2,
    )
    db.add(shift)
    await db.flush()
    return shift


def _choices(*codes: str, then: str | None = None) -> Callable[[str], str]:
    """A stand-in for ``secrets.choice`` that spells out ``codes`` in turn,
    then repeats the characters of ``then`` (or the last code) for good."""
    tail = then or codes[-1]
    chars: Iterator[str] = chain(*codes, chain.from_iterable(repeat(tail)))
    return lambda _alphabet: next(chars)


class TestGenerateCode:
    def test_twelve_characters_of_the_alphabet(self) -> None:
        codes = {generate_code() for _ in range(200)}
        assert len(codes) == 200
        for code in codes:
            assert len(code) == CODE_LENGTH == 12
            assert set(code) <= set(CODE_ALPHABET)

    def test_the_alphabet_leaves_out_lookalikes_and_dots(self) -> None:
        assert not set("ilo" + "IO" + "01" + ".") & set(CODE_ALPHABET)
        assert len(CODE_ALPHABET) == 55


@pytest.mark.asyncio
class TestCreate:
    async def test_stores_a_live_list_with_its_creator(
        self, db_session: AsyncSession, test_event: Event, test_user: User
    ) -> None:
        shared_list = await crud_shared_list.create(
            db_session,
            event_id=test_event.id,
            created_by=test_user,
            title="Kuchenbuffet",
            intro="Wir brauchen Hilfe",
            share_note="WhatsApp-Gruppe",
            ask_email="optional",
            ask_phone="required",
            show_names="first",
            max_per_person=2,
            ends_mode="date",
            ends_on=dt.date(2026, 6, 12),
        )
        await db_session.refresh(shared_list)
        assert shared_list.status == "live"
        assert shared_list.view_count == 0
        assert (shared_list.created_by_id, shared_list.created_by_name) == (
            test_user.id,
            "Test User",
        )
        assert (
            shared_list.ask_email,
            shared_list.ask_phone,
            shared_list.show_names,
        ) == (
            "optional",
            "required",
            "first",
        )
        assert len(shared_list.code) == CODE_LENGTH

    async def test_a_taken_code_is_retried(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        make_shared_list: SharedListFactory,
    ) -> None:
        monkeypatch.setattr(
            "secrets.choice", _choices("a" * CODE_LENGTH, "a" * CODE_LENGTH, then="b")
        )
        first = await make_shared_list()
        second = await make_shared_list()
        assert (first.code, second.code) == ("a" * CODE_LENGTH, "b" * CODE_LENGTH)

    async def test_gives_up_after_five_taken_codes(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        make_shared_list: SharedListFactory,
    ) -> None:
        monkeypatch.setattr("secrets.choice", _choices("a"))
        await make_shared_list()
        with pytest.raises(RuntimeError, match="free shared list code"):
            await make_shared_list()


@pytest.mark.asyncio
class TestRotateCode:
    async def test_replaces_the_code_and_stamps_it(
        self, db_session: AsyncSession, test_shared_list: SharedList
    ) -> None:
        old = test_shared_list.code
        now = dt.datetime(2026, 6, 1, 12, 0)
        await crud_shared_list.rotate_code(
            db_session, shared_list=test_shared_list, now=now
        )
        assert test_shared_list.code != old
        assert test_shared_list.rotated_at == now
        assert await crud_shared_list.get_by_code(db_session, code=old) is None

    async def test_a_taken_code_is_retried_and_nothing_else_is_lost(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        make_shared_list: SharedListFactory,
    ) -> None:
        """The caller's change made before the rotation survives the failed
        attempt, and the row is readable afterwards without a lazy load."""
        monkeypatch.setattr(
            "secrets.choice",
            _choices("a" * CODE_LENGTH, "c" * CODE_LENGTH, "a" * CODE_LENGTH, then="d"),
        )
        taken = await make_shared_list()
        rotated = await make_shared_list()
        rotated.title = "Neuer Titel"

        await crud_shared_list.rotate_code(
            db_session, shared_list=rotated, now=dt.datetime(2026, 6, 1)
        )

        assert taken.code == "a" * CODE_LENGTH
        assert (rotated.code, rotated.title) == ("d" * CODE_LENGTH, "Neuer Titel")

    async def test_gives_up_after_five_taken_codes(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        make_shared_list: SharedListFactory,
    ) -> None:
        monkeypatch.setattr("secrets.choice", _choices("b" * CODE_LENGTH, then="a"))
        rotated = await make_shared_list()
        await make_shared_list()
        with pytest.raises(RuntimeError, match="free shared list code"):
            await crud_shared_list.rotate_code(
                db_session, shared_list=rotated, now=dt.datetime(2026, 6, 1)
            )


@pytest.mark.asyncio
class TestLookups:
    async def test_by_id_with_and_without_lock(
        self, db_session: AsyncSession, test_shared_list: SharedList
    ) -> None:
        assert (
            await crud_shared_list.get(db_session, shared_list_id=test_shared_list.id)
            is test_shared_list
        )
        assert (
            await crud_shared_list.get_for_update(
                db_session, shared_list_id=test_shared_list.id
            )
            is test_shared_list
        )

    @pytest.mark.parametrize("lock", [None, "key_share"])
    async def test_by_code(
        self,
        lock: CodeLock | None,
        db_session: AsyncSession,
        test_shared_list: SharedList,
    ) -> None:
        found = await crud_shared_list.get_by_code(
            db_session,
            code=test_shared_list.code,
            lock=lock,
        )
        assert found is test_shared_list

    async def test_an_unknown_code_is_none(
        self, db_session: AsyncSession, test_shared_list: SharedList
    ) -> None:
        assert await crud_shared_list.get_by_code(db_session, code="x" * 12) is None


@pytest.mark.asyncio
class TestTasksAndExclusions:
    async def test_tasks_keep_their_order_once_each(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        test_task: Task,
        test_shared_list: SharedList,
    ) -> None:
        bar = await _task(db_session, test_event, test_user, "Bar")
        await crud_shared_list.set_tasks(
            db_session,
            shared_list_id=test_shared_list.id,
            task_ids=[bar.id, test_task.id, bar.id],
        )
        assert await crud_shared_list.task_ids(
            db_session, shared_list_id=test_shared_list.id
        ) == [bar.id, test_task.id]

    async def test_exclusions_keep_only_shifts_of_the_lists_tasks(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        test_task: Task,
        test_shared_list: SharedList,
    ) -> None:
        mine = await _shift(db_session, test_task)
        other_task = await _task(db_session, test_event, test_user, "Bar")
        foreign = await _shift(db_session, other_task)

        kept = await crud_shared_list.set_excluded(
            db_session,
            shared_list_id=test_shared_list.id,
            shift_ids=[mine.id, foreign.id, uuid.uuid4()],
        )

        assert kept == [mine.id]
        assert await crud_shared_list.excluded_ids(
            db_session, shared_list_id=test_shared_list.id
        ) == [mine.id]

    async def test_exclusions_are_replaced(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_shared_list: SharedList,
    ) -> None:
        first, second = (
            await _shift(db_session, test_task),
            await _shift(db_session, test_task, day=12),
        )
        await crud_shared_list.set_excluded(
            db_session, shared_list_id=test_shared_list.id, shift_ids=[first.id]
        )
        await crud_shared_list.set_excluded(
            db_session, shared_list_id=test_shared_list.id, shift_ids=[second.id]
        )
        assert await crud_shared_list.excluded_ids(
            db_session, shared_list_id=test_shared_list.id
        ) == [second.id]
        assert (
            await crud_shared_list.set_excluded(
                db_session, shared_list_id=test_shared_list.id, shift_ids=[]
            )
            == []
        )
        assert (
            await crud_shared_list.excluded_ids(
                db_session, shared_list_id=test_shared_list.id
            )
            == []
        )

    async def test_dropping_a_task_drops_its_exclusions(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        test_task: Task,
        make_shared_list: SharedListFactory,
    ) -> None:
        """Adding the task back later offers all its shifts again."""
        bar = await _task(db_session, test_event, test_user, "Bar")
        dropped = await _shift(db_session, test_task)
        kept = await _shift(db_session, bar)
        shared_list = await make_shared_list(
            tasks=[test_task, bar], excluded=[dropped, kept]
        )

        await crud_shared_list.set_tasks(
            db_session, shared_list_id=shared_list.id, task_ids=[bar.id]
        )

        assert await crud_shared_list.excluded_ids(
            db_session, shared_list_id=shared_list.id
        ) == [kept.id]

    async def test_current_tasks_leave_out_a_task_now_elsewhere(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_draft_event: Event,
        test_user: User,
        test_task: Task,
        make_shared_list: SharedListFactory,
    ) -> None:
        bar = await _task(db_session, test_event, test_user, "Bar")
        shared_list = await make_shared_list(tasks=[bar, test_task])
        bar.event_id = test_draft_event.id
        await db_session.flush()

        assert await crud_shared_list.task_ids(
            db_session, shared_list_id=shared_list.id
        ) == [bar.id, test_task.id]
        assert await crud_shared_list.current_task_ids(
            db_session, shared_list=shared_list
        ) == [test_task.id]


@pytest.mark.asyncio
class TestLifecycle:
    async def test_detaching_a_task_takes_it_off_every_list(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        test_task: Task,
        make_shared_list: SharedListFactory,
    ) -> None:
        bar = await _task(db_session, test_event, test_user, "Bar")
        moving = await _shift(db_session, test_task)
        staying = await _shift(db_session, bar)
        one = await make_shared_list(tasks=[test_task, bar], excluded=[moving, staying])
        two = await make_shared_list(tasks=[test_task], excluded=[moving])

        await crud_shared_list.detach_task_from_lists(db_session, task_id=test_task.id)

        assert await crud_shared_list.task_ids(db_session, shared_list_id=one.id) == [
            bar.id
        ]
        assert await crud_shared_list.task_ids(db_session, shared_list_id=two.id) == []
        assert await crud_shared_list.excluded_ids(
            db_session, shared_list_id=one.id
        ) == [staying.id]
        assert (
            await crud_shared_list.excluded_ids(db_session, shared_list_id=two.id) == []
        )

    async def test_deleting_a_task_or_a_shift_takes_its_rows_along(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        test_task: Task,
        make_shared_list: SharedListFactory,
    ) -> None:
        bar = await _task(db_session, test_event, test_user, "Bar")
        shift = await _shift(db_session, test_task)
        shared_list = await make_shared_list(tasks=[test_task, bar], excluded=[shift])

        await db_session.delete(shift)
        await db_session.flush()
        assert (
            await crud_shared_list.excluded_ids(
                db_session, shared_list_id=shared_list.id
            )
            == []
        )

        await db_session.delete(bar)
        await db_session.flush()
        assert await crud_shared_list.task_ids(
            db_session, shared_list_id=shared_list.id
        ) == [test_task.id]

    async def test_deleting_the_event_takes_its_lists_and_leaves_the_guests(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """The contact address and the manage link go with the event at once.
        The task survives as an orphan, and with it the guest user and their
        booking, until retention finds them; the activity log has no foreign
        key, so no delete resets a quota."""
        shift = await _shift(db_session, test_task)
        excluded = await _shift(db_session, test_task, day=12)
        shared_list = await make_shared_list(excluded=[excluded])
        guest = await make_list_guest(
            shared_list, email="gast@example.org", shifts=[shift]
        )
        db_session.add(
            GuestActivityLog(
                kind="signup",
                address_hash="0" * 64,
                event_id=test_event.id,
                shared_list_id=shared_list.id,
                booking_id=guest.bookings[0].id,
            )
        )
        await db_session.flush()

        await db_session.delete(test_event)
        await db_session.flush()
        await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

        for model in (
            SharedList,
            SharedListTask,
            SharedListExcludedShift,
            SharedListGuest,
        ):
            count = await db_session.execute(select(func.count()).select_from(model))
            assert count.scalar_one() == 0, model
        booking = await db_session.execute(
            select(col(Booking.shift_id), col(Booking.shared_list_id)).where(
                col(Booking.user_id) == guest.user.id
            )
        )
        assert booking.one() == (shift.id, shared_list.id)
        logged = await db_session.execute(
            select(func.count()).select_from(GuestActivityLog)
        )
        assert logged.scalar_one() == 1

    async def test_shift_dates_move_the_closing_days_of_the_events_lists(
        self,
        db_session: AsyncSession,
        test_draft_event: Event,
        make_shared_list: SharedListFactory,
    ) -> None:
        dated = await make_shared_list(ends_mode="date", ends_on=dt.date(2026, 6, 12))
        undated = await make_shared_list()
        elsewhere = await make_shared_list(
            event=test_draft_event,
            tasks=[],
            ends_mode="date",
            ends_on=dt.date(2026, 6, 12),
        )

        await crud_shared_list.shift_ends_on(
            db_session, event_id=dated.event_id, delta=dt.timedelta(days=7)
        )

        for shared_list in (dated, undated, elsewhere):
            await db_session.refresh(shared_list)
        assert dated.ends_on == dt.date(2026, 6, 19)
        assert undated.ends_on is None
        assert elsewhere.ends_on == dt.date(2026, 6, 12)
