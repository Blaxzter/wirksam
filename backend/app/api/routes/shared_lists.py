"""Managing shared lists: the tables, the wizard's choices, the list a printed
notice reuses, and creating, editing, pausing, resuming, ending and rotating
lists.

Every route answers 404 ``shared_list.disabled`` while ``SHARED_LISTS_ENABLED``
is off. The routes of an event load it and pass ``shared_list_scope`` (or
``require_shared_list_tasks``), which test a sandbox before the role; the
routes of one list pass ``require_shared_list_visible`` or
``require_shared_list_manager``, all in ``app.logic.permissions``. What the
views show is worked out in ``app.logic.shared_lists.overview``, what a change
does in ``app.logic.shared_lists.manage``. Each request reads the event's clock
once.
"""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DBDep, require_shared_lists_enabled
from app.core.errors import raise_problem
from app.crud.event import event as crud_event
from app.crud.shared_list import shared_list as crud_shared_list
from app.logic import clock
from app.logic.permissions import (
    SharedListAccess,
    require_event_role,
    require_shared_list_manager,
    require_shared_list_tasks,
    require_shared_list_visible,
    shared_list_scope,
)
from app.logic.sandbox.guards import refuse_if_sandbox
from app.logic.shared_lists import manage, overview
from app.logic.shared_lists.manage import TransitionAction
from app.models.event import Event
from app.models.shared_list import SharedList
from app.models.user import User
from app.schemas.shared_list import (
    ListFilter,
    ListSort,
    SharedListBulkRequest,
    SharedListBulkResult,
    SharedListCandidateListResponse,
    SharedListCandidateShift,
    SharedListCreate,
    SharedListDetail,
    SharedListListResponse,
    SharedListOverview,
    SharedListPauseAllRequest,
    SharedListReusable,
    SharedListTaskListResponse,
    SharedListUpdate,
    SortDir,
    TaskFilter,
    TaskSort,
)

router = APIRouter(
    tags=["shared-lists"], dependencies=[Depends(require_shared_lists_enabled)]
)

Skip = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]
Search = Annotated[str | None, Query(max_length=100)]


async def _event(
    session: AsyncSession, event_id: uuid.UUID, *, for_change: bool = False
) -> Event:
    """The event; for a change to its lists, read ``FOR SHARE`` before the
    gate reads ``managers_share_lists``, as ``manage.lock_for_change`` does
    for one list, so an emergency stop that switches it off is waited for."""
    if for_change:
        event = await crud_event.lock(session, event_id, mode="share")
    else:
        event = await crud_event.get(session, event_id)
    if event is None:
        raise_problem(404, code="event.not_found", detail="Event not found")
    return event


async def _shared_list(
    session: AsyncSession, list_id: uuid.UUID, *, for_change: bool = False
) -> SharedList:
    if for_change:
        shared_list = await manage.lock_for_change(session, list_id)
    else:
        shared_list = await crud_shared_list.get(session, shared_list_id=list_id)
    if shared_list is None:
        raise_problem(404, code="shared_list.not_found", detail="Shared list not found")
    return shared_list


async def _detail(
    session: AsyncSession,
    event: Event,
    shared_list: SharedList,
    *,
    access: SharedListAccess,
    now_wall: dt.datetime,
) -> SharedListDetail:
    snapshot = await overview.load(session, event, now_wall=now_wall)
    return overview.detail(snapshot, shared_list.id, access=access)


# --- One event's lists ------------------------------------------------------


