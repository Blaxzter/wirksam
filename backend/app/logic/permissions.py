"""Per-event authorisation.

Every event is its own little tenancy: who may read it, book in it, or manage
it is decided by the caller's ``EventMembership`` row, not by a global role.
The one global role left is ``admin`` (the platform superadmin), which passes
every check here so support and moderation stay possible.

All mutation routes funnel through :func:`require_event_role`; all read routes
through :func:`require_event_visible`. Keeping the gates in this module the only
entry points is what makes the model auditable — grep for them to find every
check.

Teams add one layer *inside* an event, and only two gates of their own:
:func:`require_team_manager` (deciding requests, editing a roster) and
:func:`require_team_for_booking` (booking a shift of a task that requires a
team). Both let event admins through, so a team can never lock its own event's
admins out.

People in charge of a task (``task_managers``) add four more, all of which let
event admins through as well:

- :func:`require_task_manager` for editing one task's details and its shifts.
  It returns the caller's level (:data:`TaskAccess`) so the route can refuse
  the fields that stay with event admins (status, team, moving the task).
- :func:`require_shift_editor` for adding, deleting and regenerating a task's
  shifts and batches: :func:`require_task_manager`, plus 403
  ``task.voucher_shifts_admin_only`` for a person in charge of a task that
  earns vouchers, unless the event allows it
  (``events.managers_edit_voucher_shifts``, off by default). Every extra or
  bigger shift earns vouchers, so that lever stays with the event admins.
  ``PATCH /shifts/{id}`` asks :func:`check_voucher_shifts` only when it
  changes one of :data:`SHIFT_EARNING_FIELDS`, so a person in charge can still
  fix a shift's title or place; :func:`voucher_shifts_locked` is the same rule
  as a pure flag, for ``TaskRead.can_manage_shifts``.
- :func:`require_task_visible` for reading one task: event members see
  published tasks; drafts and archived tasks only the event admins and the
  task's people in charge (and a booker can always reopen their own shift).
- :func:`check_shift_history`, the shift history rule: a person in charge may
  not delete, re-date or re-start a booked shift that has started, nor move a
  booked shift's start or end into the past. Hours are derived from booked
  shifts that have ended, so that past belongs to the event admins.

Being in charge only counts while the person is a member of the task's event
(:func:`task_access`), so a row left behind by someone who left grants nothing.

Vouchers add one gate, :func:`require_voucher_redeemer`, for taking vouchers at
a task that is a redemption point: event admins, the task's people in charge,
and whoever has a confirmed booking on one of its shifts that is running now
(``logic.vouchers.redeem_window``: 30 minutes either side). Redeeming without
a code, by picking the person, is for admins and people in charge, and, when
the event's ``voucher_manual_redeem`` is ``on_shift`` (the default), for
whoever is on shift at that point too (:func:`may_redeem_manually`). Every
manual redemption records who made it, so it can be traced.
"""

import datetime as dt
import enum
import uuid
from typing import Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.event_membership import event_membership as crud_membership
from app.crud.event_team import event_team as crud_team
from app.crud.task_manager import task_manager as crud_task_manager
from app.logic.vouchers import in_redeem_window, redeem_window_dates
from app.logic.work_hours import shift_ends_at
from app.models.event import Event
from app.models.event_team import EventTeam
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.event_membership import EventRole

#: How a caller may manage one task: as an event admin (or the superadmin), or
#: as one of the task's people in charge.
TaskAccess = Literal["admin", "manager"]

#: Why a caller may redeem vouchers at a point: as an event admin, as one of
#: its people in charge, or because they are on a running shift there.
RedeemerKind = Literal["admin", "manager", "on_shift"]

#: Shift fields whose change decides who earns how much: when a shift runs,
#: and how many people it takes.
SHIFT_EARNING_FIELDS: tuple[str, ...] = (
    "date",
    "start_time",
    "end_time",
    "max_bookings",
)


class _EarnsVouchers(Protocol):
    """A task, or a task read: anything with a voucher rate."""

    @property
    def vouchers_per_shift(self) -> int: ...


class _VoucherShiftRule(Protocol):
    """An event, or anything else carrying its voucher-shift setting."""

    @property
    def managers_edit_voucher_shifts(self) -> bool: ...


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


