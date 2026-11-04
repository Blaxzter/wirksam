"""The viewer-relative "people in charge" fields on task reads.

``TaskRead.can_manage``, ``TaskRead.can_manage_shifts``, ``TaskRead.managers``
and ``TaskRead.can_redeem`` are worked out here for a whole page of tasks in a
fixed number of queries: one for every task's people in charge, one role lookup
per distinct event (as ``logic.teams`` does for the team locks), one for the
events' voucher-shift setting when the caller is in charge of a task that earns
vouchers, and one for the caller's running shifts at the voucher points they
cannot manage. ``can_manage`` is what
:func:`app.logic.permissions.task_access` would decide for each task,
``can_manage_shifts`` what :func:`app.logic.permissions.require_shift_editor`
would, and ``can_redeem`` what
:func:`app.logic.permissions.voucher_redeemer_kind` would, for a task that is a
point.
"""

import uuid
from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.event import event as crud_event
from app.crud.task_manager import task_manager as crud_task_manager
from app.logic import clock
from app.logic.permissions import (
    TaskAccess,
    get_event_role,
    on_shift_task_ids,
    role_at_least,
    voucher_shifts_locked,
)
from app.logic.teams import TeamLock, mark_task_locks
from app.models.event import Event
from app.models.user import User
from app.schemas.event_membership import EventRole
from app.schemas.event_team import TeamMemberStatus
from app.schemas.task import TaskStatus
from app.schemas.task_manager import TaskManagerBrief


class _TaskAccessEntry(Protocol):
    id: uuid.UUID
    event_id: uuid.UUID | None
    status: TaskStatus
    can_manage: bool
    can_manage_shifts: bool
    managers: list[TaskManagerBrief]
    vouchers_per_shift: int
    is_voucher_point: bool
    can_redeem: bool


class _TaskReadEntry(_TaskAccessEntry, Protocol):
    team_name: str | None
    team_requires_approval: bool | None
    my_team_status: TeamMemberStatus | None
    locked_by_team: bool


async def mark_task_access(
    session: AsyncSession, user: User, reads: Sequence[_TaskAccessEntry]
) -> None:
    """Fill ``can_manage``, ``can_manage_shifts``, ``managers`` and
    ``can_redeem`` on task reads."""
    if not reads:
        return
    managers = await crud_task_manager.managers_for_tasks(
        session, task_ids=(r.id for r in reads)
    )
    roles: dict[uuid.UUID | None, EventRole | None] = {}
    for event_id in {r.event_id for r in reads}:
        roles[event_id] = await get_event_role(user, session, event_id)
    access: dict[uuid.UUID, TaskAccess | None] = {}
    for read in reads:
        rows = managers.get(read.id, [])
        read.managers = [
            TaskManagerBrief(user_id=u.id, name=u.name, avatar_etag=u.avatar_etag)
            for _, u in rows
        ]
        role = roles[read.event_id]
        access[read.id] = (
            "admin"
            if role_at_least(role, "admin")
            # A member of the event, and in charge of this very task.
            else "manager"
            if role is not None and any(u.id == user.id for _, u in rows)
            else None
        )
        read.can_manage = access[read.id] is not None
        read.can_redeem = (
            read.is_voucher_point and read.can_manage and read.status != "archived"
        )

    # The events' voucher-shift setting decides only for a person in charge
    # of a task that earns vouchers; one query for all of them.
    rule_event_ids = {
        r.event_id
        for r in reads
        if access[r.id] == "manager"
        and r.vouchers_per_shift > 0
        and r.event_id is not None
    }
    events: dict[uuid.UUID | None, Event] = {}
    if rule_event_ids:
        result = await session.execute(
            select(Event).where(col(Event.id).in_(rule_event_ids))
        )
        events = {e.id: e for e in result.scalars()}
    for read in reads:
        read.can_manage_shifts = read.can_manage and not voucher_shifts_locked(
            access[read.id], read, events.get(read.event_id)
        )

    # The points the caller cannot manage: redeeming there needs a running
    # shift, which one query answers for all of them.
    on_shift_candidates = [
        r.id
        for r in reads
        if r.is_voucher_point
        and r.status != "archived"
        and not r.can_manage
        and roles[r.event_id] is not None
    ]
    if on_shift_candidates:
        # Each point on its own event's clock: one query per zone in play.
        zones = await crud_event.zones_by_id(
            session, (r.event_id for r in reads if r.id in on_shift_candidates)
        )
        by_zone: dict[str | None, list[uuid.UUID]] = {}
        for read in reads:
            if read.id in on_shift_candidates:
                by_zone.setdefault(zones.get(read.event_id), []).append(read.id)
        on_shift: set[uuid.UUID] = set()
        for zone, task_ids in by_zone.items():
            on_shift |= await on_shift_task_ids(
                user, session, task_ids, now=clock.wall_clock_now(zone)
            )
        for read in reads:
            if read.id in on_shift:
                read.can_redeem = True


async def decorate_task_reads(
    session: AsyncSession, user: User, reads: Sequence[_TaskReadEntry]
) -> dict[uuid.UUID, TeamLock]:
    """Everything viewer-relative on task reads: team locks and access.

    Returns the team locks, like :func:`app.logic.teams.mark_task_locks`.
    """
    locks = await mark_task_locks(session, user, reads)
    await mark_task_access(session, user, reads)
    return locks
