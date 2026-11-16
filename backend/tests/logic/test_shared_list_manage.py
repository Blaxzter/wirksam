"""Pausing, resuming, ending and rotating a list, and editing what it offers
(``app.logic.shared_lists.manage``).

The transitions are pinned as a matrix of action and starting state on the
event's clock at 2026-06-10 12:00, the day before ``test_task``'s shifts. The
routes around them are in ``tests/api/routes/test_shared_lists.py``.
"""

import datetime as dt
from typing import Any, cast

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.shared_list import shared_list as crud_shared_list
from app.logic.shared_lists.manage import TransitionAction, transition, update
from app.models.booking import Booking
from app.models.event import Event
from app.models.shared_list import EndsMode, ListStatus, SharedList
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.shared_list import SharedListUpdate
from tests.fixtures.shared_lists import ListGuestFactory, SharedListFactory

NOW = dt.datetime(2026, 6, 10, 12, 0)
#: After every shift of ``test_task`` has started.
LATER = dt.datetime(2026, 6, 14, 12, 0)
STAMP = dt.datetime(2026, 6, 10, 10, 0)
YESTERDAY = NOW.date() - dt.timedelta(days=1)
DAYS = (dt.date(2026, 6, 11), dt.date(2026, 6, 12), dt.date(2026, 6, 13))


@pytest_asyncio.fixture
async def shifts(db_session: AsyncSession, test_task: Task) -> list[Shift]:
    out: list[Shift] = []
    for day in DAYS:
        shift = Shift(
            task_id=test_task.id,
            title=test_task.name,
            date=day,
            start_time=dt.time(10),
            max_bookings=2,
        )
        db_session.add(shift)
        out.append(shift)
    await db_session.flush()
    return out


def _code(exc: pytest.ExceptionInfo[HTTPException]) -> str:
    return cast(dict[str, Any], exc.value.detail)["code"]


