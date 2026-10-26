# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false
# SQLAlchemy column-level selects produce types that basedpyright cannot resolve.
import datetime as dt
import uuid

import sqlalchemy as sa
from fastapi import APIRouter
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.api.deps import CurrentUser, DBDep
from app.crud.event_team import event_team as crud_team
from app.logic.event_scope import (
    get_manageable_event_ids,
    get_user_event_scope,
    get_visible_event_ids,
)
from app.logic.teams import bookable_filter, team_locks
from app.models.booking import Booking
from app.models.event import Event
from app.models.event_join_request import EventJoinRequest
from app.models.event_team import EventTeam, EventTeamMember
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.dashboard import (
    DashboardAttention,
    DashboardFeedResponse,
    DashboardOpenShift,
    DashboardShift,
)
from app.schemas.sidebar import (
    SidebarBooking,
    SidebarEvent,
    SidebarResponse,
    SidebarTask,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

#: How many rows of each list the dashboard actually draws.
PAGE_SIZE = 6

#: How far a single feed request will scan to reach its totals. Both lists are
#: bounded by real-world size - a volunteer's future commitments, and the open
#: shifts of one event - so this is a runaway guard, not a page size.
SCAN_LIMIT = 500

#: The window "needs your attention" reports on. A week is long enough to still
#: do something about a gap and short enough that everything in it is urgent.
ATTENTION_HORIZON_DAYS = 7


@router.get("/feed", response_model=DashboardFeedResponse)
async def dashboard_feed(
    session: DBDep,
    current_user: CurrentUser,
) -> DashboardFeedResponse:
    """Everything /app/home draws, in one request.

    Two different scopes on purpose. *My shifts* ignores the selected event: a
    duty you have promised to turn up to should not disappear because the event
    switcher is pointing somewhere else. Everything else - the open shifts, the
    organiser's counts - is about the event in view.
    """
    now = dt.datetime.now()
    today = now.date()

    visible_event_ids = await get_visible_event_ids(session, current_user)
    manageable_event_ids = await get_manageable_event_ids(session, current_user)
    scope_event_id = _effective_scope(current_user, visible_event_ids)

    my_shifts, my_shift_count, my_minutes = await _load_my_shifts(
        session, current_user.id, today, now.time()
    )
    open_shifts, open_shift_count, open_places = await _load_open_shifts(
        session,
        current_user.id,
        today,
        now.time(),
        scope_event_id,
        visible_event_ids,
        await bookable_filter(session, current_user),
    )
    team_requests = await _pending_team_requests_by_event(
        session, current_user.id, visible_event_ids, manageable_event_ids
    )
    attention = await _load_attention(
        session, today, scope_event_id, manageable_event_ids, team_requests
    )

    return DashboardFeedResponse(
        event_id=scope_event_id,
        event_name=await _event_name(session, scope_event_id),
        my_shifts=my_shifts[:PAGE_SIZE],
        my_shift_count=my_shift_count,
        my_minutes=my_minutes,
        open_shifts=open_shifts[:PAGE_SIZE],
        open_shift_count=open_shift_count,
        open_places=open_places,
        attention=attention,
        pending_join_request_count=await _count_pending_join_requests(
            session, manageable_event_ids
        ),
        pending_team_request_count=sum(team_requests.values()),
    )


# ---------------------------------------------------------------------------
# Feed sections
# ---------------------------------------------------------------------------


async def _load_my_shifts(
    session: AsyncSession,
    user_id: uuid.UUID,
    today: dt.date,
    now_time: dt.time,
) -> tuple[list[DashboardShift], int, int]:
    """The user's upcoming confirmed bookings, soonest first.

    Returns the rows, how many there are and how many minutes they add up to.
    A shift with no clock times counts as zero minutes rather than guessing.
    """
    query = (
        select(
            col(Booking.id).label("booking_id"),
            col(Shift.id).label("shift_id"),
            col(Shift.title),
            col(Shift.date),
            col(Shift.start_time),
            col(Shift.end_time),
            col(Shift.location),
            col(Shift.max_bookings),
            col(Task.id).label("task_id"),
            col(Task.name).label("task_name"),
            col(Event.id).label("event_id"),
            col(Event.name).label("event_name"),
            _confirmed_count_sq().label("taken"),
        )
        .join(Shift, col(Booking.shift_id) == col(Shift.id))
        .join(Task, col(Shift.task_id) == col(Task.id))
        .join(Event, col(Task.event_id) == col(Event.id), isouter=True)
        .where(
            col(Booking.user_id) == user_id,
            col(Booking.status) == "confirmed",
            _future_shift_condition(today, now_time),
        )
        .order_by(col(Shift.date), col(Shift.start_time), col(Shift.title))
        .limit(SCAN_LIMIT)
    )
    rows = (await session.execute(query)).all()

    items = [
        DashboardShift(
            booking_id=r.booking_id,
            shift_id=r.shift_id,
            task_id=r.task_id,
            task_name=r.task_name,
            event_id=r.event_id,
            event_name=r.event_name,
            title=r.title,
            date=r.date,
            start_time=r.start_time,
            end_time=r.end_time,
            location=r.location,
            taken=r.taken or 0,
            capacity=r.max_bookings,
        )
        for r in rows
    ]
    minutes = sum(_duration_minutes(i.start_time, i.end_time) for i in items)
    return items, len(items), minutes


async def _load_open_shifts(
    session: AsyncSession,
    user_id: uuid.UUID,
    today: dt.date,
    now_time: dt.time,
    scope_event_id: uuid.UUID | None,
    visible_event_ids: list[uuid.UUID] | None,
    gate: tuple[list[uuid.UUID], list[uuid.UUID]] | None,
) -> tuple[list[DashboardOpenShift], int, int]:
    """Upcoming shifts that still have room, soonest first.

    Published tasks only: a draft is the organiser's workbench, not something
    to offer a volunteer. Shifts the user is already on are left out - those
    are on the other list, and offering them again reads as a bug.

    So are shifts a team keeps the user from booking. This is a list of
    suggestions, and suggesting what they cannot take is a dead end; the
    Tasks page still shows those, with the lock and the way in. ``gate`` is
    :func:`app.logic.teams.bookable_filter` - ``None`` for the superadmin,
    whom no team stops.
    """
    taken_sq = _confirmed_count_sq()
    mine_sq = (
        select(col(Booking.id))
        .where(
            col(Booking.shift_id) == col(Shift.id),
            col(Booking.user_id) == user_id,
            col(Booking.status) == "confirmed",
        )
        .correlate(Shift)
        .exists()
    )

    query = (
        select(
            col(Shift.id).label("shift_id"),
            col(Shift.title),
            col(Shift.date),
            col(Shift.start_time),
            col(Shift.end_time),
            col(Shift.location),
            col(Shift.max_bookings),
            col(Task.id).label("task_id"),
            col(Task.name).label("task_name"),
            col(Event.id).label("event_id"),
            col(Event.name).label("event_name"),
            taken_sq.label("taken"),
        )
        .join(Task, col(Shift.task_id) == col(Task.id))
        .join(Event, col(Task.event_id) == col(Event.id), isouter=True)
        .where(
            _future_shift_condition(today, now_time),
            col(Task.status) == "published",
            col(Shift.max_bookings) > taken_sq,
            ~mine_sq,
            _visible_tasks_condition(scope_event_id, visible_event_ids),
        )
        .order_by(col(Shift.date), col(Shift.start_time), col(Shift.title))
        .limit(SCAN_LIMIT)
    )
    if gate is not None:
        team_ids, admin_event_ids = gate
        # Same rule as crud_task's "only tasks I can book" filter.
        query = query.where(
            or_(
                col(Task.team_id).is_(None),
                col(Task.team_id).in_(team_ids),
                col(Task.event_id).in_(admin_event_ids),
            )
        )
    rows = (await session.execute(query)).all()

    items = [
        DashboardOpenShift(
            shift_id=r.shift_id,
            task_id=r.task_id,
            task_name=r.task_name,
            event_id=r.event_id,
            event_name=r.event_name,
            title=r.title,
            date=r.date,
            start_time=r.start_time,
            end_time=r.end_time,
            location=r.location,
            taken=r.taken or 0,
            capacity=r.max_bookings,
            places_left=max(r.max_bookings - (r.taken or 0), 0),
        )
        for r in rows
    ]
    return items, len(items), sum(i.places_left for i in items)


async def _load_attention(
    session: AsyncSession,
    today: dt.date,
    scope_event_id: uuid.UUID | None,
    manageable_event_ids: list[uuid.UUID] | None,
    team_requests: dict[uuid.UUID, int],
) -> DashboardAttention | None:
    """The organiser's counts, or ``None`` for somebody who runs nothing.

    ``manageable_event_ids`` is ``None`` for the platform superadmin, meaning
    unrestricted - the one case where an empty list and ``None`` must not be
    confused.
    """
    if manageable_event_ids is not None and not manageable_event_ids:
        return None
    if (
        scope_event_id is not None
        and manageable_event_ids is not None
        and scope_event_id not in manageable_event_ids
    ):
        # A plain member of the event in view, even though they administer a
        # different one. None of this is theirs to act on here.
        return None

    scope = _visible_tasks_condition(scope_event_id, manageable_event_ids)
    horizon = today + dt.timedelta(days=ATTENTION_HORIZON_DAYS)
    taken_sq = _confirmed_count_sq()

    draft_tasks = await _scalar(
        session,
        select(func.count())
        .select_from(Task)
        .where(col(Task.status) == "draft", col(Task.end_date) >= today, scope),
    )

    async def count_shifts(extra) -> int:  # noqa: ANN001
        return await _scalar(
            session,
            select(func.count())
            .select_from(Shift)
            .join(Task, col(Shift.task_id) == col(Task.id))
            .where(
                col(Shift.date) >= today,
                col(Shift.date) <= horizon,
                col(Task.status) == "published",
                scope,
                extra,
            ),
        )

    return DashboardAttention(
        pending_join_requests=await _count_pending_join_requests(
            session, manageable_event_ids, scope_event_id
        ),
        # Only the events this user runs: a team they merely lead elsewhere is
        # in the top-level count, not on the organiser's to-do list.
        pending_team_requests=sum(
            n
            for event_id, n in team_requests.items()
            if (manageable_event_ids is None or event_id in manageable_event_ids)
            and (scope_event_id is None or event_id == scope_event_id)
        ),
        draft_tasks=draft_tasks,
        empty_shifts_soon=await count_shifts(taken_sq == 0),
        short_shifts_soon=await count_shifts(
            and_(taken_sq > 0, taken_sq < col(Shift.max_bookings))
        ),
        horizon_days=ATTENTION_HORIZON_DAYS,
    )


async def _count_pending_join_requests(
    session: AsyncSession,
    manageable_event_ids: list[uuid.UUID] | None,
    scope_event_id: uuid.UUID | None = None,
) -> int:
    """Join requests awaiting a decision, across every event this user runs.

    ``scope_event_id`` narrows it to the event in view. The top-level count on
    the feed leaves it off, because the toast it drives is about anything
    waiting on the user, wherever it is.
    """
    query = (
        select(func.count())
        .select_from(EventJoinRequest)
        .where(col(EventJoinRequest.status) == "pending")
    )
    if manageable_event_ids is not None:
        if not manageable_event_ids:
            return 0
        query = query.where(col(EventJoinRequest.event_id).in_(manageable_event_ids))
    if scope_event_id is not None:
        query = query.where(col(EventJoinRequest.event_id) == scope_event_id)
    return await _scalar(session, query)


async def _pending_team_requests_by_event(
    session: AsyncSession,
    user_id: uuid.UUID,
    visible_event_ids: list[uuid.UUID] | None,
    manageable_event_ids: list[uuid.UUID] | None,
) -> dict[uuid.UUID, int]:
    """Team requests waiting on this user, per event.

    Every request in an event they administer, those of teams they lead in the
    rest - the same split ``require_team_manager`` makes, and the same count
    ``EventRead.pending_team_request_count`` carries per event. The superadmin
    (``None``) gets every non-demo event, like the join-request count.
    """
    if manageable_event_ids is None or visible_event_ids is None:
        rows = await session.execute(
            select(col(EventTeam.event_id), func.count())
            .select_from(EventTeamMember)
            .join(EventTeam, col(EventTeam.id) == col(EventTeamMember.team_id))
            .join(Event, col(Event.id) == col(EventTeam.event_id))
            .where(
                col(EventTeamMember.status) == "pending",
                col(Event.is_sandbox).is_(False),
            )
            .group_by(col(EventTeam.event_id))
        )
        return dict(rows.all())
    admin_ids = set(manageable_event_ids)
    return await crud_team.decidable_pending_by_event(
        session,
        user_id=user_id,
        admin_event_ids=list(admin_ids),
        member_event_ids=[e for e in visible_event_ids if e not in admin_ids],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _effective_scope(
    user: User, visible_event_ids: list[uuid.UUID] | None
) -> uuid.UUID | None:
    """The user's selected event, if they may actually still see it.

    A selection can outlive the membership that justified it - being removed
    from an event does not reach into the profile pointing at it - so this
    drops a stale one instead of filtering the whole dashboard down to nothing.
    """
    selected = get_user_event_scope(user)
    if selected is None or visible_event_ids is None:
        return selected
    return selected if selected in visible_event_ids else None


def _visible_tasks_condition(
    scope_event_id: uuid.UUID | None,
    event_ids: list[uuid.UUID] | None,
):  # noqa: ANN202
    """Restrict a Task-joined query to what this user may see.

    ``event_ids`` of ``None`` means unrestricted (platform superadmin); an
    empty list means the user is in no events, and that has to come back as
    "nothing" rather than collapsing into "everything".
    """
    conditions = []
    if event_ids is None:
        # Sandbox demos are hidden from the superadmin too, and their tasks can
        # outlive their event with a NULL event_id, so this cannot lean on the
        # event filter to keep them out.
        conditions.append(col(Task.is_sandbox).is_(False))
    elif not event_ids:
        return sa.false()
    else:
        conditions.append(col(Task.event_id).in_(event_ids))

    if scope_event_id is not None and (
        event_ids is None or scope_event_id in event_ids
    ):
        conditions.append(col(Task.event_id) == scope_event_id)
    return and_(*conditions)


def _confirmed_count_sq():  # noqa: ANN202
    """Confirmed bookings on the Shift row of the enclosing query."""
    return (
        select(func.count())
        .select_from(Booking)
        .where(
            col(Booking.shift_id) == col(Shift.id),
            col(Booking.status) == "confirmed",
        )
        .correlate(Shift)
        .scalar_subquery()
    )


async def _scalar(session: AsyncSession, query) -> int:  # noqa: ANN001
    return (await session.execute(query)).scalar_one()


async def _get_visibility_filters(
    session: AsyncSession,
    user: User,
) -> tuple[str | None, list[uuid.UUID] | None, list[uuid.UUID] | None]:
    """Return (effective_status, manageable_ids, visible_event_ids).

    ``visible_event_ids`` of None means unrestricted (platform superadmin);
    an empty list means the user is in no events and should see nothing.
    """
    visible = await get_visible_event_ids(session, user)
    if visible is None:
        return None, None, None
    manageable = await get_manageable_event_ids(session, user)
    return "published", manageable or None, visible


async def _event_name(session: AsyncSession, event_id: uuid.UUID | None) -> str | None:
    if event_id is None:
        return None
    query = select(col(Event.name)).where(col(Event.id) == event_id)
    return (await session.execute(query)).scalar_one_or_none()


def _duration_minutes(start: dt.time | None, end: dt.time | None) -> int:
    """Minutes between two wall-clock times, 0 when either is missing.

    An end before the start is read as running past midnight, which is what a
    22:00-02:00 shift means to whoever is standing there.
    """
    if start is None or end is None:
        return 0
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    return minutes if minutes >= 0 else minutes + 24 * 60


def _future_shift_condition(today: dt.date, now_time: dt.time | None = None):  # noqa: ANN202
    """Shift is in the future: date > today, or date == today and start_time >= now."""
    if now_time is not None:
        return or_(
            col(Shift.date) > today,
            and_(
                col(Shift.date) == today,
                or_(
                    col(Shift.start_time).is_(None),
                    col(Shift.start_time) >= now_time,
                ),
            ),
        )
    return col(Shift.date) >= today


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


@router.get("/sidebar", response_model=SidebarResponse)
async def dashboard_sidebar(
    session: DBDep,
    current_user: CurrentUser,
) -> SidebarResponse:
    """Lightweight data for sidebar quick-links."""
    now = dt.datetime.now()
    today = now.date()
    now_time = now.time()
    (
        effective_status,
        managed_group_ids,
        visible_event_ids,
    ) = await _get_visibility_filters(session, current_user)

    scoped_event_id = get_user_event_scope(current_user)

    groups = await _sidebar_events(
        session,
        today,
        effective_status,
        managed_group_ids,
        visible_event_ids,
        viewer_id=current_user.id,
    )
    tasks = await _sidebar_tasks(
        session,
        today,
        now_time,
        effective_status,
        managed_group_ids,
        event_id=scoped_event_id,
        visible_event_ids=visible_event_ids,
    )
    # A task reserved for a team the viewer is not in shows a lock instead of
    # its open-shift count: those shifts are not theirs to take.
    locks = await team_locks(session, current_user, (t.id for t in tasks))
    for task in tasks:
        lock = locks.get(task.id)
        if lock is not None and lock.team_id is not None:
            task.team_name = lock.team_name
            task.locked_by_team = lock.locked
    bookings = await _sidebar_bookings(
        session,
        current_user.id,
        today,
        now_time,
        event_id=scoped_event_id,
    )

    return SidebarResponse(
        events=groups,
        tasks=tasks,
        bookings=bookings,
    )


async def _sidebar_events(  # noqa: ANN001
    session,
    today: dt.date,
    status: str | None,
    managed_group_ids: list[uuid.UUID] | None = None,
    visible_event_ids: list[uuid.UUID] | None = None,
    viewer_id: uuid.UUID | None = None,
) -> list[SidebarEvent]:
    """The user's events whose end_date >= today, limit 5."""
    query = (
        select(col(Event.id), col(Event.name), col(Event.status))
        .where(col(Event.end_date) >= today)
        .where(
            # ``visible_event_ids`` is None for the superadmin, so it cannot be
            # what keeps demos out of their sidebar - this has to stand on its
            # own. The guest still sees their own, which is the entire point of
            # the second clause.
            or_(
                col(Event.is_sandbox).is_(False),
                col(Event.created_by_id) == viewer_id,
            )
        )
        .order_by(col(Event.start_date))
        .limit(5)
    )
    if visible_event_ids is not None:
        query = query.where(col(Event.id).in_(visible_event_ids))
    if status:
        status_filter = col(Event.status) == status
        if managed_group_ids:
            status_filter = or_(status_filter, col(Event.id).in_(managed_group_ids))
        query = query.where(status_filter)
    result = await session.execute(query)
    return [SidebarEvent(id=r.id, name=r.name, status=r.status) for r in result.all()]


async def _sidebar_tasks(  # noqa: ANN001
    session,
    today: dt.date,
    now_time: dt.time,
    status: str | None,
    managed_group_ids: list[uuid.UUID] | None = None,
    event_id: uuid.UUID | None = None,
    visible_event_ids: list[uuid.UUID] | None = None,
) -> list[SidebarTask]:
    """Published tasks with open-shift count and next shift date, limit 10.

    Scoped to ``event_id`` when provided so the sidebar matches the user's
    selected event.
    """
    future_cond = _future_shift_condition(today, now_time)

    # Subquery: confirmed booking count per shift
    booking_count_sq = (
        select(func.count())
        .select_from(Booking)
        .where(
            col(Booking.shift_id) == col(Shift.id),
            col(Booking.status) == "confirmed",
        )
        .correlate(Shift)
        .scalar_subquery()
    )

    # Subquery: count of open shifts (future AND has capacity)
    open_shifts_sq = (
        select(func.count())
        .select_from(Shift)
        .where(
            col(Shift.task_id) == col(Task.id),
            future_cond,
            col(Shift.max_bookings) > booking_count_sq,
        )
        .correlate(Task)
        .scalar_subquery()
    )

    # Subquery: next open shift date
    next_shift_date_sq = (
        select(func.min(col(Shift.date)))
        .where(
            col(Shift.task_id) == col(Task.id),
            future_cond,
            col(Shift.max_bookings) > booking_count_sq,
        )
        .correlate(Task)
        .scalar_subquery()
    )

    # Subquery: start_time of next open shift (on that date)
    next_shift_time_sq = (
        select(func.min(col(Shift.start_time)))
        .where(
            col(Shift.task_id) == col(Task.id),
            col(Shift.date) == next_shift_date_sq,
            col(Shift.max_bookings) > booking_count_sq,
        )
        .correlate(Task)
        .scalar_subquery()
    )

    # Only tasks that have at least one future open shift
    has_open_shift_sq = select(col(Shift.task_id)).where(
        future_cond,
        col(Shift.max_bookings) > booking_count_sq,
    )

    query = (
        select(
            col(Task.id),
            col(Task.name),
            col(Task.status),
            open_shifts_sq.label("open_shifts"),
            next_shift_date_sq.label("next_shift_date"),
            next_shift_time_sq.label("next_shift_start_time"),
        )
        .where(
            col(Task.end_date) >= today,
            col(Task.id).in_(has_open_shift_sq),
        )
        .order_by(col(Task.start_date))
        .limit(10)
    )
    if status:
        status_filter = col(Task.status) == status
        if managed_group_ids:
            status_filter = or_(
                status_filter, col(Task.event_id).in_(managed_group_ids)
            )
        query = query.where(status_filter)
    if event_id is not None:
        query = query.where(col(Task.event_id) == event_id)
    if visible_event_ids is not None:
        query = query.where(col(Task.event_id).in_(visible_event_ids))

    result = await session.execute(query)
    return [
        SidebarTask(
            id=r.id,
            name=r.name,
            status=r.status,
            open_shifts=r.open_shifts or 0,
            next_shift_date=r.next_shift_date,
            next_shift_start_time=r.next_shift_start_time,
        )
        for r in result.all()
    ]


async def _sidebar_bookings(  # noqa: ANN001
    session,
    user_id,
    today: dt.date,
    now_time: dt.time,
    event_id: uuid.UUID | None = None,
) -> list[SidebarBooking]:
    """User's upcoming confirmed bookings, limit 5.

    Scoped to ``event_id`` when provided so the sidebar matches the
    event-scoped /bookings/me view.
    """
    future_cond = _future_shift_condition(today, now_time)
    query = (
        select(
            col(Booking.id),
            col(Shift.id).label("slot_id"),
            col(Shift.task_id),
            col(Shift.title).label("slot_title"),
            col(Shift.date).label("slot_date"),
            col(Shift.start_time).label("slot_start_time"),
        )
        .join(Shift, col(Booking.shift_id) == col(Shift.id))
        .where(
            col(Booking.user_id) == user_id,
            col(Booking.status) == "confirmed",
            future_cond,
        )
        .order_by(col(Shift.date), col(Shift.start_time))
        .limit(5)
    )
    if event_id is not None:
        query = query.where(
            col(Shift.task_id).in_(
                select(col(Task.id)).where(col(Task.event_id) == event_id)
            )
        )
    result = await session.execute(query)
    return [
        SidebarBooking(
            id=r.id,
            slot_id=r.slot_id,
            task_id=r.task_id,
            slot_title=r.slot_title,
            slot_date=r.slot_date,
            slot_start_time=r.slot_start_time,
        )
        for r in result.all()
    ]
