"""Changing shared lists: create, edit, pause, resume, end and rotate them.

Every change to a list runs under its row lock, which waits for the sign-ups
in flight, taken after its event's (:func:`lock_for_change`); the routes take
them and pass the shared-list gates of ``app.logic.permissions`` first.
Ending, pausing and editing never touch bookings: whoever signed up stays
signed up.

``ended`` is final. "Expired" is never stored (``offer.effective_status``), so
resuming an expired list works it out again, on the event's clock.
"""

import datetime as dt
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any, Literal, NoReturn, cast

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.core.errors import raise_problem
from app.crud.event import event as crud_event
from app.crud.shared_list import shared_list as crud_shared_list
from app.crud.shared_list_overview import shared_list_overview as crud_overview
from app.logic.permissions import SharedListScope, shared_list_change_refusal
from app.logic.shared_lists import offer, overview
from app.logic.shared_lists.offer import EffectiveStatus
from app.models.event import Event
from app.models.shared_list import EndsMode, SharedList
from app.models.task import Task
from app.models.user import User
from app.schemas.shared_list import (
    BulkAction,
    SharedListBulkResult,
    SharedListBulkSkip,
    SharedListCreate,
    SharedListUpdate,
)

TransitionAction = Literal["pause", "resume", "end", "rotate"]


@dataclass(frozen=True, slots=True)
class Refusal:
    """Why a list refuses a change of its status: the 409 the single action
    answers with, and the code a batch reports."""

    code: str
    detail: str

    def raise_(self) -> NoReturn:
        raise_problem(409, code=self.code, detail=self.detail)


_ENDED = Refusal("shared_list.ended", "This list has ended")
_NOT_LIVE = Refusal(
    "shared_list.not_live", "This list is not open, so there is nothing to pause"
)
_NOT_PUBLISHED = Refusal(
    "shared_list.event_not_published",
    "Lists can only be shared for a published event",
)
_NOTHING_TO_OFFER = Refusal(
    "shared_list.nothing_to_offer",
    "Every shift on this list has started, so it cannot reopen",
)


async def lock_for_change(
    session: AsyncSession, shared_list_id: uuid.UUID
) -> SharedList | None:
    """The list ``FOR UPDATE``, for any change to it, after its event ``FOR
    SHARE`` (``crud.event.lock``).

    The event first, as an emergency stop (:func:`pause_all`) and deleting
    the event take it: the stop may switch ``managers_share_lists`` off, and
    a person in charge resuming a list beside it must either see that or
    happen before it.
    """
    found = await crud_shared_list.get(session, shared_list_id=shared_list_id)
    if found is None:
        return None
    await crud_event.lock(session, found.event_id, mode="share")
    return await crud_shared_list.get_for_update(session, shared_list_id=shared_list_id)


#: Fields a list always has a value for: an explicit null in an edit keeps it.
_ALWAYS_SET = (
    "title",
    "task_ids",
    "excluded_shift_ids",
    "ask_email",
    "ask_phone",
    "show_names",
    "ends_mode",
)

#: Edits that change what the list offers or how long, and so are checked
#: like a new list.
_SELECTION_FIELDS = frozenset(
    {"task_ids", "excluded_shift_ids", "ends_mode", "ends_on"}
)


def refuse_ended(shared_list: SharedList) -> None:
    """409 ``shared_list.ended``: an ended list cannot be changed or reopened."""
    if shared_list.status == "ended":
        _ENDED.raise_()


def _require_published(event: Event) -> None:
    if event.status != "published":
        _NOT_PUBLISHED.raise_()


def _closing_day(ends_mode: EndsMode, ends_on: dt.date | None) -> dt.date | None:
    """``ends_on`` counts only for a list that closes on a day."""
    return ends_on if ends_mode == "date" else None


def _reopened_closing(
    shared_list: SharedList, now_wall: dt.datetime
) -> tuple[EndsMode, dt.date | None]:
    """How a resumed list closes. One whose closing day is over then closes
    with its last shift, so it stays open as long as it has something to
    offer rather than for no time at all."""
    if shared_list.ends_on is not None and now_wall.date() > shared_list.ends_on:
        return "last_shift", None
    return cast(EndsMode, shared_list.ends_mode), shared_list.ends_on