async def _apply(
    db: AsyncSession,
    shared_list: SharedList,
    action: TransitionAction,
    event: Event,
    *,
    now_wall: dt.datetime = NOW,
) -> bool:
    return await transition(
        db, shared_list, action, event=event, now_utc=STAMP, now_wall=now_wall
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("shifts")
class TestTransitionMatrix:
    @pytest.mark.parametrize(
        ("status", "ends_mode", "ends_on", "action", "changed", "after"),
        [
            # pause: a live list only.
            ("live", "last_shift", None, "pause", True, "paused"),
            ("paused", "last_shift", None, "pause", False, "paused"),
            # resume: a paused or expired one; a live one stays.
            ("paused", "last_shift", None, "resume", True, "live"),
            ("live", "last_shift", None, "resume", False, "live"),
            ("paused", "manual", None, "resume", True, "live"),
            ("paused", "date", DAYS[1], "resume", True, "live"),
            # end: anything not ended, for good.
            ("live", "last_shift", None, "end", True, "ended"),
            ("paused", "last_shift", None, "end", True, "ended"),
            ("live", "date", YESTERDAY, "end", True, "ended"),
            ("ended", "last_shift", None, "end", False, "ended"),
            # rotate: anything not ended.
            ("live", "last_shift", None, "rotate", True, "live"),
            ("paused", "last_shift", None, "rotate", True, "paused"),
        ],
    )
    async def test_allowed(
        self,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        status: ListStatus,
        ends_mode: EndsMode,
        ends_on: dt.date | None,
        action: TransitionAction,
        changed: bool,
        after: ListStatus,
    ) -> None:
        shared_list = await make_shared_list(
            status=status, ends_mode=ends_mode, ends_on=ends_on
        )
        code = shared_list.code

        assert await _apply(db_session, shared_list, action, test_event) is changed

        assert shared_list.status == after
        assert (shared_list.code != code) is (action == "rotate")
        if changed and action == "pause":
            assert shared_list.paused_at == STAMP
        if changed and action == "resume":
            assert shared_list.paused_at is None
            assert (shared_list.ends_mode, shared_list.ends_on) == (ends_mode, ends_on)
        if changed and action == "end":
            assert shared_list.ended_at == STAMP
        if action == "rotate":
            assert shared_list.rotated_at == STAMP

    @pytest.mark.parametrize(
        ("status", "ends_mode", "ends_on", "action", "code"),
        [
            ("live", "date", YESTERDAY, "pause", "shared_list.not_live"),
            ("ended", "last_shift", None, "pause", "shared_list.ended"),
            ("ended", "last_shift", None, "resume", "shared_list.ended"),
            ("ended", "last_shift", None, "rotate", "shared_list.ended"),
        ],
    )
    async def test_refused(
        self,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        status: ListStatus,
        ends_mode: EndsMode,
        ends_on: dt.date | None,
        action: TransitionAction,
        code: str,
    ) -> None:
        shared_list = await make_shared_list(
            status=status, ends_mode=ends_mode, ends_on=ends_on
        )

        with pytest.raises(HTTPException) as exc:
            await _apply(db_session, shared_list, action, test_event)

        assert exc.value.status_code == 409
        assert _code(exc) == code
        assert shared_list.status == status

    @pytest.mark.parametrize("status", ["live", "paused"])
    async def test_resuming_after_the_closing_day_closes_with_the_last_shift(
        self,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        status: ListStatus,
    ) -> None:
        shared_list = await make_shared_list(
            status=status, ends_mode="date", ends_on=YESTERDAY
        )

        assert await _apply(db_session, shared_list, "resume", test_event) is True

        assert shared_list.status == "live"
        assert (shared_list.ends_mode, shared_list.ends_on) == ("last_shift", None)

    @pytest.mark.parametrize("status", ["live", "paused"])
    async def test_nothing_left_to_offer_cannot_reopen(
        self,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        status: ListStatus,
    ) -> None:
        shared_list = await make_shared_list(status=status)

        with pytest.raises(HTTPException) as exc:
            await _apply(db_session, shared_list, "resume", test_event, now_wall=LATER)

        assert _code(exc) == "shared_list.nothing_to_offer"
        assert shared_list.status == status

    async def test_a_list_closed_by_hand_reopens_with_nothing_left(
        self,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
    ) -> None:
        shared_list = await make_shared_list(status="paused", ends_mode="manual")

        assert (
            await _apply(db_session, shared_list, "resume", test_event, now_wall=LATER)
            is True
        )
        assert shared_list.status == "live"

    async def test_an_unpublished_event_reopens_nothing(
        self,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
    ) -> None:
        paused = await make_shared_list(status="paused")
        expired = await make_shared_list(ends_mode="manual")
        test_event.status = "draft"

        for shared_list in (paused, expired):
            with pytest.raises(HTTPException) as exc:
                await _apply(db_session, shared_list, "resume", test_event)
            assert _code(exc) == "shared_list.event_not_published"

    async def test_no_transition_touches_a_booking(
        self,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        test_event: Event,
        shifts: list[Shift],
    ) -> None:
        shared_list = await make_shared_list()
        guest = await make_list_guest(shared_list, shifts=shifts[:2])

        for action in ("pause", "resume", "rotate", "end"):
            await _apply(db_session, shared_list, action, test_event)

        statuses = await db_session.execute(
            select(col(Booking.status)).where(col(Booking.user_id) == guest.user.id)
        )
        assert list(statuses.scalars()) == ["confirmed", "confirmed"]


@pytest.mark.asyncio
class TestUpdate:
    async def test_a_new_closing_day_is_checked_against_what_the_list_can_offer(
        self,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        test_user: User,
        shifts: list[Shift],
    ) -> None:
        """A task unpublished since is left out, rather than blocking the edit."""
        draft = Task(
            name="Später",
            start_date=DAYS[0],
            end_date=DAYS[2],
            status="published",
            created_by_id=test_user.id,
            event_id=test_event.id,
        )
        db_session.add(draft)
        await db_session.flush()
        shared_list = await make_shared_list(tasks=[test_task, draft])
        draft.status = "draft"
        await db_session.flush()

        await update(
            db_session,
            shared_list,
            event=test_event,
            changes=SharedListUpdate(ends_mode="date", ends_on=DAYS[2]),
            now_wall=NOW,
        )

        assert (shared_list.ends_mode, shared_list.ends_on) == ("date", DAYS[2])

    async def test_a_list_with_nothing_left_to_offer_cannot_change_its_closing(
        self,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        shifts: list[Shift],
    ) -> None:
        shared_list = await make_shared_list()
        test_task.status = "draft"
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await update(
                db_session,
                shared_list,
                event=test_event,
                changes=SharedListUpdate(ends_mode="manual"),
                now_wall=NOW,
            )

        assert _code(exc) == "shared_list.no_shifts"
        assert shared_list.ends_mode == "last_shift"

    async def test_exclusions_stay_unless_the_edit_names_them(
        self,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_event: Event,
        test_task: Task,
        shifts: list[Shift],
    ) -> None:
        shared_list = await make_shared_list(excluded=shifts[:1])

        await update(
            db_session,
            shared_list,
            event=test_event,
            changes=SharedListUpdate(task_ids=[test_task.id], title="Neu"),
            now_wall=NOW,
        )
        kept = await crud_shared_list.excluded_ids(
            db_session, shared_list_id=shared_list.id
        )
        await update(
            db_session,
            shared_list,
            event=test_event,
            changes=SharedListUpdate(excluded_shift_ids=[]),
            now_wall=NOW,
        )
        cleared = await crud_shared_list.excluded_ids(
            db_session, shared_list_id=shared_list.id
        )

        assert shared_list.title == "Neu"
        assert kept == [shifts[0].id]
        assert cleared == []
