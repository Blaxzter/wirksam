import uuid
from collections import defaultdict
from collections.abc import Iterable
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User


class CRUDTaskManager:
    """The people in charge of tasks.

    Never commits; the request owns the transaction. Who may call what is
    decided in the routes through ``app.logic.permissions``, and these rows
    only count there while the person is still a member of the task's event.
    """

    async def is_manager(
        self,
        session: AsyncSession,
        *,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        row = await session.execute(
            select(col(TaskManager.id)).where(
                col(TaskManager.task_id) == task_id,
                col(TaskManager.user_id) == user_id,
            )
        )
        return row.first() is not None

    async def task_ids_for_user(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> list[uuid.UUID]:
        """Every task the user is in charge of, in any event.

        Callers combine this with an event scope; on its own it says nothing
        about membership.
        """
        rows = await session.execute(
            select(col(TaskManager.task_id)).where(col(TaskManager.user_id) == user_id)
        )
        return list(rows.scalars().all())

    async def managers_for_tasks(
        self,
        session: AsyncSession,
        *,
        task_ids: Iterable[uuid.UUID],
    ) -> dict[uuid.UUID, list[tuple[TaskManager, User]]]:
        """``{task_id: [(row, user), ...]}``, each list ordered by name."""
        ids = set(task_ids)
        if not ids:
            return {}
        rows = await session.execute(
            select(TaskManager, User)
            .join(User, col(User.id) == col(TaskManager.user_id))
            .where(col(TaskManager.task_id).in_(ids))
            .order_by(col(User.name), col(User.email))
        )
        out: dict[uuid.UUID, list[tuple[TaskManager, User]]] = defaultdict(list)
        for manager, user in rows.all():
            out[manager.task_id].append((manager, user))
        return dict(out)

    async def user_ids_for_task(
        self,
        session: AsyncSession,
        *,
        task_id: uuid.UUID,
    ) -> list[uuid.UUID]:
        rows = await session.execute(
            select(col(TaskManager.user_id)).where(col(TaskManager.task_id) == task_id)
        )
        return list(rows.scalars().all())

    async def add(
        self,
        session: AsyncSession,
        *,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
        added_by: User,
    ) -> TaskManager:
        """Insert one row and flush, so a duplicate surfaces as IntegrityError."""
        row = TaskManager(
            task_id=task_id,
            user_id=user_id,
            added_by_id=added_by.id,
            added_by_name=added_by.name or added_by.email,
        )
        session.add(row)
        await session.flush()
        return row

    async def remove(
        self,
        session: AsyncSession,
        *,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Delete one row. False when the person was not in charge."""
        result = cast(
            CursorResult[Any],
            await session.execute(
                delete(TaskManager).where(
                    col(TaskManager.task_id) == task_id,
                    col(TaskManager.user_id) == user_id,
                )
            ),
        )
        await session.flush()
        return result.rowcount > 0

    async def remove_all_for_task(
        self,
        session: AsyncSession,
        *,
        task_id: uuid.UUID,
    ) -> None:
        """Drop everyone in charge of a task, e.g. when it moves to another event."""
        await session.execute(
            delete(TaskManager).where(col(TaskManager.task_id) == task_id)
        )
        await session.flush()

    async def remove_user_from_event_tasks(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> None:
        """Drop every row of a user who left (or was removed from) an event.

        Without this, re-joining the event later would quietly restore a right
        nobody granted again. The same rule as for team rows
        (``crud.event_team.remove_user_from_event_teams``).
        """
        task_ids = select(col(Task.id)).where(col(Task.event_id) == event_id)
        await session.execute(
            delete(TaskManager).where(
                col(TaskManager.user_id) == user_id,
                col(TaskManager.task_id).in_(task_ids),
            )
        )
        await session.flush()

    async def rows_for_clone(
        self,
        session: AsyncSession,
        *,
        task_ids: Iterable[uuid.UUID],
        user_ids: Iterable[uuid.UUID],
    ) -> dict[uuid.UUID, list[TaskManager]]:
        """``{task_id: [row, ...]}`` for the people who come along into a clone."""
        tasks = set(task_ids)
        users = set(user_ids)
        if not tasks or not users:
            return {}
        rows = await session.execute(
            select(TaskManager).where(
                col(TaskManager.task_id).in_(tasks),
                col(TaskManager.user_id).in_(users),
            )
        )
        out: dict[uuid.UUID, list[TaskManager]] = defaultdict(list)
        for row in rows.scalars().all():
            out[row.task_id].append(row)
        return dict(out)


task_manager = CRUDTaskManager()
