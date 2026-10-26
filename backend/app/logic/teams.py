import datetime as dt
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.errors import raise_problem
from app.crud.event_membership import event_membership as crud_membership
from app.crud.event_team import event_team as crud_team
from app.logic.permissions import get_event_role, role_at_least
from app.logic.team_requirements import add_years
from app.models.event_team import EventTeam, EventTeamCheck, EventTeamRequirement
from app.models.task import Task
from app.models.user import User
from app.schemas.event_team import TeamCheckIn, TeamCheckRead, TeamMemberStatus


async def ensure_team_in_event(
    session: AsyncSession,
    *,
    team_id: uuid.UUID | None,
    event_id: uuid.UUID | None,
) -> None:
    """Refuse a task's ``team_id`` unless the team belongs to the task's event.

    Without this a task could be gated on another event's team — one its own
    admins cannot see or manage, which would lock their volunteers out.
    """
    if team_id is None:
        return
    if event_id is None or not await crud_team.get_in_event(
        session, team_id=team_id, event_id=event_id
    ):
        raise_problem(
            422,
            code="task.team_not_in_event",
            detail="The team must belong to the same event as the task",
        )


# --- Booking locks ------------------------------------------------------


@dataclass(frozen=True)
class TeamLock:
    """What a task's team means for one viewer."""

    event_id: uuid.UUID | None
    team_id: uuid.UUID | None = None
    team_name: str | None = None
    requires_approval: bool | None = None
    #: The viewer's own row in that team: pending, approved, declined or None.
    my_status: TeamMemberStatus | None = None
    locked: bool = False


async def team_locks(
    session: AsyncSession,
    user: User,
    task_ids: Iterable[uuid.UUID],
) -> dict[uuid.UUID, TeamLock]:
    """``{task_id: TeamLock}`` for every task given, gated or not.

    ``locked`` is what :func:`app.logic.permissions.require_team_for_booking`
    would decide, worked out for a whole list in a constant number of queries
    (one per distinct event for the role) rather than one per shift.
    """
    ids = set(task_ids)
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(
                col(Task.id),
                col(Task.event_id),
                col(EventTeam.id),
                col(EventTeam.name),
                col(EventTeam.requires_approval),
            )
            .outerjoin(EventTeam, col(EventTeam.id) == col(Task.team_id))
            .where(col(Task.id).in_(ids))
        )
    ).all()
    # An outer join: the team columns are NULL for a task without a team,
    # whatever the column types say.
    typed = [
        (task_id, event_id, cast(uuid.UUID | None, team_id), name, approval)
        for task_id, event_id, team_id, name, approval in rows
    ]
    gated = [r for r in typed if r[2] is not None]
    admin_events = {
        event_id
        for event_id in {r[1] for r in gated}
        if role_at_least(await get_event_role(user, session, event_id), "admin")
    }
    mine = await crud_team.rows_for_user(
        session, user_id=user.id, team_ids=[r[2] for r in gated if r[2] is not None]
    )
    out: dict[uuid.UUID, TeamLock] = {}
    for task_id, event_id, team_id, team_name, requires_approval in typed:
        if team_id is None:
            out[task_id] = TeamLock(event_id=event_id)
            continue
        row = mine.get(team_id)
        out[task_id] = TeamLock(
            event_id=event_id,
            team_id=team_id,
            team_name=team_name,
            requires_approval=requires_approval,
            my_status=cast(TeamMemberStatus, row.status) if row else None,
            locked=(
                event_id not in admin_events
                and (row is None or row.status != "approved")
            ),
        )
    return out


class _ShiftEntry(Protocol):
    task_id: uuid.UUID
    event_id: uuid.UUID | None
    team_id: uuid.UUID | None
    team_name: str | None
    team_requires_approval: bool | None
    my_team_status: TeamMemberStatus | None
    locked_by_team: bool


def apply_lock(entry: _ShiftEntry, lock: TeamLock | None) -> None:
    if lock is None:
        return
    entry.event_id = lock.event_id
    entry.team_id = lock.team_id
    entry.team_name = lock.team_name
    entry.team_requires_approval = lock.requires_approval
    entry.my_team_status = lock.my_status
    entry.locked_by_team = lock.locked


async def mark_team_locks(
    session: AsyncSession, user: User, entries: Sequence[_ShiftEntry]
) -> None:
    """Fill the team fields and ``event_id`` on shifts, like mark_collisions."""
    locks = await team_locks(session, user, (e.task_id for e in entries))
    for entry in entries:
        apply_lock(entry, locks.get(entry.task_id))


class _TaskEntry(Protocol):
    id: uuid.UUID
    team_name: str | None
    team_requires_approval: bool | None
    my_team_status: TeamMemberStatus | None
    locked_by_team: bool


