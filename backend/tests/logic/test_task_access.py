"""The gates for people in charge of a task (``app.logic.permissions``).

``task_access`` decides who may edit a task, ``require_task_visible`` who may
read it, and ``check_shift_history`` what a person in charge may not do to a
booked shift's past. The route tests in ``test_task_managers.py`` cover the
same rules through the API; these pin the edge cases directly.
"""

import datetime as dt
import uuid
from typing import Any, cast

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic.permissions import (
    TaskAccess,
    check_shift_history,
    require_task_visible,
    task_access,
)
from app.models.booking import Booking
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shift import Shift
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from tests.fixtures.sandbox import SandboxSetup


async def _put_in_charge(db: AsyncSession, task: Task, user: User) -> None:
    db.add(TaskManager(task_id=task.id, user_id=user.id))
    await db.flush()


async def _other_task(db: AsyncSession, event: Event, creator: User) -> Task:
    task = Task(
        name="Garderobe",
        start_date=dt.date(2026, 6, 11),
        end_date=dt.date(2026, 6, 11),
        status="published",
        created_by_id=creator.id,
        event_id=event.id,
    )
    db.add(task)
    await db.flush()
    return task


def _problem_code(exc: HTTPException) -> str:
    """The ``code`` of a problem raised through ``raise_problem``."""
    return str(cast(dict[str, Any], exc.detail)["code"])


def _code(exc: pytest.ExceptionInfo[HTTPException]) -> str:
    return _problem_code(exc.value)


@pytest.mark.asyncio
class TestTaskAccess:
    async def test_event_admin_is_admin(
        self, db_session: AsyncSession, test_task: Task, test_event_admin_user: User
    ) -> None:
        assert (
            await task_access(test_event_admin_user, db_session, test_task) == "admin"
        )

    async def test_owner_is_admin(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_event: Event,
    ) -> None:
        owner = User(subject="local|owner-x", email="owner-x@example.com", roles=[])
        db_session.add(owner)
        await db_session.flush()
        db_session.add(
            EventMembership(user_id=owner.id, event_id=test_event.id, role="owner")
        )
        await db_session.flush()
        assert await task_access(owner, db_session, test_task) == "admin"

    async def test_superadmin_is_admin(
        self, db_session: AsyncSession, test_task: Task, test_admin_user: User
    ) -> None:
        assert await task_access(test_admin_user, db_session, test_task) == "admin"

    async def test_person_in_charge_is_manager(
        self, db_session: AsyncSession, test_task: Task, test_user: User
    ) -> None:
        await _put_in_charge(db_session, test_task, test_user)
        assert await task_access(test_user, db_session, test_task) == "manager"

    async def test_plain_member_is_nobody(
        self, db_session: AsyncSession, test_task: Task, test_user: User
    ) -> None:
        assert await task_access(test_user, db_session, test_task) is None

    async def test_a_stale_row_of_someone_who_left_grants_nothing(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_outsider_user: User,
    ) -> None:
        """A row inserted by hand for a non-member: membership comes first."""
        await _put_in_charge(db_session, test_task, test_outsider_user)
        assert await task_access(test_outsider_user, db_session, test_task) is None

    async def test_in_charge_in_another_event_is_nobody_here(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
        test_draft_event: Event,
    ) -> None:
        elsewhere = await _other_task(db_session, test_draft_event, test_user)
        await _put_in_charge(db_session, elsewhere, test_user)
        assert await task_access(test_user, db_session, test_task) is None

    async def test_in_charge_of_a_sibling_task_is_nobody_here(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
        test_event: Event,
    ) -> None:
        sibling = await _other_task(db_session, test_event, test_user)
        await _put_in_charge(db_session, sibling, test_user)
        assert await task_access(test_user, db_session, sibling) == "manager"
        assert await task_access(test_user, db_session, test_task) is None

    async def test_an_orphan_task_is_the_superadmins_only(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
        test_admin_user: User,
    ) -> None:
        await _put_in_charge(db_session, test_task, test_user)
        test_task.event_id = None
        db_session.add(test_task)
        await db_session.flush()
        assert await task_access(test_user, db_session, test_task) is None
        assert await task_access(test_admin_user, db_session, test_task) == "admin"


