"""The management views of one event's shared lists, worked out in one pass.

:func:`load` reads what they need with a fixed number of queries
(``crud.shared_list_overview``), whatever the number of lists. The rest is pure:
which shifts each list offers and its status on the event's clock (the rules of
``offer``), which free places no live list offers, and the rows of the tables,
filtered, sorted and paged here. Paging in Python is affordable because an event
holds at most ``SHARED_LISTS_PER_EVENT`` lists, and needed because the status
and the issues depend on the clock and on every other list of the event: a
filter count, the summary and "to do" stay right on every page.

The coverage counts every list of the event, whoever asks: a shift on someone
else's live list is not stranded. What each caller sees follows the scope from
``permissions.shared_list_scope``, or, for one list, the access from
``require_shared_list_visible``.
"""

import datetime as dt
import uuid
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeVar, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.shared_list_overview import ListedTask, ShiftFill, SignupCounts
from app.crud.shared_list_overview import shared_list_overview as crud_overview
from app.crud.task_manager import task_manager as crud_task_manager
from app.logic.permissions import SharedListAccess, SharedListScope
from app.logic.shared_lists import offer
from app.logic.shared_lists.offer import EffectiveStatus
from app.models.event import Event
from app.models.shared_list import AskMode, EndsMode, ListStatus, SharedList, ShowNames
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from app.schemas.shared_list import (
    ListFilter,
    ListSort,
    SharedListCandidate,
    SharedListCandidateListResponse,
    SharedListCandidateShift,
    SharedListChip,
    SharedListCounts,
    SharedListDetail,
    SharedListDetailTask,
    SharedListEventRef,
    SharedListIssue,
    SharedListListResponse,
    SharedListOverview,
    SharedListRow,
    SharedListSummary,
    SharedListTaskCounts,
    SharedListTaskListResponse,
    SharedListTaskRef,
    SharedListTaskRow,
    SortDir,
    TaskFilter,
    TaskSort,
    TeamRef,
    UnsharedNotice,
)

#: The order of "status, ascending": open lists first, finished ones last.
_STATUS_RANK: dict[EffectiveStatus, int] = {
    "live": 0,
    "paused": 1,
    "expired": 2,
    "ended": 3,
}

_Row = TypeVar("_Row", SharedListRow, SharedListTaskRow)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Everything the views of one event are worked out from."""

    event: Event
    #: The event's wall clock, read once for the whole request.
    now_wall: dt.datetime
    lists: list[SharedList]
    listed: dict[uuid.UUID, list[ListedTask]]
    excluded: dict[uuid.UUID, frozenset[uuid.UUID]]
    #: The event's published tasks.
    tasks: dict[uuid.UUID, Task]
    #: Their shifts, started or not, by task and start.
    shifts: dict[uuid.UUID, list[ShiftFill]]
    signups: dict[uuid.UUID, SignupCounts]


@dataclass(frozen=True, slots=True)
class ListState:
    """One list as it stands on the event's clock."""

    shared_list: SharedList
    #: Its linked tasks still in its event, in its order: whoever is in charge
    #: of all of them manages it.
    current: list[ListedTask]
    #: Of those, the ones it can offer: published, and not limited to a team.
    offered: list[ListedTask]
    #: Their shifts that have not started, left out or not.
    ahead: list[ShiftFill]
    #: Of those, the ones it offers.
    open: list[ShiftFill]
    last_start: dt.datetime | None
    effective: EffectiveStatus

    @property
    def capacity(self) -> int:
        return sum(s.max_bookings for s in self.open)

    @property
    def free(self) -> int:
        return sum(s.free for s in self.open)


@dataclass(frozen=True, slots=True)
class Coverage:
    """Which shifts the event's lists offer, over every list of the event."""

    #: Offered by a live list.
    live: frozenset[uuid.UUID]
    #: Offered by a list that has not ended: live, paused or expired.
    listed: frozenset[uuid.UUID]


@dataclass(frozen=True, slots=True)
class _TaskState:
    task: Task
    ahead: list[ShiftFill]
    #: The visible lists it is on, any status.
    lists: list[ListState]
    stranded_free: int
    unlisted_free: int