def change_status(
    shared_list: SharedList,
    action: BulkAction,
    *,
    event: Event,
    last_start: dt.datetime | None,
    effective: EffectiveStatus,
    now_utc: dt.datetime,
    now_wall: dt.datetime,
) -> Refusal | bool:
    """Pause, resume or end a list held ``FOR UPDATE``: the refusal, or
    whether it changed. ``last_start`` and ``effective`` are its
    ``offer.last_start`` and ``offer.effective_status``.

    - pause: a live list. Paused already: nothing to do. Expired:
      ``shared_list.not_live``, there is nothing open to pause.
    - resume: a paused or expired list. Live already: nothing to do. A list
      whose closing day has passed is switched to close with its last shift.
      ``shared_list.event_not_published``, or ``shared_list.nothing_to_offer``
      when it would still be expired.
    - end: anything not ended yet; final.

    Pause and resume refuse an ended list (``shared_list.ended``).
    ``now_utc`` is stored, ``now_wall`` is the event's clock.
    """
    if action == "end":
        if shared_list.status == "ended":
            return False
        shared_list.status = "ended"
        shared_list.ended_at = now_utc
        return True
    if shared_list.status == "ended":
        return _ENDED
    if action == "pause":
        if effective == "paused":
            return False
        if effective == "expired":
            return _NOT_LIVE
        shared_list.status = "paused"
        shared_list.paused_at = now_utc
        return True
    if effective == "live":
        return False
    if event.status != "published":
        return _NOT_PUBLISHED
    ends_mode, ends_on = _reopened_closing(shared_list, now_wall)
    if ends_mode == "last_shift" and (last_start is None or last_start <= now_wall):
        return _NOTHING_TO_OFFER
    shared_list.status = "live"
    shared_list.paused_at = None
    shared_list.ends_mode = ends_mode
    shared_list.ends_on = ends_on
    return True


async def transition(
    session: AsyncSession,
    shared_list: SharedList,
    action: TransitionAction,
    *,
    event: Event,
    now_utc: dt.datetime,
    now_wall: dt.datetime,
) -> bool:
    """Pause, resume, end or rotate a list held ``FOR UPDATE``; True if it changed.

    As :func:`change_status`, whose refusals are 409s here. Rotate gives
    anything not ended a new code, and the old link stops working.
    ``now_utc`` is stored, ``now_wall`` is the event's clock.
    """
    if action == "rotate":
        refuse_ended(shared_list)
        await crud_shared_list.rotate_code(
            session, shared_list=shared_list, now=now_utc
        )
        return True
    last_start = await offer.last_start(session, shared_list)
    outcome = change_status(
        shared_list,
        action,
        event=event,
        last_start=last_start,
        effective=offer.effective_status(
            shared_list, event=event, last_start=last_start, now_wall=now_wall
        ),
        now_utc=now_utc,
        now_wall=now_wall,
    )
    if isinstance(outcome, Refusal):
        outcome.raise_()
    if outcome:
        session.add(shared_list)
        await session.flush()
    return outcome


async def _tasks(
    session: AsyncSession, task_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, Task]:
    result = await session.execute(select(Task).where(col(Task.id).in_(task_ids)))
    return {task.id: task for task in result.scalars().all()}


def _refuse_tasks(
    task_ids: Sequence[uuid.UUID],
    refused: Collection[uuid.UUID],
    *,
    code: str,
    detail: str,
) -> None:
    if refused:
        raise_problem(
            422,
            code=code,
            detail=detail,
            extensions={
                "task_ids": [str(t) for t in dict.fromkeys(task_ids) if t in refused]
            },
        )


async def validate_selection(
    session: AsyncSession,
    *,
    event: Event,
    task_ids: Sequence[uuid.UUID],
    excluded_shift_ids: Collection[uuid.UUID],
    ends_mode: EndsMode,
    ends_on: dt.date | None,
    now_wall: dt.datetime,
) -> None:
    """Whether a list of ``task_ids`` minus ``excluded_shift_ids`` may be shared.

    In order: the event is published (409); every task is in it, published and
    open to everyone, not just a team (422, naming the tasks in
    ``task_ids``); at least one shift is left that has not started (422
    ``shared_list.no_shifts``) and has a free place (422
    ``shared_list.no_free_places``); a closing day is today or later and no
    later than the last of those shifts (422 ``shared_list.ends_on_invalid``
    with ``last_shift_date``). Excluded ids of other shifts change nothing.
    """
    _require_published(event)
    tasks = await _tasks(session, task_ids)
    _refuse_tasks(
        task_ids,
        {t for t in task_ids if t not in tasks or tasks[t].event_id != event.id},
        code="shared_list.task_not_in_event",
        detail="Only tasks of this event can be on its lists",
    )
    _refuse_tasks(
        task_ids,
        {t for t in task_ids if tasks[t].status != "published"},
        code="shared_list.task_not_published",
        detail="Only published tasks can be shared",
    )
    _refuse_tasks(
        task_ids,
        {t for t in task_ids if tasks[t].team_id is not None},
        code="shared_list.task_team_locked",
        detail="Tasks only a team may book cannot be shared with people without an account",
    )

    excluded = set(excluded_shift_ids)
    offered = [
        s
        for s in await crud_overview.task_shifts(
            session, event_id=event.id, task_ids=task_ids
        )
        if s.id not in excluded and offer.starts_at(s.date, s.start_time) > now_wall
    ]
    if not offered:
        raise_problem(
            422,
            code="shared_list.no_shifts",
            detail="The list would offer no shift that has not started",
        )
    if not any(s.free for s in offered):
        raise_problem(
            422,
            code="shared_list.no_free_places",
            detail="Every shift on the list is full",
        )
    if ends_mode == "date":
        last_day = max(s.date for s in offered)
        if ends_on is None or not now_wall.date() <= ends_on <= last_day:
            raise_problem(
                422,
                code="shared_list.ends_on_invalid",
                detail="The closing day must lie between today and the last shift",
                extensions={"last_shift_date": last_day.isoformat()},
            )


