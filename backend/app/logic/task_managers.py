"""The viewer-relative "people in charge" fields on task reads.

``TaskRead.can_manage`` and ``TaskRead.managers`` are worked out here for a
whole page of tasks in a fixed number of queries: one for every task's people
in charge, and one role lookup per distinct event (as ``logic.teams`` does for
the team locks). ``can_manage`` is what :func:`app.logic.permissions.task_access`
would decide for each task.
"""

import uuid
from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.task_manager import task_manager as crud_task_manager
from app.logic.permissions import get_event_role, role_at_least
from app.logic.teams import TeamLock, mark_task_locks
from app.models.user import User
from app.schemas.event_membership import EventRole
from app.schemas.event_team import TeamMemberStatus
from app.schemas.task_manager import TaskManagerBrief


class _TaskAccessEntry(Protocol):
    id: uuid.UUID
    event_id: uuid.UUID | None
    can_manage: bool
    managers: list[TaskManagerBrief]


class _TaskReadEntry(_TaskAccessEntry, Protocol):
    team_name: str | None
    team_requires_approval: bool | None
    my_team_status: TeamMemberStatus | None
    locked_by_team: bool


async def mark_task_access(
    session: AsyncSession, user: User, reads: Sequence[_TaskAccessEntry]
) -> None:
    """Fill ``can_manage`` and ``managers`` on task reads."""
    if not reads:
        return
    managers = await crud_task_manager.managers_for_tasks(
        session, task_ids=(r.id for r in reads)
    )
    roles: dict[uuid.UUID | None, EventRole | None] = {}
    for event_id in {r.event_id for r in reads}:
        roles[event_id] = await get_event_role(user, session, event_id)
    for read in reads:
        rows = managers.get(read.id, [])
        read.managers = [
            TaskManagerBrief(user_id=u.id, name=u.name, avatar_etag=u.avatar_etag)
            for _, u in rows
        ]
        role = roles[read.event_id]
        read.can_manage = role_at_least(role, "admin") or (
            # A member of the event, and in charge of this very task.
            role is not None and any(u.id == user.id for _, u in rows)
        )


async def decorate_task_reads(
    session: AsyncSession, user: User, reads: Sequence[_TaskReadEntry]
) -> dict[uuid.UUID, TeamLock]:
    """Everything viewer-relative on task reads: team locks and access.

    Returns the team locks, like :func:`app.logic.teams.mark_task_locks`.
    """
    locks = await mark_task_locks(session, user, reads)
    await mark_task_access(session, user, reads)
    return locks