# --- People in charge of a task -------------------------------------------


async def task_access(
    user: User,
    session: AsyncSession,
    task: Task,
) -> TaskAccess | None:
    """``"admin"`` for event admins, the owner and the superadmin; ``"manager"``
    for a person in charge who is still a member of the task's event; else None.

    A task without an event (its event was deleted) is the superadmin's only.
    """
    role = await get_event_role(user, session, task.event_id)
    if role_at_least(role, "admin"):
        return "admin"
    if role is None:
        # Before the row lookup: someone who left the event keeps nothing,
        # even if a stale row survived somewhere.
        return None
    if await crud_task_manager.is_manager(session, task_id=task.id, user_id=user.id):
        return "manager"
    return None


async def can_manage_task(user: User, session: AsyncSession, task: Task) -> bool:
    return await task_access(user, session, task) is not None


async def require_task_manager(
    user: User,
    session: AsyncSession,
    task: Task,
) -> TaskAccess:
    """Raise 403 ``task.forbidden`` unless the user may edit this task.

    Returns the level, so the caller can refuse what only admins may change.
    """
    access = await task_access(user, session, task)
    if access is None:
        raise_problem(
            403,
            code="task.forbidden",
            detail="Only this task's people in charge and the event admins can do this",
        )
    return access


def voucher_shifts_locked(
    access: TaskAccess | None,
    task: _EarnsVouchers,
    event: _VoucherShiftRule | None,
) -> bool:
    """Whether the shifts of ``task`` are the event admins' alone for this caller.

    True for a person in charge (``access == "manager"``) of a task that earns
    vouchers, in an event that does not let people in charge change those
    shifts (``managers_edit_voucher_shifts``, off by default). Never for event
    admins. A task without an event (``event`` None) counts as locked.

    Pure, so the task reads use it for ``can_manage_shifts`` as well.
    """
    if access != "manager" or task.vouchers_per_shift <= 0:
        return False
    return event is None or not event.managers_edit_voucher_shifts


async def check_voucher_shifts(
    access: TaskAccess, session: AsyncSession, task: Task
) -> None:
    """Raise 403 ``task.voucher_shifts_admin_only`` when :func:`voucher_shifts_locked`.

    Loads the event only for a person in charge of a task that earns vouchers,
    the one case where its setting decides.
    """
    if access != "manager" or task.vouchers_per_shift <= 0:
        return
    event = await session.get(Event, task.event_id) if task.event_id else None
    if voucher_shifts_locked(access, task, event):
        raise_problem(
            403,
            code="task.voucher_shifts_admin_only",
            detail=(
                "This task earns vouchers, so only the event admins can add, "
                "move, resize or delete its shifts"
            ),
        )


async def require_shift_editor(
    user: User,
    session: AsyncSession,
    task: Task,
) -> TaskAccess:
    """Raise 403 unless the user may add, delete or regenerate this task's shifts.

    :func:`require_task_manager` (403 ``task.forbidden``), then
    :func:`check_voucher_shifts` (403 ``task.voucher_shifts_admin_only``).
    Returns the level, like :func:`require_task_manager`.
    """
    access = await require_task_manager(user, session, task)
    await check_voucher_shifts(access, session, task)
    return access