async def create(
    session: AsyncSession,
    *,
    event: Event,
    user: User,
    body: SharedListCreate,
    now_wall: dt.datetime,
) -> SharedList:
    """A new live list, after :func:`validate_selection` and the cap of
    ``SHARED_LISTS_PER_EVENT`` lists per event (409 ``shared_list.too_many``).

    The cap counts ended lists too: it bounds the work of every management
    view, which evaluates all of them. Two creates at the same moment can both
    pass it; it is a bound, not a quota.
    """
    ends_on = _closing_day(body.ends_mode, body.ends_on)
    await validate_selection(
        session,
        event=event,
        task_ids=body.task_ids,
        excluded_shift_ids=body.excluded_shift_ids,
        ends_mode=body.ends_mode,
        ends_on=ends_on,
        now_wall=now_wall,
    )
    if (
        await crud_overview.count_lists(session, event_id=event.id)
        >= settings.SHARED_LISTS_PER_EVENT
    ):
        raise_problem(
            409,
            code="shared_list.too_many",
            detail="This event has as many lists as it can have",
            extensions={"max": settings.SHARED_LISTS_PER_EVENT},
        )
    shared_list = await crud_shared_list.create(
        session,
        event_id=event.id,
        created_by=user,
        title=body.title,
        intro=body.intro,
        share_note=body.share_note,
        ask_email=body.ask_email,
        ask_phone=body.ask_phone,
        show_names=body.show_names,
        max_per_person=body.max_per_person,
        ends_mode=body.ends_mode,
        ends_on=ends_on,
    )
    await crud_shared_list.set_tasks(
        session, shared_list_id=shared_list.id, task_ids=body.task_ids
    )
    await crud_shared_list.set_excluded(
        session, shared_list_id=shared_list.id, shift_ids=body.excluded_shift_ids
    )
    return shared_list


async def _offered_task_ids(
    session: AsyncSession, shared_list: SharedList
) -> list[uuid.UUID]:
    """The list's tasks it can offer now: still in its event, and
    :func:`~app.logic.shared_lists.offer.offerable`."""
    linked = await crud_shared_list.task_ids(session, shared_list_id=shared_list.id)
    tasks = await _tasks(session, linked)
    return [
        task_id
        for task_id in linked
        if task_id in tasks
        and tasks[task_id].event_id == shared_list.event_id
        and offer.offerable(tasks[task_id])
    ]


async def update(
    session: AsyncSession,
    shared_list: SharedList,
    *,
    event: Event,
    changes: SharedListUpdate,
    now_wall: dt.datetime,
) -> None:
    """Edit a list held ``FOR UPDATE``; its code stays the same.

    An edit of the tasks, the exclusions or the closing is checked by
    :func:`validate_selection` against the result: the tasks given, or else
    the ones the list can offer now, so a task that has since been unpublished
    does not block changing the closing day. Other edits are not checked
    against the shifts at all.
    """
    refuse_ended(shared_list)
    data: dict[str, Any] = changes.model_dump(exclude_unset=True)
    for name in _ALWAYS_SET:
        if name in data and data[name] is None:
            del data[name]
    reselect = not _SELECTION_FIELDS.isdisjoint(data)
    task_ids: list[uuid.UUID] | None = data.pop("task_ids", None)
    excluded_ids: list[uuid.UUID] | None = data.pop("excluded_shift_ids", None)
    ends_mode = cast(EndsMode, data.get("ends_mode", shared_list.ends_mode))
    data["ends_mode"] = ends_mode
    data["ends_on"] = _closing_day(ends_mode, data.get("ends_on", shared_list.ends_on))

    if reselect:
        await validate_selection(
            session,
            event=event,
            task_ids=(
                task_ids
                if task_ids is not None
                else await _offered_task_ids(session, shared_list)
            ),
            excluded_shift_ids=(
                excluded_ids
                if excluded_ids is not None
                else await crud_shared_list.excluded_ids(
                    session, shared_list_id=shared_list.id
                )
            ),
            ends_mode=ends_mode,
            ends_on=data["ends_on"],
            now_wall=now_wall,
        )

    for name, value in data.items():
        setattr(shared_list, name, value)
    session.add(shared_list)
    await session.flush()
    if task_ids is not None:
        await crud_shared_list.set_tasks(
            session, shared_list_id=shared_list.id, task_ids=task_ids
        )
    if excluded_ids is not None:
        await crud_shared_list.set_excluded(
            session, shared_list_id=shared_list.id, shift_ids=excluded_ids
        )