@pytest.mark.asyncio
class TestRequireTaskVisible:
    async def test_a_draft_is_hidden_from_a_member(
        self, db_session: AsyncSession, test_draft_task: Task, test_user: User
    ) -> None:
        with pytest.raises(HTTPException) as exc:
            await require_task_visible(test_user, db_session, test_draft_task)
        assert exc.value.status_code == 403
        assert _code(exc) == "task.not_published"

    async def test_a_draft_is_open_to_its_person_in_charge(
        self, db_session: AsyncSession, test_draft_task: Task, test_user: User
    ) -> None:
        await _put_in_charge(db_session, test_draft_task, test_user)
        assert await require_task_visible(test_user, db_session, test_draft_task) == (
            "member"
        )

    async def test_a_booker_reopens_their_shift_of_an_archived_task(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_shift: Shift,
        test_user: User,
    ) -> None:
        test_task.status = "archived"
        db_session.add(test_task)
        db_session.add(
            Booking(shift_id=test_shift.id, user_id=test_user.id, status="cancelled")
        )
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await require_task_visible(test_user, db_session, test_task)
        assert _code(exc) == "task.not_published"
        # Any status counts: a cancelled booking still opens the shift.
        assert (
            await require_task_visible(
                test_user, db_session, test_task, booked_shift_id=test_shift.id
            )
            == "member"
        )

    async def test_a_member_without_a_booking_stays_out(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_shift: Shift,
        test_event: Event,
    ) -> None:
        member = User(subject="local|member-y", email="member-y@example.com", roles=[])
        db_session.add(member)
        await db_session.flush()
        db_session.add(
            EventMembership(user_id=member.id, event_id=test_event.id, role="member")
        )
        test_task.status = "archived"
        db_session.add(test_task)
        await db_session.flush()
        with pytest.raises(HTTPException) as exc:
            await require_task_visible(
                member, db_session, test_task, booked_shift_id=test_shift.id
            )
        assert exc.value.status_code == 403

    async def test_an_outsider_gets_404(
        self, db_session: AsyncSession, test_task: Task, test_outsider_user: User
    ) -> None:
        with pytest.raises(HTTPException) as exc:
            await require_task_visible(test_outsider_user, db_session, test_task)
        assert exc.value.status_code == 404
        assert _code(exc) == "task.not_found"

    async def test_a_sandbox_task_is_404_for_the_superadmin(
        self,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
        test_admin_user: User,
    ) -> None:
        task = (
            (
                await db_session.execute(
                    select(Task).where(col(Task.event_id) == test_sandbox.event.id)
                )
            )
            .scalars()
            .first()
        )
        assert task is not None
        with pytest.raises(HTTPException) as exc:
            await require_task_visible(test_admin_user, db_session, task)
        assert exc.value.status_code == 404
        # Its guest reads it.
        assert await require_task_visible(test_sandbox.guest, db_session, task)


# ── The shift history rule ────────────────────────────────────────

NOW = dt.datetime(2026, 6, 11, 10, 0)


def _shift(
    date: dt.date = dt.date(2026, 6, 11),
    start: dt.time | None = dt.time(8, 0),
    end: dt.time | None = dt.time(12, 0),
) -> Shift:
    return Shift(
        task_id=uuid.uuid4(),
        title="Theke",
        date=date,
        start_time=start,
        end_time=end,
    )


def _refused(access: TaskAccess, **kwargs: object) -> bool:
    try:
        check_shift_history(access, now=NOW, **kwargs)  # pyright: ignore[reportArgumentType]
    except HTTPException as exc:
        assert exc.status_code == 403
        assert _problem_code(exc) == "task.shift_history_admin_only"
        return True
    return False