async def load(
    session: AsyncSession, event: Event, *, now_wall: dt.datetime
) -> Snapshot:
    """Read the event's lists, their tasks and every shift they could offer.

    Six queries, however many lists, tasks or shifts there are.
    """
    lists = await crud_overview.lists(session, event_id=event.id)
    listed = await crud_overview.listed_tasks(session, event_id=event.id)
    excluded = await crud_overview.excluded(session, event_id=event.id)
    tasks = await crud_overview.published_tasks(session, event_id=event.id)
    shifts: dict[uuid.UUID, list[ShiftFill]] = {}
    for shift in await crud_overview.event_shifts(session, event_id=event.id):
        shifts.setdefault(shift.task_id, []).append(shift)
    signups = await crud_overview.signup_counts(session, event_id=event.id)
    return Snapshot(
        event=event,
        now_wall=now_wall,
        lists=lists,
        listed=listed,
        excluded=excluded,
        tasks={task.id: task for task in tasks},
        shifts=shifts,
        signups=signups,
    )


def _starts_at(shift: ShiftFill) -> dt.datetime:
    return offer.starts_at(shift.date, shift.start_time)


def evaluate(snapshot: Snapshot) -> list[ListState]:
    """Every list of the event on the event's clock, by the rules of ``offer``."""
    states: list[ListState] = []
    for shared_list in snapshot.lists:
        current = [
            task
            for task in snapshot.listed.get(shared_list.id, [])
            if task.event_id == shared_list.event_id
        ]
        offered = [task for task in current if offer.offerable(task)]
        excluded = snapshot.excluded.get(shared_list.id, frozenset())
        shifts = [s for task in offered for s in snapshot.shifts.get(task.task_id, [])]
        last_start = max(
            (_starts_at(s) for s in shifts if s.id not in excluded), default=None
        )
        ahead = [s for s in shifts if _starts_at(s) > snapshot.now_wall]
        states.append(
            ListState(
                shared_list=shared_list,
                current=current,
                offered=offered,
                ahead=ahead,
                open=[s for s in ahead if s.id not in excluded],
                last_start=last_start,
                effective=offer.effective_status(
                    shared_list,
                    event=snapshot.event,
                    last_start=last_start,
                    now_wall=snapshot.now_wall,
                ),
            )
        )
    return states


def coverage(states: Iterable[ListState]) -> Coverage:
    live: set[uuid.UUID] = set()
    listed: set[uuid.UUID] = set()
    for state in states:
        ids = {s.id for s in state.open}
        if state.effective == "live":
            live |= ids
        if state.effective != "ended":
            listed |= ids
    return Coverage(live=frozenset(live), listed=frozenset(listed))


def _visible(
    scope: SharedListScope, states: Iterable[ListState]
) -> list[tuple[ListState, SharedListAccess]]:
    out: list[tuple[ListState, SharedListAccess]] = []
    for state in states:
        access = scope.access_to(task.task_id for task in state.current)
        if access is not None:
            out.append((state, access))
    return out


def _only_days(
    ahead: Sequence[ShiftFill], offered: Sequence[ShiftFill]
) -> list[dt.date] | None:
    """The days offered, when some day ahead is left out entirely; else None."""
    days = {s.date for s in offered}
    if {s.date for s in ahead} <= days:
        return None
    return sorted(days)


def _task_names(state: ListState, shifts: Iterable[ShiftFill]) -> list[str]:
    """The tasks of ``shifts``, once each, in the list's order."""
    task_ids = {s.task_id for s in shifts}
    return [task.name for task in state.offered if task.task_id in task_ids]


def _issue(
    state: ListState, cover: Coverage, *, now_wall: dt.datetime
) -> SharedListIssue | None:
    shared_list = state.shared_list
    if state.effective in ("paused", "expired"):
        stranded = [s for s in state.open if s.free and s.id not in cover.live]
        if not stranded:
            return None
        return SharedListIssue(
            kind="stranded",
            free=sum(s.free for s in stranded),
            task_names=_task_names(state, stranded),
        )
    if state.free and offer.expires_soon(
        shared_list, effective=state.effective, now_wall=now_wall
    ):
        assert shared_list.ends_on is not None  # a date list (expires_soon)
        return SharedListIssue(
            kind="expires_soon",
            free=state.free,
            task_names=_task_names(state, (s for s in state.open if s.free)),
            days_left=(shared_list.ends_on - now_wall.date()).days,
        )
    return None


