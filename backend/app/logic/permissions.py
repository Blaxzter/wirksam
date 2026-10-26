"""Per-event authorisation.

Every event is its own little tenancy: who may read it, book in it, or manage
it is decided by the caller's ``EventMembership`` row, not by a global role.
The one global role left is ``admin`` (the platform superadmin), which passes
every check here so support and moderation stay possible.

All mutation routes funnel through :func:`require_event_role`; all read routes
through :func:`require_event_visible`. Keeping those two the only entry points
is what makes the model auditable — grep for them to find every gate.

Teams add one layer *inside* an event, and only two gates of their own:
:func:`require_team_manager` (deciding requests, editing a roster) and
:func:`require_team_for_booking` (booking a shift of a task that requires a
team). Both let event admins through, so a team can never lock its own event's
admins out.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import raise_problem
from app.crud.event_membership import event_membership as crud_membership
from app.crud.event_team import event_team as crud_team
from app.models.event import Event
from app.models.event_team import EventTeam
from app.models.task import Task
from app.models.user import User
from app.schemas.event_membership import EventRole

# Weakest → strongest. Comparing positions in this tuple is the whole hierarchy.
_ROLE_ORDER: tuple[EventRole, ...] = ("member", "admin", "owner")


def role_at_least(role: EventRole | None, minimum: EventRole) -> bool:
    """Whether ``role`` is at or above ``minimum`` in the hierarchy."""
    if role is None:
        return False
    return _ROLE_ORDER.index(role) >= _ROLE_ORDER.index(minimum)


async def get_event_role(
    user: User,
    session: AsyncSession,
    event_id: uuid.UUID | None,
) -> EventRole | None:
    """Return the user's role in this event, or None if they hold none.

    The platform superadmin is reported as ``owner`` so callers can render
    management UI without a second special case — but note this is an
    *effective* role: it is not backed by a membership row.
    """
    if event_id is None:
        return "owner" if user.is_admin else None
    if user.is_admin:
        return "owner"
    return await crud_membership.get_role(session, user_id=user.id, event_id=event_id)


async def require_event_role(
    user: User,
    session: AsyncSession,
    event_id: uuid.UUID | None,
    *,
    minimum: EventRole = "admin",
) -> EventRole:
    """Raise 403 unless the user holds at least ``minimum`` in this event.

    ``event_id`` of None means an object that belongs to no event; only the
    platform superadmin may touch those.
    """
    role = await get_event_role(user, session, event_id)
    if not role_at_least(role, minimum):
        raise_problem(
            403,
            code="event.forbidden",
            detail="You do not have permission to do this in this event",
        )
    assert role is not None  # narrowed by role_at_least
    return role


async def require_event_visible(
    user: User,
    session: AsyncSession,
    event: Event,
) -> EventRole | None:
    """Raise 404 unless the user is allowed to see this event at all.

    Members see their events whatever the status. Everyone else sees only
    public *published* events, and gets a 404 rather than a 403 for private
    ones — a stranger should not be able to probe which private events exist.
    """
    # Before the role check, not after: ``get_event_role`` reports the
    # platform superadmin as "owner" of every event, so a test placed below
    # this line would leave them able to read any visitor's demo by id.
    if event.is_sandbox and event.created_by_id != user.id:
        raise_problem(404, code="event.not_found", detail="Event not found")

    role = await get_event_role(user, session, event.id)
    if role is not None:
        return role
    if event.visibility == "public" and event.status == "published":
        return None
    raise_problem(
        404,
        code="event.not_found",
        detail="Event not found",
    )


async def can_manage_team(
    user: User,
    session: AsyncSession,
    team: EventTeam,
) -> bool:
    """Event admins manage every team; an approved lead manages their own."""
    role = await get_event_role(user, session, team.event_id)
    if role_at_least(role, "admin"):
        return True
    if role is None:
        return False
    return await crud_team.is_approved(
        session, team_id=team.id, user_id=user.id, role="lead"
    )


async def require_team_manager(
    user: User,
    session: AsyncSession,
    team: EventTeam,
) -> None:
    """Raise 403 unless the user may decide requests for and edit this team."""
    if not await can_manage_team(user, session, team):
        raise_problem(
            403,
            code="team.forbidden",
            detail="Only this team's leads and the event admins can do this",
        )


async def may_book_task(user: User, session: AsyncSession, task: Task) -> bool:
    """Whether the team requirement on ``task`` (if any) lets this user book.

    Says nothing about event membership — that is the caller's concern.
    """
    if task.team_id is None:
        return True
    if role_at_least(await get_event_role(user, session, task.event_id), "admin"):
        return True
    return await crud_team.is_approved(session, team_id=task.team_id, user_id=user.id)


async def require_team_for_booking(
    user: User,
    session: AsyncSession,
    task: Task,
) -> None:
    """Raise 403 ``booking.team_required`` if the task needs a team the user lacks.

    The team is named in the problem body so the client can offer "ask to
    join" without a second request.
    """
    if await may_book_task(user, session, task):
        return
    assert task.team_id is not None  # narrowed by may_book_task
    team = await session.get(EventTeam, task.team_id)
    raise_problem(
        403,
        code="booking.team_required",
        detail=(
            f'Only approved members of the team "{team.name}" can book this shift'
            if team
            else "Only approved team members can book this shift"
        ),
        extensions={
            "team_id": str(task.team_id),
            "team_name": team.name if team else None,
        },
    )
