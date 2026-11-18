"""The shared-list gates in ``app.logic.permissions``.

Who sees a list and who may change it depends on the list's *current* tasks and
on who is in charge of them right now, so these pin the edges directly: a stale
row of someone who left, a task that moved, an empty set of managed tasks, a
sandbox the superadmin must not see, and the event setting that stops people
in charge from sharing.
"""

import datetime as dt
from typing import Any, cast, get_args

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic.permissions import (
    ManageAction,
    require_shared_list_manager,
    require_shared_list_tasks,
    require_shared_list_visible,
    shared_list_access,
    shared_list_scope,
)
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shared_list import SharedList
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from tests.fixtures.sandbox import SandboxSetup
from tests.fixtures.shared_lists import SharedListFactory


async def _put_in_charge(db: AsyncSession, task: Task, user: User) -> None:
    db.add(TaskManager(task_id=task.id, user_id=user.id))
    await db.flush()


async def _task(db: AsyncSession, event: Event, creator: User, name: str) -> Task:
    task = Task(
        name=name,
        start_date=dt.date(2026, 6, 11),
        end_date=dt.date(2026, 6, 11),
        status="published",
        created_by_id=creator.id,
        event_id=event.id,
    )
    db.add(task)
    await db.flush()
    return task


async def _superadmin(db: AsyncSession) -> User:
    """A superadmin with no membership anywhere."""
    user = User(subject="local|root-x", email="root-x@example.com", roles=["admin"])
    db.add(user)
    await db.flush()
    return user


def _problem(exc: pytest.ExceptionInfo[HTTPException]) -> dict[str, Any]:
    return cast(dict[str, Any], exc.value.detail)


@pytest_asyncio.fixture
async def bar(db_session: AsyncSession, test_event: Event, test_user: User) -> Task:
    """A second published task in ``test_event``."""
    return await _task(db_session, test_event, test_user, "Bar")


@pytest.mark.asyncio
class TestSharedListAccess:
    async def test_event_admin_is_admin(
        self,
        db_session: AsyncSession,
        test_event_admin_user: User,
        make_shared_list: SharedListFactory,
    ) -> None:
        shared_list = await make_shared_list()
        assert (
            await shared_list_access(test_event_admin_user, db_session, shared_list)
            == "admin"
        )

    async def test_superadmin_is_admin_without_a_membership(
        self, db_session: AsyncSession, make_shared_list: SharedListFactory
    ) -> None:
        root = await _superadmin(db_session)
        shared_list = await make_shared_list()
        assert await shared_list_access(root, db_session, shared_list) == "admin"

    async def test_in_charge_of_every_task_is_manager(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_task: Task,
        bar: Task,
        make_shared_list: SharedListFactory,
    ) -> None:
        await _put_in_charge(db_session, test_task, test_user)
        await _put_in_charge(db_session, bar, test_user)
        shared_list = await make_shared_list(tasks=[test_task, bar])
        assert await shared_list_access(test_user, db_session, shared_list) == "manager"

    async def test_in_charge_of_some_tasks_is_viewer(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_task: Task,
        bar: Task,
        make_shared_list: SharedListFactory,
    ) -> None:
        await _put_in_charge(db_session, test_task, test_user)
        shared_list = await make_shared_list(tasks=[test_task, bar])
        assert await shared_list_access(test_user, db_session, shared_list) == "viewer"

    async def test_in_charge_of_none_of_its_tasks_sees_nothing(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_task: Task,
        bar: Task,
        make_shared_list: SharedListFactory,
    ) -> None:
        await _put_in_charge(db_session, test_task, test_user)
        shared_list = await make_shared_list(tasks=[bar])
        assert await shared_list_access(test_user, db_session, shared_list) is None

    async def test_a_plain_member_sees_nothing(
        self,
        db_session: AsyncSession,
        test_user: User,
        make_shared_list: SharedListFactory,
    ) -> None:
        shared_list = await make_shared_list()
        assert await shared_list_access(test_user, db_session, shared_list) is None

    async def test_a_stale_row_after_leaving_grants_nothing(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_event: Event,
        test_task: Task,
        make_shared_list: SharedListFactory,
    ) -> None:
        await _put_in_charge(db_session, test_task, test_user)
        shared_list = await make_shared_list()
        await db_session.execute(
            delete(EventMembership).where(
                col(EventMembership.user_id) == test_user.id,
                col(EventMembership.event_id) == test_event.id,
            )
        )
        assert await shared_list_access(test_user, db_session, shared_list) is None

    async def test_a_task_moved_to_another_event_no_longer_counts(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_task: Task,
        bar: Task,
        test_draft_event: Event,
        make_shared_list: SharedListFactory,
    ) -> None:
        """The list's current tasks are those still in its event: once ``bar``
        has moved, being in charge of ``test_task`` is being in charge of all."""
        await _put_in_charge(db_session, test_task, test_user)
        shared_list = await make_shared_list(tasks=[test_task, bar])
        bar.event_id = test_draft_event.id
        await db_session.flush()
        assert await shared_list_access(test_user, db_session, shared_list) == "manager"

    async def test_a_list_without_current_tasks_is_the_admins_alone(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_event_admin_user: User,
        test_task: Task,
        make_shared_list: SharedListFactory,
    ) -> None:
        await _put_in_charge(db_session, test_task, test_user)
        shared_list = await make_shared_list(tasks=[])
        assert await shared_list_access(test_user, db_session, shared_list) is None
        assert (
            await shared_list_access(test_event_admin_user, db_session, shared_list)
            == "admin"
        )

    async def test_nobody_else_sees_a_list_of_a_sandbox(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
        test_sandbox: SandboxSetup,
        make_shared_list: SharedListFactory,
    ) -> None:
        """Before the role: ``get_event_role`` reports the superadmin as owner."""
        shared_list = await make_shared_list(event=test_sandbox.event, tasks=[])
        assert (
            await shared_list_access(test_admin_user, db_session, shared_list) is None
        )