@router.get("/events/{event_id}/shared-lists", response_model=SharedListListResponse)
async def list_shared_lists(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    status_filter: ListFilter = "active",
    q: Search = None,
    sort_by: ListSort = "status",
    sort_dir: SortDir | None = None,
    skip: Skip = 0,
    limit: Limit = 20,
) -> SharedListListResponse:
    """The lists the caller may see, with the counts of every filter chip.

    ``sort_dir`` defaults per key: ascending for status, title and closing
    time, descending for creation, sign-ups and free places. Ties go by id,
    and lists that close only by hand come last by closing time.
    """
    event = await _event(session, event_id)
    scope = await shared_list_scope(current_user, session, event)
    snapshot = await overview.load(
        session, event, now_wall=clock.wall_clock_now(event.timezone)
    )
    return overview.list_page(
        snapshot,
        scope,
        status_filter=status_filter,
        q=q,
        sort_by=sort_by,
        sort_dir=sort_dir,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/events/{event_id}/shared-lists/overview", response_model=SharedListOverview
)
async def get_shared_lists_overview(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> SharedListOverview:
    """The figures above the tables and what the caller may do there."""
    event = await _event(session, event_id)
    scope = await shared_list_scope(current_user, session, event)
    snapshot = await overview.load(
        session, event, now_wall=clock.wall_clock_now(event.timezone)
    )
    return overview.summary(snapshot, scope)


@router.get(
    "/events/{event_id}/shared-lists/tasks", response_model=SharedListTaskListResponse
)
async def list_shared_list_tasks(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    status_filter: TaskFilter = "all",
    q: Search = None,
    sort_by: TaskSort = "name",
    sort_dir: SortDir | None = None,
    skip: Skip = 0,
    limit: Limit = 20,
) -> SharedListTaskListResponse:
    """The caller's published tasks with shifts ahead, and the lists they are on.

    ``sort_dir`` defaults to ascending for the name and descending otherwise.
    """
    event = await _event(session, event_id)
    scope = await shared_list_scope(current_user, session, event)
    snapshot = await overview.load(
        session, event, now_wall=clock.wall_clock_now(event.timezone)
    )
    return await overview.task_page(
        session,
        snapshot,
        scope,
        status_filter=status_filter,
        q=q,
        sort_by=sort_by,
        sort_dir=sort_dir,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/events/{event_id}/shared-lists/candidates",
    response_model=SharedListCandidateListResponse,
)
async def list_shared_list_candidates(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    q: Search = None,
    skip: Skip = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
) -> SharedListCandidateListResponse:
    """The tasks the caller may put on a list, by name; ``q`` searches the
    name and the place."""
    event = await _event(session, event_id)
    scope = await shared_list_scope(current_user, session, event)
    return await overview.candidate_page(
        session,
        event,
        scope,
        now_wall=clock.wall_clock_now(event.timezone),
        q=q,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/events/{event_id}/shared-lists/candidate-shifts",
    response_model=list[SharedListCandidateShift],
)
async def list_shared_list_candidate_shifts(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    task_id: Annotated[list[uuid.UUID], Query(min_length=1, max_length=50)],
) -> list[SharedListCandidateShift]:
    """The shifts ahead of the chosen tasks, by start, to leave some out."""
    event = await _event(session, event_id)
    await require_shared_list_tasks(current_user, session, event, task_id)
    return await overview.candidate_shifts(
        session,
        event,
        task_ids=task_id,
        now_wall=clock.wall_clock_now(event.timezone),
    )


@router.get(
    "/events/{event_id}/shared-lists/reusable",
    response_model=SharedListReusable,
)
async def find_reusable_shared_list(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    task_id: Annotated[list[uuid.UUID], Query(min_length=1, max_length=50)],
    covering: bool = False,
) -> SharedListReusable:
    """The list a printed notice of these tasks reuses, so it keeps its link
    (``overview.reusable``); ``list`` null when there is none. A whole
    event's print passes ``covering``: its list stays the one while some of
    its tasks have nothing left to offer.

    Gated like sharing the tasks: whoever could not create a list of them
    gets the refusal creating it would answer.
    """
    event = await _event(session, event_id)
    await require_shared_list_tasks(current_user, session, event, task_id)
    scope = await shared_list_scope(current_user, session, event)
    snapshot = await overview.load(
        session, event, now_wall=clock.wall_clock_now(event.timezone)
    )
    return SharedListReusable(
        list=overview.reusable(snapshot, scope, task_ids=task_id, covering=covering)
    )


@router.post(
    "/events/{event_id}/shared-lists",
    response_model=SharedListDetail,
    status_code=201,
)
async def create_shared_list(
    event_id: uuid.UUID,
    body: SharedListCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> SharedListDetail:
    """Share tasks of the event as a new live list."""
    event = await _event(session, event_id, for_change=True)
    access = await require_shared_list_tasks(
        current_user, session, event, body.task_ids
    )
    # After the gate, which 404s someone else's demo: the demo's own guest
    # owns it and passes every gate, and a demo must not reach strangers.
    await refuse_if_sandbox(
        session,
        event.id,
        code="sandbox.shared_lists_disabled",
        detail="Shared lists cannot be published from a demo event",
    )
    now_wall = clock.wall_clock_now(event.timezone)
    shared_list = await manage.create(
        session, event=event, user=current_user, body=body, now_wall=now_wall
    )
    return await _detail(session, event, shared_list, access=access, now_wall=now_wall)


@router.post(
    "/events/{event_id}/shared-lists/bulk", response_model=SharedListBulkResult
)
async def bulk_update_shared_lists(
    event_id: uuid.UUID,
    body: SharedListBulkRequest,
    session: DBDep,
    current_user: CurrentUser,
) -> SharedListBulkResult:
    """Pause, resume or end several lists. A list the caller may not change,
    or that refuses the action, is reported in ``skipped``."""
    event = await _event(session, event_id, for_change=True)
    scope = await shared_list_scope(current_user, session, event)
    return await manage.bulk(
        session,
        event=event,
        scope=scope,
        action=body.action,
        list_ids=body.list_ids,
        now_utc=clock.utc_now(),
        now_wall=clock.wall_clock_now(event.timezone),
    )


@router.post(
    "/events/{event_id}/shared-lists/pause-all", response_model=SharedListBulkResult
)
async def pause_all_shared_lists(
    event_id: uuid.UUID,
    body: SharedListPauseAllRequest,
    session: DBDep,
    current_user: CurrentUser,
) -> SharedListBulkResult:
    """Event admins: pause every list of the event that is still open."""
    event = await _event(session, event_id)
    # The scope first: it 404s someone else's demo before the role is asked.
    await shared_list_scope(current_user, session, event)
    await require_event_role(current_user, session, event.id, minimum="admin")
    return await manage.pause_all(
        session,
        event=event,
        now_utc=clock.utc_now(),
        lock_managers=body.lock_managers,
    )


# --- One list -------------------------------------------------------------


@router.get("/shared-lists/{list_id}", response_model=SharedListDetail)
async def get_shared_list(
    list_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> SharedListDetail:
    shared_list = await _shared_list(session, list_id)
    access = await require_shared_list_visible(current_user, session, shared_list)
    event = await _event(session, shared_list.event_id)
    return await _detail(
        session,
        event,
        shared_list,
        access=access,
        now_wall=clock.wall_clock_now(event.timezone),
    )


@router.patch("/shared-lists/{list_id}", response_model=SharedListDetail)
async def update_shared_list(
    list_id: uuid.UUID,
    body: SharedListUpdate,
    session: DBDep,
    current_user: CurrentUser,
) -> SharedListDetail:
    """Edit a list; its link stays the same."""
    shared_list = await _shared_list(session, list_id, for_change=True)
    access = await require_shared_list_manager(
        current_user, session, shared_list, "edit"
    )
    event = await _event(session, shared_list.event_id)
    if body.task_ids is not None:
        await require_shared_list_tasks(current_user, session, event, body.task_ids)
    now_wall = clock.wall_clock_now(event.timezone)
    await manage.update(
        session, shared_list, event=event, changes=body, now_wall=now_wall
    )
    return await _detail(session, event, shared_list, access=access, now_wall=now_wall)


async def _transition(
    session: AsyncSession,
    user: User,
    list_id: uuid.UUID,
    action: TransitionAction,
) -> SharedListDetail:
    shared_list = await _shared_list(session, list_id, for_change=True)
    access = await require_shared_list_manager(user, session, shared_list, action)
    event = await _event(session, shared_list.event_id)
    now_wall = clock.wall_clock_now(event.timezone)
    await manage.transition(
        session,
        shared_list,
        action,
        event=event,
        now_utc=clock.utc_now(),
        now_wall=now_wall,
    )
    return await _detail(session, event, shared_list, access=access, now_wall=now_wall)


@router.post("/shared-lists/{list_id}/pause", response_model=SharedListDetail)
async def pause_shared_list(
    list_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> SharedListDetail:
    """Stop new sign-ups for now. Pausing a paused list changes nothing."""
    return await _transition(session, current_user, list_id, "pause")


@router.post("/shared-lists/{list_id}/resume", response_model=SharedListDetail)
async def resume_shared_list(
    list_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> SharedListDetail:
    """Reopen a paused or expired list. One whose closing day is over then
    closes with its last shift."""
    return await _transition(session, current_user, list_id, "resume")


@router.post("/shared-lists/{list_id}/end", response_model=SharedListDetail)
async def end_shared_list(
    list_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> SharedListDetail:
    """End a list for good. Everyone signed up stays signed up."""
    return await _transition(session, current_user, list_id, "end")


@router.post("/shared-lists/{list_id}/rotate", response_model=SharedListDetail)
async def rotate_shared_list(
    list_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> SharedListDetail:
    """Give the list a new link; the old one, printed QR codes included,
    stops working."""
    return await _transition(session, current_user, list_id, "rotate")