async def require_task_visible(
    user: User,
    session: AsyncSession,
    task: Task,
    *,
    booked_shift_id: uuid.UUID | None = None,
) -> EventRole:
    """The read gate for one task; returns the caller's role in its event.

    - 404 ``task.not_found`` for a task in a sandbox event that the caller did
      not create. Checked first, because ``get_event_role`` reports the
      superadmin as owner of everything (the same order as
      :func:`require_event_visible`). Decided on the *event*: a task the guest
      creates in their demo is a sandbox task whatever its own flag says.
      ``Task.is_sandbox`` still counts for a task whose event is gone.
    - 404 ``task.not_found`` when the caller holds no role in the task's event,
      so a task cannot be probed by id.
    - 403 ``task.not_published`` for a draft or archived task, unless the caller
      can manage it, or ``booked_shift_id`` is given and the caller has a
      booking (any status) on that shift: a volunteer can always reopen their
      own booking after the organisers archive the task.
    """
    event = await session.get(Event, task.event_id) if task.event_id else None
    if (task.is_sandbox or (event is not None and event.is_sandbox)) and (
        event is None or event.created_by_id != user.id
    ):
        raise_problem(404, code="task.not_found", detail="Task not found")

    role = await get_event_role(user, session, task.event_id)
    if role is None:
        raise_problem(404, code="task.not_found", detail="Task not found")
    if task.status == "published" or role_at_least(role, "admin"):
        return role
    if await crud_task_manager.is_manager(session, task_id=task.id, user_id=user.id):
        return role
    if booked_shift_id is not None and (
        await crud_booking.get_by_shift_and_user(
            session, shift_id=booked_shift_id, user_id=user.id
        )
        is not None
    ):
        return role
    raise_problem(403, code="task.not_published", detail="Task is not published")


class _Keep(enum.Enum):
    """Sentinel for "this value does not change" in :func:`check_shift_history`.

    ``None`` cannot play that part: a shift may legitimately have no start or
    end time, and a PATCH may clear one.
    """

    KEEP = enum.auto()


KEEP = _Keep.KEEP


def check_shift_history(
    access: TaskAccess,
    *,
    before: Shift,
    has_bookings: bool,
    new_date: dt.date | _Keep = KEEP,
    new_start: dt.time | None | _Keep = KEEP,
    new_end: dt.time | None | _Keep = KEEP,
    deleting: bool = False,
    now: dt.datetime,
) -> None:
    """The shift history rule. Raises 403 ``task.shift_history_admin_only``.

    Nothing to check for event admins, or for a shift nobody has a confirmed
    booking on. For a person in charge:

    - a booked shift that **has started** cannot be deleted, and its date and
      start time cannot change. Its end time may still move while the shift
      stays unfinished ("we're staying an hour longer"), but not once it has
      ended;
    - a booked shift cannot be moved so that it starts, or ends, at or before
      ``now``. Moving only the start into the past would leave a shift that
      has not ended yet but soon has, with the back-dated part counted.

    Hours are derived from booked shifts that have ended, so whoever rewrites a
    booked shift's past rewrites other people's hours.

    ``new_*`` are the values after the edit, :data:`KEEP` for unchanged.
    "Started" is ``combine(date, start_time or 00:00) <= now``; "ends" is
    ``work_hours.shift_ends_at``. ``now`` is the event wall clock
    (``clock.wall_clock_now(zone)``). Pure, so the routes pass ``has_bookings``.
    Creating shifts never calls this: nobody can book a shift that has ended,
    and a shift created already running is visible on the task like any other
    (see "What this does not prevent" in the plan).
    """
    if shift_history_refuses(
        access,
        before=before,
        has_bookings=has_bookings,
        new_date=new_date,
        new_start=new_start,
        new_end=new_end,
        deleting=deleting,
        now=now,
    ):
        raise_problem(
            403,
            code="task.shift_history_admin_only",
            detail=(
                "Only an event admin can change or delete a booked shift that "
                "has started, or move a booked shift into the past"
            ),
        )


def shift_history_refuses(
    access: TaskAccess,
    *,
    before: Shift,
    has_bookings: bool,
    new_date: dt.date | _Keep = KEEP,
    new_start: dt.time | None | _Keep = KEEP,
    new_end: dt.time | None | _Keep = KEEP,
    deleting: bool = False,
    now: dt.datetime,
) -> bool:
    """What :func:`check_shift_history` decides, as a flag instead of a 403.

    For the regenerate dry run, which reports refused shifts as ``locked``
    rather than failing.
    """
    if access == "admin" or not has_bookings:
        return False

    started = dt.datetime.combine(before.date, before.start_time or dt.time()) <= now
    if deleting:
        return started

    date = before.date if isinstance(new_date, _Keep) else new_date
    start = before.start_time if isinstance(new_start, _Keep) else new_start
    end = before.end_time if isinstance(new_end, _Keep) else new_end
    date_or_start_changed = date != before.date or start != before.start_time
    if not date_or_start_changed and end == before.end_time:
        return False
    if date_or_start_changed and (
        started or dt.datetime.combine(date, start or dt.time()) <= now
    ):
        # Neither re-date one that has started, nor move one's start into the
        # past: next week's 10-12 turned into "since midnight, ends in a
        # minute" has not ended yet, but a minute later it has, with the whole
        # back-dated length counted as worked.
        return True
    if shift_ends_at(before.date, before.start_time, before.end_time) <= now:
        # Already over: moving its end, even to later, rewrites worked hours.
        return True
    return shift_ends_at(date, start, end) <= now


