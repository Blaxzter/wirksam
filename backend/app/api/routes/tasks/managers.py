"""Naming and removing the people in charge of a task.

There is no list endpoint: ``TaskRead.managers`` is the list, and the editor
reloads the task after each change. What being in charge allows is decided in
``app.logic.permissions`` (``require_task_manager``).

Whoever is put in charge, or taken off, by someone else hears about it
(``task.manager_added`` / ``task.manager_removed``). The dispatchers are
imported by name so tests can replace them on this module.
"""

import uuid
from typing import NoReturn

from fastapi import APIRouter, BackgroundTasks, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.event_membership import event_membership as crud_membership
from app.crud.task import task as crud_task
from app.crud.task_manager import task_manager as crud_task_manager
from app.crud.user import user as crud_user
from app.logic.notifications.triggers import (
    dispatch_task_manager_added,
    dispatch_task_manager_removed,
)
from app.logic.permissions import require_event_role
from app.models.task import Task
from app.schemas.task_manager import TaskManagerAdd, TaskManagerBrief

router = APIRouter()


async def _get_task(session: DBDep, task_id: uuid.UUID) -> Task:
    task = await crud_task.get(session, task_id)
    if task is None:
        raise_problem(404, code="task.not_found", detail="Task not found")
    return task


@router.post(
    "/{task_id}/managers",
    response_model=TaskManagerBrief,
    status_code=status.HTTP_201_CREATED,
)
async def add_task_manager(
    task_id: uuid.UUID,
    body: TaskManagerAdd,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> TaskManagerBrief:
    """Put an event member in charge of this task. Event admins only.

    The person is told, unless they named themselves.
    """
    task = await _get_task(session, task_id)
    await require_event_role(current_user, session, task.event_id)
    # Locked, not just read: a leave running alongside then waits for this
    # grant and removes it, rather than missing it and leaving it to come
    # back when the person re-joins.
    members = (
        await crud_membership.lock_member_ids(
            session, event_id=task.event_id, user_ids=[body.user_id]
        )
        if task.event_id is not None
        else set[uuid.UUID]()
    )
    if body.user_id not in members:
        raise_problem(
            422,
            code="task.manager_not_event_member",
            detail="Only members of this event can be put in charge of its tasks",
        )
    if await crud_task_manager.is_manager(
        session, task_id=task.id, user_id=body.user_id
    ):
        _already()
    try:
        async with session.begin_nested():
            await crud_task_manager.add(
                session, task_id=task.id, user_id=body.user_id, added_by=current_user
            )
    except IntegrityError:
        # Someone else added the same person between the check and the insert.
        _already()
    user = await crud_user.get(session, id=body.user_id, raise_404_error=True)
    if body.user_id != current_user.id:
        background_tasks.add_task(
            dispatch_task_manager_added,
            task_id=task.id,
            user_ids=[body.user_id],
            actor_id=current_user.id,
        )
    return TaskManagerBrief(
        user_id=user.id, name=user.name, avatar_etag=user.avatar_etag
    )


def _already() -> NoReturn:
    raise_problem(
        409,
        code="task.manager_already",
        detail="That person is already in charge of this task",
    )


@router.delete("/{task_id}/managers/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_task_manager(
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> None:
    """Remove someone from charge of this task.

    Event admins may remove anyone, and that person is told; a person in
    charge may step down, which tells nobody.
    """
    task = await _get_task(session, task_id)
    if user_id != current_user.id:
        await require_event_role(current_user, session, task.event_id)
    if not await crud_task_manager.remove(session, task_id=task.id, user_id=user_id):
        raise_problem(
            404,
            code="task.manager_not_found",
            detail="That person is not in charge of this task",
        )
    if user_id != current_user.id:
        background_tasks.add_task(
            dispatch_task_manager_removed,
            task_id=task.id,
            user_id=user_id,
            actor_id=current_user.id,
        )