async def _lock_lists(
    session: AsyncSession, event_id: uuid.UUID, *conditions: ColumnElement[bool]
) -> list[SharedList]:
    """The event's lists matching ``conditions``, locked ``FOR UPDATE`` in id
    order, so two batches over the same lists cannot deadlock."""
    result = await session.execute(
        select(SharedList)
        .where(col(SharedList.event_id) == event_id, *conditions)
        .order_by(col(SharedList.id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def bulk(
    session: AsyncSession,
    *,
    event: Event,
    scope: SharedListScope,
    action: BulkAction,
    list_ids: Collection[uuid.UUID],
    now_utc: dt.datetime,
    now_wall: dt.datetime,
) -> SharedListBulkResult:
    """Pause, resume or end several lists of the event, each as if alone.

    Every list is judged by the rule of ``require_shared_list_manager``
    (``shared_list_change_refusal``, with the caller's ``scope``) and by
    :func:`change_status`; a refusal is reported in ``skipped`` with the code
    the single action would have answered, and never fails the batch. An id
    that is not a list of this event is skipped as ``shared_list.not_found``.
    A fixed number of queries, however many lists.

    The caller holds the event ``FOR SHARE``, taken before ``scope``, as
    :func:`lock_for_change` takes it for one list.
    """
    locked = await _lock_lists(session, event.id, col(SharedList.id).in_(list_ids))
    found = {shared_list.id: shared_list for shared_list in locked}
    states = {
        state.shared_list.id: state
        for state in overview.evaluate(
            await overview.load(session, event, now_wall=now_wall)
        )
    }
    changed: list[uuid.UUID] = []
    skipped: list[SharedListBulkSkip] = []
    for list_id in sorted(set(list_ids)):
        shared_list, state = found.get(list_id), states.get(list_id)
        if shared_list is None or state is None:
            skipped.append(SharedListBulkSkip(id=list_id, code="shared_list.not_found"))
            continue
        refusal = shared_list_change_refusal(
            scope.access_to(task.task_id for task in state.current),
            action,
            managers_share_lists=scope.managers_share_lists,
        )
        if refusal is not None:
            skipped.append(SharedListBulkSkip(id=list_id, code=refusal))
            continue
        outcome = change_status(
            shared_list,
            action,
            event=event,
            last_start=state.last_start,
            effective=state.effective,
            now_utc=now_utc,
            now_wall=now_wall,
        )
        if isinstance(outcome, Refusal):
            skipped.append(SharedListBulkSkip(id=list_id, code=outcome.code))
        elif outcome:
            session.add(shared_list)
            changed.append(list_id)
    await session.flush()
    return SharedListBulkResult(changed=changed, skipped=skipped)


async def pause_all(
    session: AsyncSession,
    *,
    event: Event,
    now_utc: dt.datetime,
    lock_managers: bool,
) -> SharedListBulkResult:
    """The event admins' emergency stop: pause every list of the event that is
    not paused or ended yet.

    Expired lists are paused too, unlike with a single pause: a shift added
    later or the event published again would otherwise reopen them.
    ``lock_managers`` also switches ``managers_share_lists`` off, so people in
    charge cannot resume their own lists afterwards.

    The event is locked first, as every change to a list locks it
    (:func:`lock_for_change`): a change in flight finishes before the lists
    are read, so none stays open behind the stop, and one after it sees the
    switch.
    """
    await crud_event.lock(session, event.id, mode="no_key_update")
    paused = await _lock_lists(session, event.id, col(SharedList.status) == "live")
    for shared_list in paused:
        shared_list.status = "paused"
        shared_list.paused_at = now_utc
        session.add(shared_list)
    if lock_managers:
        event.managers_share_lists = False
        session.add(event)
    await session.flush()
    return SharedListBulkResult(
        changed=[shared_list.id for shared_list in paused], skipped=[]
    )