@pytest.mark.asyncio
class TestRequireSharedListVisible:
    async def test_returns_the_access(
        self,
        db_session: AsyncSession,
        test_event_admin_user: User,
        test_shared_list: SharedList,
    ) -> None:
        assert (
            await require_shared_list_visible(
                test_event_admin_user, db_session, test_shared_list
            )
            == "admin"
        )

    async def test_404_when_invisible(
        self, db_session: AsyncSession, test_user: User, test_shared_list: SharedList
    ) -> None:
        with pytest.raises(HTTPException) as exc:
            await require_shared_list_visible(test_user, db_session, test_shared_list)
        assert exc.value.status_code == 404
        assert _problem(exc)["code"] == "shared_list.not_found"


@pytest.mark.asyncio
class TestRequireSharedListManager:
    @pytest.mark.parametrize("action", get_args(ManageAction))
    async def test_a_viewer_may_change_nothing(
        self,
        action: ManageAction,
        db_session: AsyncSession,
        test_user: User,
        test_task: Task,
        bar: Task,
        make_shared_list: SharedListFactory,
    ) -> None:
        await _put_in_charge(db_session, test_task, test_user)
        shared_list = await make_shared_list(tasks=[test_task, bar])
        with pytest.raises(HTTPException) as exc:
            await require_shared_list_manager(
                test_user, db_session, shared_list, action
            )
        assert exc.value.status_code == 403
        assert _problem(exc)["code"] == "shared_list.forbidden"

    async def test_404_for_someone_who_cannot_see_it(
        self,
        db_session: AsyncSession,
        test_outsider_user: User,
        test_shared_list: SharedList,
    ) -> None:
        with pytest.raises(HTTPException) as exc:
            await require_shared_list_manager(
                test_outsider_user, db_session, test_shared_list, "pause"
            )
        assert exc.value.status_code == 404

    @pytest.mark.parametrize("action", get_args(ManageAction))
    async def test_a_manager_may_do_everything_while_sharing_is_on(
        self,
        action: ManageAction,
        db_session: AsyncSession,
        test_user: User,
        test_task: Task,
        test_shared_list: SharedList,
    ) -> None:
        await _put_in_charge(db_session, test_task, test_user)
        assert (
            await require_shared_list_manager(
                test_user, db_session, test_shared_list, action
            )
            == "manager"
        )

    @pytest.mark.parametrize(
        ("action", "allowed"),
        [
            ("edit", False),
            ("resume", False),
            ("rotate", False),
            ("pause", True),
            ("end", True),
        ],
    )
    async def test_with_sharing_off_a_manager_may_only_stop_it(
        self,
        action: ManageAction,
        allowed: bool,
        db_session: AsyncSession,
        test_user: User,
        test_event: Event,
        test_task: Task,
        test_shared_list: SharedList,
    ) -> None:
        await _put_in_charge(db_session, test_task, test_user)
        test_event.managers_share_lists = False
        await db_session.flush()
        if allowed:
            assert (
                await require_shared_list_manager(
                    test_user, db_session, test_shared_list, action
                )
                == "manager"
            )
            return
        with pytest.raises(HTTPException) as exc:
            await require_shared_list_manager(
                test_user, db_session, test_shared_list, action
            )
        assert exc.value.status_code == 403
        assert _problem(exc)["code"] == "shared_list.managers_disabled"

    @pytest.mark.parametrize("action", get_args(ManageAction))
    async def test_an_admin_always_passes(
        self,
        action: ManageAction,
        db_session: AsyncSession,
        test_event_admin_user: User,
        test_event: Event,
        test_shared_list: SharedList,
    ) -> None:
        test_event.managers_share_lists = False
        await db_session.flush()
        assert (
            await require_shared_list_manager(
                test_event_admin_user, db_session, test_shared_list, action
            )
            == "admin"
        )