async def mark_task_locks(
    session: AsyncSession, user: User, tasks: Sequence[_TaskEntry]
) -> dict[uuid.UUID, TeamLock]:
    """Fill the team fields on task reads; returns the locks for reuse."""
    locks = await team_locks(session, user, (t.id for t in tasks))
    for task in tasks:
        lock = locks.get(task.id)
        if lock is None or lock.team_id is None:
            continue
        task.team_name = lock.team_name
        task.team_requires_approval = lock.requires_approval
        task.my_team_status = lock.my_status
        task.locked_by_team = lock.locked
    return locks


async def bookable_filter(
    session: AsyncSession, user: User
) -> tuple[list[uuid.UUID], list[uuid.UUID]] | None:
    """``(approved team ids, admin event ids)`` for the task "bookable" filter.

    None for the platform superadmin, whom no team gate stops.
    """
    if user.is_admin:
        return None
    team_ids = await crud_team.approved_team_ids(session, user_id=user.id)
    admin_event_ids = await crud_membership.list_event_ids_for_user(
        session, user_id=user.id, minimum_role="admin"
    )
    return team_ids, admin_event_ids


# --- Requirements and checks ----------------------------------------------


def expiry_for(
    requirement: EventTeamRequirement, issued_on: dt.date | None, today: dt.date
) -> dt.date | None:
    """When a check of ``requirement`` stops being valid, if ever.

    Counted from the document's issue date when it was asked for, else from
    the day of the check.
    """
    if requirement.valid_for_years is None:
        return None
    return add_years(issued_on or today, requirement.valid_for_years)


@dataclass(frozen=True)
class ValidCheck:
    requirement: EventTeamRequirement
    issued_on: dt.date | None
    expires_on: dt.date | None


def validate_checks(
    requirements: Sequence[EventTeamRequirement],
    checks: Sequence[TeamCheckIn],
    *,
    require_all: bool,
    today: dt.date | None = None,
) -> list[ValidCheck]:
    """Turn the decider's ticks into checks to store, or raise a 422.

    ``require_all`` (approving, placing someone) wants one tick per
    requirement, with an issue date where the requirement asks for one —
    ``team.checks_missing`` names the rest. A future issue date, or one so old
    the check would already have expired, is refused rather than stored.
    """
    today = today or dt.date.today()
    by_id = {r.id: r for r in requirements}
    unknown = [str(c.requirement_id) for c in checks if c.requirement_id not in by_id]
    if unknown:
        raise_problem(
            422,
            code="team.check_unknown_requirement",
            detail="A check names a requirement this team does not have",
            extensions={"requirement_ids": unknown},
        )
    given = {c.requirement_id: c for c in checks}
    missing = [
        r
        for r in requirements
        if (require_all and r.id not in given)
        or (r.id in given and r.ask_issue_date and given[r.id].issued_on is None)
    ]
    if missing:
        raise_problem(
            422,
            code="team.checks_missing",
            detail="Tick every requirement (with its issue date) before approving",
            extensions={"requirement_ids": [str(r.id) for r in missing]},
        )
    out: list[ValidCheck] = []
    for req_id, tick in given.items():
        req = by_id[req_id]
        issued_on = tick.issued_on if req.ask_issue_date else None
        if issued_on is not None and issued_on > today:
            raise_problem(
                422,
                code="team.check_issued_in_future",
                detail=f'The issue date for "{req.label}" is in the future',
                extensions={"requirement_ids": [str(req.id)]},
            )
        expires_on = expiry_for(req, issued_on, today)
        if expires_on is not None and expires_on < today:
            raise_problem(
                422,
                code="team.check_expired",
                detail=f'The document for "{req.label}" is no longer valid',
                extensions={"requirement_ids": [str(req.id)]},
            )
        out.append(ValidCheck(req, issued_on, expires_on))
    return out


async def store_checks(
    session: AsyncSession,
    *,
    member_id: uuid.UUID,
    checks: Sequence[ValidCheck],
    checked_by: User,
) -> None:
    for check in checks:
        await crud_team.record_check(
            session,
            member_id=member_id,
            requirement_id=check.requirement.id,
            issued_on=check.issued_on,
            expires_on=check.expires_on,
            checked_by=checked_by,
        )


def is_expired(check: EventTeamCheck, today: dt.date) -> bool:
    return check.expires_on is not None and check.expires_on < today


def check_read(
    check: EventTeamCheck,
    requirement: EventTeamRequirement,
    today: dt.date,
    *,
    source_team_name: str | None = None,
) -> TeamCheckRead:
    return TeamCheckRead(
        requirement_id=requirement.id,
        label=requirement.label,
        checked_by_name=check.checked_by_name,
        checked_at=check.checked_at,
        issued_on=check.issued_on,
        expires_on=check.expires_on,
        expired=is_expired(check, today),
        source_team_name=source_team_name,
    )


def needs_recheck(
    requirements: Sequence[EventTeamRequirement],
    checks: Sequence[TeamCheckRead],
) -> bool:
    """A requirement without a valid check: never ticked, or since expired.

    Only a flag for the managers. Access is not revoked by it: expiry happens
    on a calendar, and pulling someone off a team at midnight helps nobody.
    """
    valid = {c.requirement_id for c in checks if not c.expired}
    return any(r.id not in valid for r in requirements)