def list_row(
    snapshot: Snapshot,
    state: ListState,
    *,
    access: SharedListAccess,
    cover: Coverage,
) -> SharedListRow:
    shared_list = state.shared_list
    counts = snapshot.signups.get(shared_list.id, SignupCounts(signups=0, guests=0))
    may_change = access != "viewer" and state.effective != "ended"
    return SharedListRow(
        id=shared_list.id,
        code=shared_list.code,
        title=shared_list.title,
        share_note=shared_list.share_note,
        status=cast(ListStatus, shared_list.status),
        effective_status=state.effective,
        ends_mode=cast(EndsMode, shared_list.ends_mode),
        ends_on=shared_list.ends_on,
        closes_at=offer.closes_at(shared_list, last_start=state.last_start),
        expires_soon=offer.expires_soon(
            shared_list, effective=state.effective, now_wall=snapshot.now_wall
        ),
        is_full=bool(state.open) and state.free == 0,
        created_at=shared_list.created_at,
        created_by_name=shared_list.created_by_name,
        tasks=[SharedListTaskRef(id=t.task_id, name=t.name) for t in state.current],
        only_days=_only_days(state.ahead, state.open),
        excluded_shift_count=len(state.ahead) - len(state.open),
        capacity=state.capacity,
        free=state.free,
        signup_count=counts.signups,
        guest_count=counts.guests,
        view_count=shared_list.view_count,
        issue=_issue(state, cover, now_wall=snapshot.now_wall) if may_change else None,
        access=access,
    )


def _not_offered_reason(
    task: ListedTask, shared_list: SharedList
) -> Literal["team_locked", "not_published", "moved"] | None:
    if task.event_id != shared_list.event_id:
        return "moved"
    if task.status != "published":
        return "not_published"
    if task.team_id is not None:
        return "team_locked"
    return None


def detail(
    snapshot: Snapshot, shared_list_id: uuid.UUID, *, access: SharedListAccess
) -> SharedListDetail:
    """One list with its settings and what it offers of each task.

    ``access`` comes from the caller's gate. Every list of the event is
    evaluated all the same: whether its free places are stranded depends on the
    others.
    """
    states = evaluate(snapshot)
    state = next(s for s in states if s.shared_list.id == shared_list_id)
    shared_list = state.shared_list
    row = list_row(snapshot, state, access=access, cover=coverage(states))
    detail_tasks: list[SharedListDetailTask] = []
    for task in snapshot.listed.get(shared_list.id, []):
        reason = _not_offered_reason(task, shared_list)
        ahead = [s for s in state.ahead if s.task_id == task.task_id]
        offered = [s for s in state.open if s.task_id == task.task_id]
        detail_tasks.append(
            SharedListDetailTask(
                id=task.task_id,
                name=task.name,
                offered=reason is None,
                not_offered_reason=reason,
                shift_count=len(offered),
                capacity=sum(s.max_bookings for s in offered),
                free=sum(s.free for s in offered),
                only_days=_only_days(ahead, offered),
            )
        )
    event = snapshot.event
    return SharedListDetail(
        **row.model_dump(),
        intro=shared_list.intro,
        ask_email=cast(AskMode, shared_list.ask_email),
        ask_phone=cast(AskMode, shared_list.ask_phone),
        show_names=cast(ShowNames, shared_list.show_names),
        max_per_person=shared_list.max_per_person,
        rotated_at=shared_list.rotated_at,
        paused_at=shared_list.paused_at,
        ended_at=shared_list.ended_at,
        task_ids=[task.task_id for task in snapshot.listed.get(shared_list.id, [])],
        excluded_shift_ids=sorted(snapshot.excluded.get(shared_list.id, frozenset())),
        detail_tasks=detail_tasks,
        event=SharedListEventRef(
            id=event.id,
            name=event.name,
            start_date=event.start_date,
            end_date=event.end_date,
            timezone=event.timezone,
        ),
    )


def reusable(
    snapshot: Snapshot,
    scope: SharedListScope,
    *,
    task_ids: Collection[uuid.UUID],
    covering: bool = False,
) -> SharedListRow | None:
    """The list a printed notice of ``task_ids`` reuses, so it keeps its link;
    None if there is none.

    A list the caller manages that has not ended, whose current tasks (those
    still in its event) are exactly ``task_ids`` or, with ``covering``,
    include them all. The newest live one, else the newest paused or expired
    one: its notice offers to resume it rather than a second list beside it.
    """
    wanted = frozenset(task_ids)
    states = evaluate(snapshot)

    def holds(state: ListState) -> bool:
        have = frozenset(task.task_id for task in state.current)
        return wanted <= have if covering else wanted == have

    matching: list[tuple[ListState, SharedListAccess]] = [
        (state, access)
        for state, access in _visible(scope, states)
        if access != "viewer" and state.effective != "ended" and holds(state)
    ]
    if not matching:
        return None
    state, access = max(
        matching,
        key=lambda pair: (
            pair[0].effective == "live",
            pair[0].shared_list.created_at,
            pair[0].shared_list.id,
        ),
    )
    return list_row(snapshot, state, access=access, cover=coverage(states))