class TestCheckShiftHistory:
    def test_an_admin_always_passes(self) -> None:
        running = _shift()
        assert not _refused("admin", before=running, has_bookings=True, deleting=True)
        assert not _refused(
            "admin",
            before=running,
            has_bookings=True,
            new_date=dt.date(2026, 6, 1),
        )

    def test_deleting_a_started_booked_shift_is_refused(self) -> None:
        assert _refused("manager", before=_shift(), has_bookings=True, deleting=True)

    def test_deleting_a_started_shift_nobody_booked_passes(self) -> None:
        assert not _refused(
            "manager", before=_shift(), has_bookings=False, deleting=True
        )

    def test_deleting_a_future_booked_shift_passes(self) -> None:
        future = _shift(date=dt.date(2026, 6, 12))
        assert not _refused("manager", before=future, has_bookings=True, deleting=True)

    def test_an_untimed_shift_has_started_at_midnight(self) -> None:
        untimed = _shift(start=None, end=None)
        assert _refused("manager", before=untimed, has_bookings=True, deleting=True)

    def test_re_dating_or_re_starting_a_started_booked_shift_is_refused(
        self,
    ) -> None:
        assert _refused(
            "manager",
            before=_shift(),
            has_bookings=True,
            new_date=dt.date(2026, 6, 12),
        )
        assert _refused(
            "manager", before=_shift(), has_bookings=True, new_start=dt.time(9, 0)
        )

    def test_extending_a_running_booked_shift_passes(self) -> None:
        """'We're staying an hour longer.'"""
        assert not _refused(
            "manager", before=_shift(), has_bookings=True, new_end=dt.time(13, 0)
        )

    def test_moving_that_end_to_before_now_is_refused(self) -> None:
        assert _refused(
            "manager", before=_shift(), has_bookings=True, new_end=dt.time(9, 30)
        )
        assert _refused(
            "manager", before=_shift(), has_bookings=True, new_end=dt.time(10, 0)
        )

    def test_moving_a_future_booked_shift_into_the_past_is_refused(self) -> None:
        future = _shift(date=dt.date(2026, 6, 12))
        assert _refused(
            "manager",
            before=future,
            has_bookings=True,
            new_date=dt.date(2026, 6, 10),
        )

    def test_moving_a_future_booked_shift_within_the_future_passes(self) -> None:
        future = _shift(date=dt.date(2026, 6, 12))
        assert not _refused(
            "manager",
            before=future,
            has_bookings=True,
            new_date=dt.date(2026, 6, 13),
            new_start=dt.time(14, 0),
            new_end=dt.time(18, 0),
        )

    def test_the_end_of_a_finished_booked_shift_stays_put(self) -> None:
        """Even moving it later would take back hours already worked."""
        finished = _shift(start=dt.time(6, 0), end=dt.time(9, 0))
        assert _refused(
            "manager", before=finished, has_bookings=True, new_end=dt.time(11, 0)
        )

    def test_sending_the_current_times_again_changes_nothing(self) -> None:
        """A form that always sends every field must not trip the rule."""
        finished = _shift(start=dt.time(6, 0), end=dt.time(9, 0))
        assert not _refused(
            "manager",
            before=finished,
            has_bookings=True,
            new_date=finished.date,
            new_start=finished.start_time,
            new_end=finished.end_time,
        )

    def test_clearing_the_end_time_of_a_running_shift_counts_as_a_change(
        self,
    ) -> None:
        """None is a value here, not "unchanged": the shift now runs all day."""
        assert not _refused("manager", before=_shift(), has_bookings=True, new_end=None)
        finished = _shift(start=dt.time(6, 0), end=dt.time(9, 0))
        assert _refused("manager", before=finished, has_bookings=True, new_end=None)