# --- Vouchers --------------------------------------------------------------


async def on_shift_task_ids(
    user: User,
    session: AsyncSession,
    task_ids: list[uuid.UUID],
    *,
    now: dt.datetime,
) -> set[uuid.UUID]:
    """Which of ``task_ids`` the user has a confirmed shift running at ``now``.

    "Running" is ``logic.vouchers.redeem_window``: 30 minutes before the start
    to 30 minutes after the end, all day for a shift without times. ``now`` is
    the event wall clock (``clock.wall_clock_now(zone)``), so ``task_ids`` are of
    events in one zone. One query, so the task
    reads can ask it for a whole page.
    """
    date_from, date_to = redeem_window_dates(now)
    rows = await crud_booking.confirmed_shift_times(
        session,
        user_id=user.id,
        task_ids=task_ids,
        date_from=date_from,
        date_to=date_to,
    )
    return {
        task_id
        for task_id, date, start, end in rows
        if in_redeem_window(now, date, start, end)
    }


async def voucher_redeemer_kind(
    user: User,
    session: AsyncSession,
    task: Task,
    *,
    now: dt.datetime,
) -> RedeemerKind | None:
    """Whether, and why, the user may redeem vouchers at ``task`` right now.

    :func:`task_access` first (event admins, the superadmin, people in charge);
    then, for an event member, a confirmed booking on a shift of this task
    whose redeem window contains ``now`` (event wall clock). Says nothing about
    whether the task *is* a point; the routes check that after this gate.
    """
    access = await task_access(user, session, task)
    if access is not None:
        return access
    if await get_event_role(user, session, task.event_id) is None:
        return None
    if task.id in await on_shift_task_ids(user, session, [task.id], now=now):
        return "on_shift"
    return None


def may_redeem_manually(kind: RedeemerKind, event: Event) -> bool:
    """Redeeming without a code: the person picked from the member list.

    Showing the code is the volunteer's consent; picking from the list is for
    people whose phone is not working. Event admins and the point's people in
    charge always may. Whoever is on shift at the point may only when the
    event's ``voucher_manual_redeem`` is ``on_shift`` (the default).

    That opens a door the organisers should know about: a member who books a
    running shift at a point anyone may book can spend other people's vouchers
    a minute later. The event settings say so under that option and suggest a
    team on such points; every manual redemption records the redeemer
    (``actor_name``, ``method="manual"``), so it can be traced; and
    ``in_charge`` closes the door.
    """
    if kind in ("admin", "manager"):
        return True
    return event.voucher_manual_redeem == "on_shift"


async def require_voucher_redeemer(
    user: User,
    session: AsyncSession,
    task: Task,
    *,
    event: Event,
    now: dt.datetime,
    manual: bool = False,
) -> RedeemerKind:
    """Raise 403 unless the user may redeem at ``task`` (without a code if ``manual``).

    ``event`` is the task's event, which the routes have already loaded.
    403 ``voucher.not_allowed`` when :func:`voucher_redeemer_kind` is None;
    403 ``voucher.manual_not_allowed`` when ``manual`` and
    :func:`may_redeem_manually` refuses.
    """
    kind = await voucher_redeemer_kind(user, session, task, now=now)
    if kind is None:
        raise_problem(
            403,
            code="voucher.not_allowed",
            detail=(
                "Only the event admins, the people in charge and whoever is on "
                "shift here can take vouchers at this task"
            ),
        )
    if manual and not may_redeem_manually(kind, event):
        raise_problem(
            403,
            code="voucher.manual_not_allowed",
            detail=(
                "Only the event admins and the people in charge can redeem "
                "without a code here"
            ),
        )
    return kind