def _matches(needle: str | None, *haystack: str | None) -> bool:
    """Case-insensitive substring search; no needle matches everything."""
    if not needle:
        return True
    return any(needle in text.casefold() for text in haystack if text)


def _needle(q: str | None) -> str | None:
    return (q.strip().casefold() or None) if q else None


def _names_in_charge(
    managers: dict[uuid.UUID, list[tuple[TaskManager, User]]], task_id: uuid.UUID
) -> list[str]:
    return [user.name for _, user in managers.get(task_id, []) if user.name]


def _team(team_id: uuid.UUID | None, names: dict[uuid.UUID, str]) -> TeamRef | None:
    if team_id is None or team_id not in names:
        return None
    return TeamRef(id=team_id, name=names[team_id])


def _ordered(
    rows: Sequence[_Row], key: Callable[[_Row], Any], *, descending: bool
) -> list[_Row]:
    """Sorted by ``key``, ties by id so pages never overlap, and rows without a
    value (None) last in either direction."""
    by_id = sorted(rows, key=lambda row: row.id)
    present = [row for row in by_id if key(row) is not None]
    # Stable in both directions, so ties keep the id order.
    present.sort(key=key, reverse=descending)
    return present + [row for row in by_id if key(row) is None]


#: Each sort key, with its direction when the caller names none.
_LIST_SORTS: dict[ListSort, tuple[Callable[[SharedListRow], Any], SortDir]] = {
    "status": (lambda row: _STATUS_RANK[row.effective_status], "asc"),
    "created_at": (lambda row: row.created_at, "desc"),
    "title": (lambda row: row.title.casefold(), "asc"),
    "signups": (lambda row: row.signup_count, "desc"),
    "free": (lambda row: row.free, "desc"),
    "closes": (lambda row: row.closes_at, "asc"),
}

_TASK_SORTS: dict[TaskSort, tuple[Callable[[SharedListTaskRow], Any], SortDir]] = {
    "name": (lambda row: row.name.casefold(), "asc"),
    "free": (lambda row: row.free, "desc"),
    "unlisted_free": (lambda row: row.unlisted_free, "desc"),
}


def _in_list_filter(row: SharedListRow, status_filter: ListFilter) -> bool:
    if status_filter == "active":
        return row.effective_status != "ended"
    if status_filter == "todo":
        return row.issue is not None
    return row.effective_status == status_filter


def list_page(
    snapshot: Snapshot,
    scope: SharedListScope,
    *,
    status_filter: ListFilter,
    q: str | None,
    sort_by: ListSort,
    sort_dir: SortDir | None,
    skip: int,
    limit: int,
) -> SharedListListResponse:
    """The lists table: the caller's lists, filtered, searched, sorted, paged.

    ``q`` is matched in the title, the share note, the creator's name and the
    task names. The chip counts ignore it; ``ended_matching`` does not.
    """
    states = evaluate(snapshot)
    cover = coverage(states)
    rows = [
        list_row(snapshot, state, access=access, cover=cover)
        for state, access in _visible(scope, states)
    ]
    counts = SharedListCounts(
        active=sum(_in_list_filter(row, "active") for row in rows),
        todo=sum(_in_list_filter(row, "todo") for row in rows),
        live=sum(_in_list_filter(row, "live") for row in rows),
        paused=sum(_in_list_filter(row, "paused") for row in rows),
        ended=sum(_in_list_filter(row, "ended") for row in rows),
    )
    needle = _needle(q)
    matching = [
        row
        for row in rows
        if _matches(
            needle,
            row.title,
            row.share_note,
            row.created_by_name,
            *(task.name for task in row.tasks),
        )
    ]
    selected = [row for row in matching if _in_list_filter(row, status_filter)]
    key, default_dir = _LIST_SORTS[sort_by]
    ordered = _ordered(selected, key, descending=(sort_dir or default_dir) == "desc")
    return SharedListListResponse(
        items=ordered[skip : skip + limit],
        total=len(selected),
        skip=skip,
        limit=limit,
        counts=counts,
        ended_matching=sum(row.effective_status == "ended" for row in matching),
    )