@pytest.mark.asyncio
class TestSharedListScope:
    async def test_an_admin_is_unrestricted(
        self,
        db_session: AsyncSession,
        test_event_admin_user: User,
        test_event: Event,
    ) -> None:
        scope = await shared_list_scope(test_event_admin_user, db_session, test_event)
        assert (scope.is_admin, scope.managers_share_lists) == (True, True)

    async def test_a_person_in_charge_gets_their_tasks_of_this_event(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_event: Event,
        test_draft_event: Event,
        test_task: Task,
    ) -> None:
        elsewhere = await _task(db_session, test_draft_event, test_user, "Woanders")
        await _put_in_charge(db_session, test_task, test_user)
        await _put_in_charge(db_session, elsewhere, test_user)
        scope = await shared_list_scope(test_user, db_session, test_event)
        assert not scope.is_admin
        assert scope.managed_task_ids == frozenset({test_task.id})

    async def test_a_member_in_charge_of_nothing_is_refused_not_unrestricted(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_event: Event,
        test_draft_event: Event,
    ) -> None:
        """An empty set of managed tasks means "nothing": 403, never a scope
        that a filter could read as "everything". Being in charge in another
        event does not count here."""
        elsewhere = await _task(db_session, test_draft_event, test_user, "Woanders")
        await _put_in_charge(db_session, elsewhere, test_user)
        with pytest.raises(HTTPException) as exc:
            await shared_list_scope(test_user, db_session, test_event)
        assert exc.value.status_code == 403
        assert _problem(exc)["code"] == "shared_list.forbidden"

    async def test_404_for_someone_outside_the_event(
        self,
        db_session: AsyncSession,
        test_outsider_user: User,
        test_event: Event,
    ) -> None:
        with pytest.raises(HTTPException) as exc:
            await shared_list_scope(test_outsider_user, db_session, test_event)
        assert exc.value.status_code == 404
        assert _problem(exc)["code"] == "event.not_found"

    async def test_a_sandbox_is_404_even_for_the_superadmin(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
        test_sandbox: SandboxSetup,
    ) -> None:
        with pytest.raises(HTTPException) as exc:
            await shared_list_scope(test_admin_user, db_session, test_sandbox.event)
        assert exc.value.status_code == 404
        assert _problem(exc)["code"] == "event.not_found"


@pytest.mark.asyncio
class TestRequireSharedListTasks:
    async def test_an_admin_may_use_any_task(
        self,
        db_session: AsyncSession,
        test_event_admin_user: User,
        test_event: Event,
        test_task: Task,
        bar: Task,
    ) -> None:
        assert (
            await require_shared_list_tasks(
                test_event_admin_user, db_session, test_event, [test_task.id, bar.id]
            )
            == "admin"
        )

    async def test_a_person_in_charge_may_use_their_own(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_event: Event,
        test_task: Task,
    ) -> None:
        await _put_in_charge(db_session, test_task, test_user)
        assert (
            await require_shared_list_tasks(
                test_user, db_session, test_event, [test_task.id]
            )
            == "manager"
        )

    async def test_names_the_tasks_they_are_not_in_charge_of(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_event: Event,
        test_task: Task,
        bar: Task,
    ) -> None:
        await _put_in_charge(db_session, test_task, test_user)
        with pytest.raises(HTTPException) as exc:
            await require_shared_list_tasks(
                test_user, db_session, test_event, [test_task.id, bar.id, bar.id]
            )
        assert exc.value.status_code == 403
        problem = _problem(exc)
        assert problem["code"] == "shared_list.tasks_forbidden"
        assert problem["extensions"] == {"task_ids": [str(bar.id)]}

    async def test_with_sharing_off_a_person_in_charge_may_not(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_event: Event,
        test_task: Task,
    ) -> None:
        await _put_in_charge(db_session, test_task, test_user)
        test_event.managers_share_lists = False
        await db_session.flush()
        with pytest.raises(HTTPException) as exc:
            await require_shared_list_tasks(
                test_user, db_session, test_event, [test_task.id]
            )
        assert exc.value.status_code == 403
        assert _problem(exc)["code"] == "shared_list.managers_disabled"

    async def test_404_for_a_non_member(
        self,
        db_session: AsyncSession,
        test_outsider_user: User,
        test_event: Event,
        test_task: Task,
    ) -> None:
        with pytest.raises(HTTPException) as exc:
            await require_shared_list_tasks(
                test_outsider_user, db_session, test_event, [test_task.id]
            )
        assert exc.value.status_code == 404
        assert _problem(exc)["code"] == "event.not_found"

    async def test_a_sandbox_is_404_even_for_the_superadmin(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
        test_sandbox: SandboxSetup,
    ) -> None:
        with pytest.raises(HTTPException) as exc:
            await require_shared_list_tasks(
                test_admin_user, db_session, test_sandbox.event, []
            )
        assert exc.value.status_code == 404