def _task_states(
    snapshot: Snapshot,
    scope: SharedListScope,
    visible: Sequence[tuple[ListState, SharedListAccess]],
    cover: Coverage,
) -> list[_TaskState]:
    """The published tasks with shifts ahead the caller sees: every one for
    an event admin, those they are in charge of for anyone else."""
    lists_of: dict[uuid.UUID, list[ListState]] = {}
    for state, _ in visible:
        for listed in state.current:
            lists_of.setdefault(listed.task_id, []).append(state)
    out: list[_TaskState] = []
    for task in snapshot.tasks.values():
        if not scope.is_admin and task.id not in scope.managed_task_ids:
            continue
        ahead = [
            s
            for s in snapshot.shifts.get(task.id, [])
            if _starts_at(s) > snapshot.now_wall
        ]
        if not ahead:
            continue
        # A team task's places can be on no list, so none of them is "left
        # unshared"; the table says "only through the team" instead.
        shareable = ahead if task.team_id is None else []
        out.append(
            _TaskState(
                task=task,
                ahead=ahead,
                lists=lists_of.get(task.id, []),
                stranded_free=sum(s.free for s in shareable if s.id not in cover.live),
                unlisted_free=sum(
                    s.free for s in shareable if s.id not in cover.listed
                ),
            )
        )
    return out


async def task_page(
    session: AsyncSession,
    snapshot: Snapshot,
    scope: SharedListScope,
    *,
    status_filter: TaskFilter,
    q: str | None,
    sort_by: TaskSort,
    sort_dir: SortDir | None,
    skip: int,
    limit: int,
) -> SharedListTaskListResponse:
    """The tasks table: the caller's published tasks with shifts ahead, and
    which lists offer their free places.

    ``todo`` holds the tasks with free places no live list offers. ``q`` is
    matched in the name, the place and the names of the people in charge.
    Two queries on top of the snapshot, for those names and the teams.
    """
    states = evaluate(snapshot)
    cover = coverage(states)
    task_states = _task_states(snapshot, scope, _visible(scope, states), cover)
    managers = await crud_task_manager.managers_for_tasks(
        session, task_ids=(t.task.id for t in task_states)
    )
    teams = await crud_overview.team_names(
        session,
        team_ids={t.task.team_id for t in task_states if t.task.team_id is not None},
    )
    may_share = scope.is_admin or scope.managers_share_lists
    rows: list[SharedListTaskRow] = []
    for t in task_states:
        task = t.task
        rows.append(
            SharedListTaskRow(
                id=task.id,
                name=task.name,
                location=task.location,
                manager_names=_names_in_charge(managers, task.id),
                shift_count=len(t.ahead),
                dates=sorted({s.date for s in t.ahead}),
                capacity=sum(s.max_bookings for s in t.ahead),
                free=sum(s.free for s in t.ahead),
                team=_team(task.team_id, teams),
                lists=[
                    SharedListChip(
                        id=state.shared_list.id,
                        title=state.shared_list.title,
                        effective_status=state.effective,
                    )
                    for state in t.lists
                    if state.effective != "ended"
                ],
                ended_list_count=sum(state.effective == "ended" for state in t.lists),
                stranded_free=t.stranded_free,
                unlisted_free=t.unlisted_free,
                can_share=task.team_id is None and may_share,
            )
        )
    needle = _needle(q)
    selected = [
        row
        for row in rows
        if (status_filter == "all" or row.stranded_free > 0)
        and _matches(needle, row.name, row.location, *row.manager_names)
    ]
    key, default_dir = _TASK_SORTS[sort_by]
    ordered = _ordered(selected, key, descending=(sort_dir or default_dir) == "desc")
    return SharedListTaskListResponse(
        items=ordered[skip : skip + limit],
        total=len(selected),
        skip=skip,
        limit=limit,
        counts=SharedListTaskCounts(
            all=len(rows), todo=sum(row.stranded_free > 0 for row in rows)
        ),
    )


def summary(snapshot: Snapshot, scope: SharedListScope) -> SharedListOverview:
    """The figures above the tables, and what the caller may do."""
    states = evaluate(snapshot)
    visible = _visible(scope, states)
    task_states = _task_states(snapshot, scope, visible, coverage(states))
    live = [state for state, _ in visible if state.effective == "live"]
    # A shift on two live lists is one shift with its free places once.
    live_shifts = {s.id: s for state in live for s in state.open}
    counts = [
        snapshot.signups.get(state.shared_list.id, SignupCounts(signups=0, guests=0))
        for state, _ in visible
    ]
    todo = sorted(
        (t for t in task_states if t.stranded_free),
        key=lambda t: (t.task.name.casefold(), t.task.id),
    )
    return SharedListOverview(
        summary=SharedListSummary(
            live_lists=len(live),
            active_lists=sum(state.effective != "ended" for state, _ in visible),
            signups=sum(c.signups for c in counts),
            guests=sum(c.guests for c in counts),
            free_in_live=sum(s.free for s in live_shifts.values()),
        ),
        unshared=UnsharedNotice(
            task_count=len(todo),
            free=sum(t.stranded_free for t in todo),
            task_names=[t.task.name for t in todo[:2]],
        ),
        # A person in charge sees only their own tasks here, so any task
        # without a team is one they could share.
        can_create=scope.is_admin
        or (
            scope.managers_share_lists
            and any(t.task.team_id is None for t in task_states)
        ),
        can_pause_all=scope.is_admin and bool(live),
        is_admin=scope.is_admin,
        managers_share_lists=scope.managers_share_lists,
        event_timezone=snapshot.event.timezone,
    )


async def candidate_page(
    session: AsyncSession,
    event: Event,
    scope: SharedListScope,
    *,
    now_wall: dt.datetime,
    q: str | None,
    skip: int,
    limit: int,
) -> SharedListCandidateListResponse:
    """The wizard's task picker: a page of the tasks the caller may put on a
    list, by name, with their shifts ahead.

    Team tasks show up only in a search, marked with their team; without one
    ``locked_count`` and ``locked_names`` stand for them.
    """
    if scope.is_admin:
        managed: frozenset[uuid.UUID] | None = None
    else:
        managed = scope.managed_task_ids
    q = q.strip() if q else None
    tasks, total = await crud_overview.candidates(
        session,
        event_id=event.id,
        managed_task_ids=managed,
        now_wall=now_wall,
        q=q,
        skip=skip,
        limit=limit,
    )
    locked = await crud_overview.team_task_names(
        session, event_id=event.id, managed_task_ids=managed, now_wall=now_wall
    )
    shifts: dict[uuid.UUID, list[ShiftFill]] = {}
    for shift in await crud_overview.task_shifts(
        session, event_id=event.id, task_ids=[t.id for t in tasks]
    ):
        if _starts_at(shift) > now_wall:
            shifts.setdefault(shift.task_id, []).append(shift)
    managers = await crud_task_manager.managers_for_tasks(
        session, task_ids=(t.id for t in tasks)
    )
    teams = await crud_overview.team_names(
        session, team_ids={t.team_id for t in tasks if t.team_id is not None}
    )
    items: list[SharedListCandidate] = []
    for task in tasks:
        ahead = shifts.get(task.id, [])
        items.append(
            SharedListCandidate(
                id=task.id,
                name=task.name,
                location=task.location,
                manager_names=_names_in_charge(managers, task.id),
                shift_count=len(ahead),
                dates=sorted({s.date for s in ahead}),
                capacity=sum(s.max_bookings for s in ahead),
                free=sum(s.free for s in ahead),
                team=_team(task.team_id, teams),
                earns_vouchers=task.vouchers_per_shift > 0,
            )
        )
    return SharedListCandidateListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        locked_count=len(locked),
        locked_names=locked[:3],
    )


async def candidate_shifts(
    session: AsyncSession,
    event: Event,
    *,
    task_ids: Sequence[uuid.UUID],
    now_wall: dt.datetime,
) -> list[SharedListCandidateShift]:
    """The shifts ahead of those of ``task_ids`` that are in the event, by start."""
    shifts = await crud_overview.task_shifts(
        session, event_id=event.id, task_ids=set(task_ids)
    )
    return [
        SharedListCandidateShift(
            id=s.id,
            task_id=s.task_id,
            date=s.date,
            start_time=s.start_time,
            end_time=s.end_time,
            capacity=s.max_bookings,
            free=s.free,
        )
        for s in shifts
        if _starts_at(s) > now_wall
    ]
