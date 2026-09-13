import datetime as dt
import uuid
from typing import Any, TypeVar

from fastapi import APIRouter, BackgroundTasks, Query
from pydantic import BaseModel, ValidationError
from sqlalchemy import func as sa_func
from sqlalchemy import select as sa_select
from sqlalchemy import update as sa_update
from sqlmodel import col

from app.api.deps import CurrentSuperuser, CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.event import EventScope
from app.crud.event import event as crud_event
from app.crud.event_invitation import event_invitation as crud_invitation
from app.crud.event_invitation import invitation_invalid_reason
from app.crud.event_join_request import event_join_request as crud_join_request
from app.crud.event_membership import event_membership as crud_membership
from app.crud.user import user as crud_user
from app.crud.user_availability import user_availability as crud_availability
from app.logic.permissions import require_event_role, require_event_visible
from app.logic.shift_generator import generate_shifts
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User as UserModel
from app.models.user_availability import UserAvailabilityDate
from app.schemas.event import (
    EventCreate,
    EventListResponse,
    EventRead,
    EventStatus,
    EventUpdate,
    EventVisibility,
)
from app.schemas.event_clone import (
    EventCloneRequest,
    EventCloneResponse,
    EventCloneTask,
)
from app.schemas.event_invitation import (
    EventInvitationBulkCreate,
    EventInvitationBulkResult,
    EventInvitationCreate,
    EventInvitationRead,
)
from app.schemas.event_join_request import (
    EventJoinRequestCreate,
    EventJoinRequestDecision,
    EventJoinRequestRead,
)
from app.schemas.event_membership import (
    EventMemberRead,
    EventMemberRoleUpdate,
    EventOwnershipTransfer,
    EventRole,
)
from app.schemas.task import ScheduleOverride
from app.schemas.user_availability import (
    UserAvailabilityCreate,
    UserAvailabilityRead,
    UserAvailabilityWithUser,
)

router = APIRouter(prefix="/events", tags=["events"])


# --- Read helpers -------------------------------------------------------


async def decorate_events(
    session: DBDep,
    user: UserModel,
    events: list[Event],
) -> list[EventRead]:
    """Attach viewer-relative context to a page of events.

    Member counts, the caller's own role and any pending join request are all
    fetched in one query each rather than per row, so a long Discover list
    costs a constant number of round trips.
    """
    event_ids = [e.id for e in events]
    if not event_ids:
        return []

    member_counts = await crud_membership.count_by_event(session, event_ids=event_ids)
    my_roles = await crud_membership.get_roles_for_user(session, user_id=user.id)
    request_statuses = await crud_join_request.statuses_for_user(
        session, user_id=user.id, event_ids=event_ids
    )

    # Only events the caller can manage need a pending-request badge.
    manageable = [
        e.id
        for e in events
        if user.is_admin or my_roles.get(e.id) in ("owner", "admin")
    ]
    pending_counts = await crud_join_request.count_pending_by_event(
        session, event_ids=manageable
    )

    out: list[EventRead] = []
    for e in events:
        read = EventRead.model_validate(e)
        read.my_role = "owner" if user.is_admin else my_roles.get(e.id)
        read.member_count = member_counts.get(e.id, 0)
        read.join_request_status = request_statuses.get(e.id)
        read.pending_request_count = pending_counts.get(e.id, 0)
        out.append(read)
    return out


async def decorate_event(
    session: DBDep,
    user: UserModel,
    event: Event,
) -> EventRead:
    decorated = await decorate_events(session, user, [event])
    return decorated[0]


# --- Event CRUD ---------------------------------------------------------


@router.get("/", response_model=EventListResponse)
async def list_events(
    session: DBDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    scope: EventScope = Query(
        default="mine",
        description=(
            "mine — events you belong to; discover — public events you could "
            "join; featured — the curated home selection; all — superadmin only"
        ),
    ),
    search: str | None = None,
    status: EventStatus | None = None,
    visibility: EventVisibility | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    is_expired: bool | None = None,
) -> EventListResponse:
    """List events in one of four scopes.

    Visibility is enforced in the query itself: a private event can only ever
    come back under ``mine`` (or ``all`` for the platform superadmin).
    """
    effective_scope: EventScope = scope
    if scope == "all" and not current_user.is_admin:
        effective_scope = "mine"

    member_event_ids = await crud_membership.list_event_ids_for_user(
        session, user_id=current_user.id
    )

    filter_kwargs: dict[str, Any] = {
        "scope": effective_scope,
        "member_event_ids": member_event_ids,
        "search": search,
        "status": status,
        "visibility": visibility,
        "date_from": date_from,
        "date_to": date_to,
        "is_expired": is_expired,
    }

    items = await crud_event.get_multi_filtered(
        session, skip=skip, limit=limit, **filter_kwargs
    )
    total = await crud_event.get_count_filtered(session, **filter_kwargs)
    return EventListResponse(
        items=await decorate_events(session, current_user, items),
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{event_id}", response_model=EventRead)
async def get_event(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> EventRead:
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_visible(current_user, session, db_event)
    return await decorate_event(session, current_user, db_event)


@router.post("/", response_model=EventRead, status_code=201)
async def create_event(
    event_in: EventCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> EventRead:
    """Create an event. Any signed-in user may; the creator becomes its owner."""
    event_in.created_by_id = current_user.id
    db_event = await crud_event.create(session, obj_in=event_in)
    await crud_membership.upsert(
        session, user_id=current_user.id, event_id=db_event.id, role="owner"
    )
    return await decorate_event(session, current_user, db_event)


@router.patch("/{event_id}", response_model=EventRead)
async def update_event(
    event_id: uuid.UUID,
    event_in: EventUpdate,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EventRead:
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, db_event.id, minimum="admin")

    # Validate date range against existing tasks
    new_start = event_in.start_date or db_event.start_date
    new_end = event_in.end_date or db_event.end_date
    if new_end < new_start:
        raise_problem(
            422,
            code="event.invalid_dates",
            detail="End date must be on or after start date",
        )

    # Validate default time window after merging with the DB record (PATCH may
    # carry only one of the two fields, but the resulting pair must satisfy
    # end > start).
    update_fields = event_in.model_fields_set
    new_start_time = (
        event_in.default_start_time
        if "default_start_time" in update_fields
        else db_event.default_start_time
    )
    new_end_time = (
        event_in.default_end_time
        if "default_end_time" in update_fields
        else db_event.default_end_time
    )
    if (
        new_start_time is not None
        and new_end_time is not None
        and new_end_time <= new_start_time
    ):
        raise_problem(
            422,
            code="event.invalid_default_times",
            detail=(
                "Default end time must be after default start time. "
                "Overnight windows are not yet supported — leave both empty for "
                "events that span midnight."
            ),
        )
    if event_in.start_date is not None or event_in.end_date is not None:
        result = await session.execute(
            sa_select(
                sa_func.min(col(Task.start_date)),
                sa_func.max(col(Task.end_date)),
            ).where(col(Task.event_id) == event_id)
        )
        row = result.one()
        earliest_task, latest_task = row[0], row[1]
        if earliest_task is not None and new_start > earliest_task:
            raise_problem(
                422,
                code="event.date_range_conflict",
                detail=f"Cannot set start date after {earliest_task.isoformat()} — a task starts on that date",
            )
        if latest_task is not None and new_end < latest_task:
            raise_problem(
                422,
                code="event.date_range_conflict",
                detail=f"Cannot set end date before {latest_task.isoformat()} — a task ends on that date",
            )

    old_status = db_event.status
    updated = await crud_event.update(session, db_obj=db_event, obj_in=event_in)

    # An event pulled back out of public listings should not keep its featured
    # slot on the home screen.
    if updated.visibility == "private" and updated.is_featured:
        updated.is_featured = False
        session.add(updated)
        await session.flush()

    # Notify when event is published
    if old_status != "published" and updated.status == "published":
        from app.logic.notifications.triggers import dispatch_event_published

        background_tasks.add_task(
            dispatch_event_published,
            event_id=updated.id,
            event_name=updated.name,
        )

    return await decorate_event(session, current_user, updated)


async def _refuse_if_sandbox(
    session: DBDep,
    event_id: uuid.UUID,
    *,
    code: str = "sandbox.invitations_disabled",
    detail: str = "Invitations cannot be sent from a demo event",
) -> None:
    """Block anything a demo event must not do.

    A guest is seeded as ``owner`` of their sandbox so the manager tour can
    show them the screens an organiser uses. That role passes
    ``require_event_role(minimum="admin")``, which means the invitation
    endpoints would happily post an email to any address an anonymous visitor
    typed in. The existing ``demo|`` guard does not help here: it tests the
    *recipient*, and the recipient of an invitation is whoever was named.

    The tour visits these screens deliberately and explains that sending is
    switched off in the demo, so this is the enforcement behind that sentence.

    ``code``/``detail`` default to the invitation wording every existing caller
    wants; cloning passes its own so a refused clone does not talk about
    invitations.
    """
    event = await crud_event.get(session, event_id, raise_404_error=True)
    if event.is_sandbox:
        raise_problem(403, code=code, detail=detail)


class FeaturedUpdate(BaseModel):
    is_featured: bool


@router.patch("/{event_id}/featured", response_model=EventRead)
async def set_event_featured(
    event_id: uuid.UUID,
    body: FeaturedUpdate,
    session: DBDep,
    current_user: CurrentSuperuser,
) -> EventRead:
    """Platform superadmin: curate which events surface on the home screen.

    Featuring is the one thing event owners cannot do for themselves — it is
    the whole of the superadmin's remaining editorial role.
    """
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    if body.is_featured and db_event.is_sandbox:
        raise_problem(
            422,
            code="event.sandbox_not_featurable",
            detail="Demo events cannot be featured",
        )
    if body.is_featured and db_event.visibility != "public":
        raise_problem(
            422,
            code="event.feature_requires_public",
            detail="Only public events can be featured on the home screen",
        )
    db_event.is_featured = body.is_featured
    session.add(db_event)
    await session.flush()
    await session.refresh(db_event)
    return await decorate_event(session, current_user, db_event)


@router.get("/{event_id}/task-date-bounds")
async def get_task_date_bounds(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> dict[str, dt.date | None]:
    """Return the earliest task start and latest task end within this event."""
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_visible(current_user, session, db_event)
    result = await session.execute(
        sa_select(
            sa_func.min(col(Task.start_date)),
            sa_func.max(col(Task.end_date)),
        ).where(col(Task.event_id) == event_id)
    )
    row = result.one()
    return {"earliest_start": row[0], "latest_end": row[1]}


class ShiftDatesRequest(BaseModel):
    new_start_date: dt.date


@router.post("/{event_id}/shift-dates", response_model=EventRead)
async def shift_event_dates(
    event_id: uuid.UUID,
    body: ShiftDatesRequest,
    session: DBDep,
    current_user: CurrentUser,
) -> EventRead:
    """Shift the entire event and all its tasks/shifts/availabilities by a date offset.

    The offset is calculated from the difference between the current event
    start_date and the provided new_start_date.
    """
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, db_event.id, minimum="admin")

    delta = body.new_start_date - db_event.start_date
    if delta.days == 0:
        return await decorate_event(session, current_user, db_event)

    # 1. Shift the event itself
    db_event.start_date = db_event.start_date + delta
    db_event.end_date = db_event.end_date + delta
    session.add(db_event)

    # Get task IDs in this event
    task_ids_result = await session.execute(
        sa_select(col(Task.id)).where(col(Task.event_id) == event_id)
    )
    task_ids = list(task_ids_result.scalars().all())

    if task_ids:
        # 2. Shift tasks
        await session.execute(
            sa_update(Task)
            .where(col(Task.event_id) == event_id)
            .values(
                start_date=Task.start_date + delta,
                end_date=Task.end_date + delta,
            )
        )

        # 3. Shift shift_batches
        await session.execute(
            sa_update(ShiftBatch)
            .where(col(ShiftBatch.task_id).in_(task_ids))
            .values(
                start_date=ShiftBatch.start_date + delta,
                end_date=ShiftBatch.end_date + delta,
            )
        )

        # 4. Shift shifts
        await session.execute(
            sa_update(Shift)
            .where(col(Shift.task_id).in_(task_ids))
            .values(date=Shift.date + delta)
        )

        # 5. Shift schedule_overrides in tasks and shift_batches (JSON with date keys)
        if delta.days != 0:
            tasks_with_overrides = (
                (
                    await session.execute(
                        sa_select(Task).where(
                            col(Task.id).in_(task_ids),
                            col(Task.schedule_overrides).isnot(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for ev in tasks_with_overrides:
                ev.schedule_overrides = _shift_overrides(ev.schedule_overrides, delta)
                session.add(ev)

            batches_with_overrides = (
                (
                    await session.execute(
                        sa_select(ShiftBatch).where(
                            col(ShiftBatch.task_id).in_(task_ids),
                            col(ShiftBatch.schedule_overrides).isnot(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for batch in batches_with_overrides:
                batch.schedule_overrides = _shift_overrides(
                    batch.schedule_overrides, delta
                )
                session.add(batch)

    # 6. Shift user availability dates for this event
    from app.models.user_availability import UserAvailability

    avail_ids_result = await session.execute(
        sa_select(col(UserAvailability.id)).where(
            col(UserAvailability.event_id) == event_id
        )
    )
    avail_ids = list(avail_ids_result.scalars().all())
    if avail_ids:
        await session.execute(
            sa_update(UserAvailabilityDate)
            .where(col(UserAvailabilityDate.availability_id).in_(avail_ids))
            .values(slot_date=UserAvailabilityDate.slot_date + delta)
        )

    await session.flush()
    await session.refresh(db_event)
    return await decorate_event(session, current_user, db_event)


def _shift_overrides(
    overrides: list[dict[str, object]] | None,
    delta: dt.timedelta,
) -> list[dict[str, object]]:
    """Shift the 'date' key in each schedule override entry."""
    if not overrides:
        return overrides or []
    shifted: list[dict[str, object]] = []
    for entry in overrides:
        new_entry = dict(entry)
        if "date" in new_entry and isinstance(new_entry["date"], str):
            try:
                d = dt.date.fromisoformat(new_entry["date"])
                new_entry["date"] = (d + delta).isoformat()
            except ValueError:
                pass
        shifted.append(new_entry)
    return shifted


# --- Clone -------------------------------------------------------------


def _resolve_overrides(raw: list[dict[str, Any]] | None) -> list[ScheduleOverride]:
    """Re-parse stored override JSON into the models ``generate_shifts`` takes.

    The column is a plain JSON blob, so it can hold anything an older writer
    put there. Entries that no longer parse are dropped rather than failing the
    whole clone — they would not have produced a shift anyway.
    """
    parsed: list[ScheduleOverride] = []
    for entry in raw or []:
        try:
            parsed.append(ScheduleOverride.model_validate(entry))
        except ValidationError:
            continue
    return parsed


_Pickable = TypeVar("_Pickable")


def _pick(override: _Pickable | None, fallback: _Pickable | None) -> _Pickable | None:
    """A caller's per-task override, or the source value when it was omitted."""
    return fallback if override is None else override


def _clone_batch(
    src: ShiftBatch,
    *,
    task_id: uuid.UUID,
    delta: dt.timedelta,
    entry: EventCloneTask,
) -> ShiftBatch:
    """A copy of ``src`` on another task, moved by ``delta``.

    Batches are mandatory on a clone, not an optimisation: ``remainder_mode``
    is persisted nowhere else, the task edit screen reads batch config in
    preference to the task's own, and the per-batch delete/regenerate flows
    have nothing to act on without one.

    The caller's per-task generation overrides are applied *here* as well as on
    the task row. Every batch written by the normal creation paths fills in all
    six of these columns, and both the generator and the edit screen read the
    batch before the task — so a batch left holding the source values would
    make the override a no-op and leave the two rows disagreeing.
    """
    return ShiftBatch(
        task_id=task_id,
        label=src.label,
        start_date=src.start_date + delta,
        end_date=src.end_date + delta,
        location=_pick(entry.location, src.location),
        category=_pick(entry.category, src.category),
        default_start_time=_pick(entry.default_start_time, src.default_start_time),
        default_end_time=_pick(entry.default_end_time, src.default_end_time),
        shift_duration_minutes=_pick(
            entry.shift_duration_minutes, src.shift_duration_minutes
        ),
        people_per_shift=_pick(entry.people_per_shift, src.people_per_shift),
        remainder_mode=src.remainder_mode,
        schedule_overrides=(
            _shift_overrides(src.schedule_overrides, delta)
            if src.schedule_overrides
            else None
        ),
    )


def _regenerate_batch_shifts(batch: ShiftBatch, task: Task) -> list[Shift]:
    """Re-run the generator for one cloned batch.

    Config resolution is batch column first, then the cloned task's own field.
    Both rows already carry the caller's per-task overrides (``_clone_batch``
    applies them too), so the two agree whichever one wins here. A batch
    missing the three values generation needs (both default times and a
    duration) yields nothing; there is no sensible guess to make.
    """
    start_time = batch.default_start_time or task.default_start_time
    end_time = batch.default_end_time or task.default_end_time
    duration = batch.shift_duration_minutes or task.shift_duration_minutes
    if start_time is None or end_time is None or not duration:
        return []

    generated = generate_shifts(
        task_id=task.id,
        task_name=task.name,
        start_date=batch.start_date,
        end_date=batch.end_date,
        default_start_time=start_time,
        default_end_time=end_time,
        shift_duration_minutes=duration,
        people_per_shift=batch.people_per_shift or task.people_per_shift or 1,
        remainder_mode=batch.remainder_mode or "drop",
        location=batch.location or task.location,
        category=batch.category or task.category,
        overrides=_resolve_overrides(batch.schedule_overrides),
    )
    out: list[Shift] = []
    for slot_in in generated:
        slot_in.batch_id = batch.id
        out.append(Shift(**slot_in.model_dump()))
    return out


def _assert_rows_fit_event(
    *,
    new_event: Event,
    task_label: str,
    batches: list[ShiftBatch],
    shifts: list[Shift],
) -> None:
    """Refuse a task whose cloned batches or shifts fall outside the clone.

    Validating the Task row is not enough. ``add_shifts_to_task`` validates
    shift dates against the *event* range, never the task's, so a source task
    may legitimately own batches and shifts outside its own start/end — and a
    clone that shortens the window (an explicit ``end_date``, or a per-task
    date override that moves the task by a different offset than its rows) can
    land those outside the new event entirely. The same 422 as the task check:
    from the caller's side it is one and the same conflict.
    """
    lo, hi = new_event.start_date, new_event.end_date
    window = f"{lo.isoformat()}–{hi.isoformat()}"

    for batch in batches:
        if batch.start_date < lo or batch.end_date > hi:
            raise_problem(
                422,
                code="event.date_range_conflict",
                detail=(
                    f'Shift block "{batch.label or task_label}" would run '
                    f"{batch.start_date.isoformat()}–{batch.end_date.isoformat()}, "
                    f"outside the new event's {window}"
                ),
            )

    for shift in shifts:
        if shift.date < lo or shift.date > hi:
            raise_problem(
                422,
                code="event.date_range_conflict",
                detail=(
                    f'Task "{task_label}" would put a shift on '
                    f"{shift.date.isoformat()}, outside the new event's {window}"
                ),
            )


@router.post("/{event_id}/clone", response_model=EventCloneResponse, status_code=201)
async def clone_event(
    event_id: uuid.UUID,
    body: EventCloneRequest,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EventCloneResponse:
    """Create a new event from an existing one: "run this again next year".

    Everything is moved by a single offset, ``new start - source start``, so the
    tasks, their batches, their shifts and the per-date overrides all stay in
    step with each other. Bookings are never copied — a cloned shift starts
    empty — and neither are ``is_featured``, ``is_sandbox`` or
    ``sandbox_expires_at``, all of which mean something about the *source*.

    The clone always starts as a draft: publishing is a separate, deliberate
    act, and it is what fans a notification out to the roster.
    """
    source = await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, source.id, minimum="admin")
    # A demo is seeded with its guest as owner, so the role check above passes
    # for an anonymous visitor. A sandbox must never produce a real event.
    await _refuse_if_sandbox(
        session,
        source.id,
        code="sandbox.clone_disabled",
        detail="A demo event cannot be cloned into a real one",
    )

    # Naming the same task twice would clone it twice — every batch and every
    # shift row again, in one transaction — for no describable gain.
    seen: set[uuid.UUID] = set()
    for entry in body.tasks:
        if entry.source_task_id in seen:
            raise_problem(
                422,
                code="event.duplicate_task",
                detail="Each task can only be cloned once",
            )
        seen.add(entry.source_task_id)

    new_end = body.end_date or body.start_date + (source.end_date - source.start_date)
    if new_end < body.start_date:
        raise_problem(
            422,
            code="event.invalid_dates",
            detail="End date must be on or after start date",
        )

    copy_description = "description" not in body.model_fields_set
    event_in = EventCreate(
        name=body.name,
        description=source.description if copy_description else body.description,
        start_date=body.start_date,
        end_date=new_end,
        default_start_time=source.default_start_time if body.copy_defaults else None,
        default_end_time=source.default_end_time if body.copy_defaults else None,
        status="draft",
        visibility=body.visibility,
        created_by_id=current_user.id,
    )
    new_event = await crud_event.create(session, obj_in=event_in)
    # Not inherited, spelled out: each of these is a statement about the source
    # that would be a privilege escalation or a scheduled deletion on the clone.
    new_event.is_featured = False
    new_event.is_sandbox = False
    new_event.sandbox_expires_at = None
    session.add(new_event)

    # The owner grant is the membership row, not created_by_id — and it has to
    # land before the roster copy, which skips whoever is already here.
    await crud_membership.upsert(
        session, user_id=current_user.id, event_id=new_event.id, role="owner"
    )

    delta = new_event.start_date - source.start_date

    members_copied = 0
    if body.copy_members:
        # Built in memory and added in one go: the event is brand new, so
        # ``upsert``'s SELECT can never hit and its per-row flush/refresh would
        # be a round trip per member for nothing. The flush below covers them.
        copied_rows: list[EventMembership] = []
        for membership, member in await crud_membership.list_members(
            session, event_id=source.id
        ):
            if member.id == current_user.id:
                continue
            # A suspended account cannot use the event it would be added to —
            # every endpoint behind ``CurrentUser`` rejects it — so carrying it
            # over only produces a roster entry that is a dead end, and an
            # announcement email to someone who cannot act on it.
            if not member.is_active:
                continue
            # One owner per event: the source's owner becomes an admin here.
            role: EventRole = "admin" if membership.role != "member" else "member"
            copied_rows.append(
                EventMembership(user_id=member.id, event_id=new_event.id, role=role)
            )
            members_copied += 1
        session.add_all(copied_rows)

    new_shifts: list[Shift] = []
    tasks_created = 0
    for entry in body.tasks:
        task_shifts = await _clone_task(
            session,
            entry=entry,
            source_event_id=source.id,
            new_event=new_event,
            delta=delta,
            current_user_id=current_user.id,
        )
        tasks_created += 1
        new_shifts.extend(task_shifts)

    if new_shifts:
        session.add_all(new_shifts)
    await session.flush()
    await session.refresh(new_event)

    # The announcement tells *other people* the event exists, so the cloner is
    # never a recipient. Without ``copy_members`` the clone's only membership
    # is the cloner's own owner row, which leaves nobody to tell — and saying
    # ``notified: true`` there would have the UI report a mail that was never
    # sent. Not an error: the clone itself succeeded.
    notified = False
    if body.announce is not None and body.announce.send and members_copied > 0:
        from app.logic.notifications.triggers import dispatch_event_cloned

        background_tasks.add_task(
            dispatch_event_cloned,
            event_id=new_event.id,
            note=body.announce.note,
            exclude_user_id=current_user.id,
        )
        notified = True

    return EventCloneResponse(
        event=await decorate_event(session, current_user, new_event),
        tasks_created=tasks_created,
        shifts_created=len(new_shifts),
        members_copied=members_copied,
        notified=notified,
    )


async def _clone_task(
    session: DBDep,
    *,
    entry: EventCloneTask,
    source_event_id: uuid.UUID,
    new_event: Event,
    delta: dt.timedelta,
    current_user_id: uuid.UUID,
) -> list[Shift]:
    """Reproduce one source task, its batches and its shifts in ``new_event``.

    ``delta`` is the event-level offset, which is only the *default*: a caller
    who re-dates this task gets a task-level offset derived from where the task
    actually lands, and everything under the task moves by that instead. Moving
    the Task row alone would leave its batches and shifts sitting in the
    source's window — a task pointing at shifts it does not contain.

    The task and its batches are added to the session here; the shift rows are
    returned so the caller can insert every task's shifts in one ``add_all``
    rather than a flush per row.
    """
    # Scoped to the source event on purpose: without this filter the request
    # body could name any task id on the installation and have it copied into
    # an event the caller owns. This is the one authorisation hole a clone
    # endpoint invites.
    result = await session.execute(
        sa_select(Task).where(
            col(Task.id) == entry.source_task_id,
            col(Task.event_id) == source_event_id,
        )
    )
    src = result.scalars().first()
    if src is None:
        raise_problem(
            404,
            code="task.not_found",
            detail="No such task in this event",
        )

    start_date = entry.start_date or src.start_date + delta
    end_date = entry.end_date or src.end_date + delta
    if end_date < start_date:
        raise_problem(
            422,
            code="event.invalid_dates",
            detail=f'Task "{entry.name or src.name}" would end before it starts',
        )
    if start_date < new_event.start_date or end_date > new_event.end_date:
        raise_problem(
            422,
            code="event.date_range_conflict",
            detail=(
                f'Task "{entry.name or src.name}" would run '
                f"{start_date.isoformat()}–{end_date.isoformat()}, outside the new "
                f"event's {new_event.start_date.isoformat()}–"
                f"{new_event.end_date.isoformat()}"
            ),
        )

    # Everything below the task follows the task, not the event: with no
    # override the two offsets are identical, and with one this is the only
    # reading that keeps a re-dated task's batches and shifts inside it.
    task_delta = start_date - src.start_date

    new_task = Task(
        name=entry.name or src.name,
        description=src.description,
        start_date=start_date,
        end_date=end_date,
        status=entry.status or src.status,
        location=_pick(entry.location, src.location),
        category=_pick(entry.category, src.category),
        shift_duration_minutes=_pick(
            entry.shift_duration_minutes, src.shift_duration_minutes
        ),
        default_start_time=_pick(entry.default_start_time, src.default_start_time),
        default_end_time=_pick(entry.default_end_time, src.default_end_time),
        people_per_shift=_pick(entry.people_per_shift, src.people_per_shift),
        # Reassigned, never mutated in place: the JSON column is not
        # mutation-tracked, so an in-place edit would simply not be persisted.
        schedule_overrides=(
            _shift_overrides(src.schedule_overrides, task_delta)
            if src.schedule_overrides
            else None
        ),
        event_id=new_event.id,
        created_by_id=current_user_id,
        is_sandbox=new_event.is_sandbox,
    )
    session.add(new_task)

    batch_result = await session.execute(
        sa_select(ShiftBatch)
        .where(col(ShiftBatch.task_id) == src.id)
        .order_by(col(ShiftBatch.created_at))
    )
    source_batches = list(batch_result.scalars().all())

    # ``id`` is a client-side uuid4 default, so children can be wired to their
    # parents before anything is flushed.
    batch_map: dict[uuid.UUID, uuid.UUID] = {}
    new_batches: list[ShiftBatch] = []
    for src_batch in source_batches:
        new_batch = _clone_batch(
            src_batch, task_id=new_task.id, delta=task_delta, entry=entry
        )
        session.add(new_batch)
        batch_map[src_batch.id] = new_batch.id
        new_batches.append(new_batch)

    if entry.mode == "regenerate":
        if not new_batches:
            # A task generated before batches existed, or seeded by hand. Give
            # the clone the batch row every other generation path produces, so
            # the regenerate screen has something to read.
            synthetic = ShiftBatch(
                task_id=new_task.id,
                label=new_task.name,
                start_date=new_task.start_date,
                end_date=new_task.end_date,
                location=new_task.location,
                category=new_task.category,
                default_start_time=new_task.default_start_time,
                default_end_time=new_task.default_end_time,
                shift_duration_minutes=new_task.shift_duration_minutes,
                people_per_shift=new_task.people_per_shift,
                remainder_mode="drop",
                schedule_overrides=new_task.schedule_overrides,
            )
            session.add(synthetic)
            new_batches.append(synthetic)
        shifts: list[Shift] = []
        for new_batch in new_batches:
            shifts.extend(_regenerate_batch_shifts(new_batch, new_task))
        _assert_rows_fit_event(
            new_event=new_event,
            task_label=new_task.name,
            batches=new_batches,
            shifts=shifts,
        )
        return shifts

    shift_result = await session.execute(
        sa_select(Shift)
        .where(col(Shift.task_id) == src.id)
        .order_by(col(Shift.date), col(Shift.start_time))
    )
    # New rows every time. Appending the source objects to the new task's
    # collections would MOVE them off the source — both relationships are
    # delete-orphan. Bookings are deliberately left behind.
    copied = [
        Shift(
            task_id=new_task.id,
            batch_id=batch_map.get(s.batch_id) if s.batch_id else None,
            title=s.title,
            description=s.description,
            date=s.date + task_delta,
            start_time=s.start_time,
            end_time=s.end_time,
            location=s.location,
            category=s.category,
            max_bookings=s.max_bookings,
        )
        for s in shift_result.scalars().all()
    ]
    _assert_rows_fit_event(
        new_event=new_event,
        task_label=new_task.name,
        batches=new_batches,
        shifts=copied,
    )
    return copied


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Delete an event. Owner (or platform superadmin) only.

    Deliberately stricter than editing: an admin brought in to help run an
    event should not be able to destroy it.
    """
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, db_event.id, minimum="owner")
    await session.delete(db_event)
    await session.commit()


# --- Availability endpoints ---


@router.get("/{event_id}/availabilities", response_model=list[UserAvailabilityWithUser])
async def list_event_availabilities(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[UserAvailabilityWithUser]:
    """List all user availabilities for this event (event admins only)."""
    await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, event_id, minimum="admin")
    availabilities = await crud_availability.get_multi_by_group(
        session, event_id=event_id, skip=skip, limit=limit
    )

    user_ids = [a.user_id for a in availabilities]
    users_map: dict[uuid.UUID, UserModel] = {}
    if user_ids:
        result = await session.execute(
            sa_select(UserModel).where(UserModel.id.in_(user_ids))  # type: ignore[attr-defined]
        )
        users_map = {u.id: u for u in result.scalars().all()}

    return [
        UserAvailabilityWithUser(
            **UserAvailabilityRead.model_validate(avail).model_dump(),
            user_full_name=(
                users_map[avail.user_id].name if avail.user_id in users_map else None
            ),
            user_email=(
                users_map[avail.user_id].email if avail.user_id in users_map else None
            ),
        )
        for avail in availabilities
    ]


@router.get("/{event_id}/availability/me", response_model=UserAvailabilityRead)
async def get_my_availability(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> UserAvailabilityRead:
    avail = await crud_availability.get_by_user_and_group(
        session,
        user_id=current_user.id,
        event_id=event_id,
    )
    if not avail:
        raise_problem(
            404,
            code="availability.not_found",
            detail="No availability registered",
        )
    return UserAvailabilityRead.model_validate(avail)


@router.post(
    "/{event_id}/availability",
    response_model=UserAvailabilityRead,
    status_code=201,
)
async def set_my_availability(
    event_id: uuid.UUID,
    avail_in: UserAvailabilityCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> UserAvailabilityRead:
    await crud_event.get(session, event_id, raise_404_error=True)
    # Offering availability is a member action — you must be in the event.
    await require_event_role(current_user, session, event_id, minimum="member")
    await crud_availability.upsert_for_user(
        session,
        user_id=current_user.id,
        event_id=event_id,
        obj_in=avail_in,
    )
    await session.flush()
    # Re-fetch after flush to get eagerly-loaded available_dates
    avail = await crud_availability.get_by_user_and_group(
        session,
        user_id=current_user.id,
        event_id=event_id,
    )
    return UserAvailabilityRead.model_validate(avail)


@router.delete("/{event_id}/availability/me", status_code=204)
async def delete_my_availability(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    deleted = await crud_availability.delete_for_user(
        session,
        user_id=current_user.id,
        event_id=event_id,
    )
    if not deleted:
        raise_problem(
            404,
            code="availability.not_found",
            detail="No availability registered",
        )
    await session.commit()


# --- Membership ---------------------------------------------------------


@router.get("/{event_id}/members", response_model=list[EventMemberRead])
async def list_event_members(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> list[EventMemberRead]:
    """The event roster. Visible to anyone in the event."""
    await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, event_id, minimum="member")
    rows = await crud_membership.list_members(session, event_id=event_id)
    return [
        EventMemberRead(
            user_id=membership.user_id,
            event_id=membership.event_id,
            role=membership.role,  # type: ignore[arg-type]
            joined_at=membership.created_at,
            name=user.name,
            email=user.email,
            avatar_etag=user.avatar_etag,
        )
        for membership, user in rows
    ]


@router.patch(
    "/{event_id}/members/{user_id}",
    response_model=EventMemberRead,
)
async def update_member_role(
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    body: EventMemberRoleUpdate,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EventMemberRead:
    """Promote or demote a member. Event admins and the owner may do this."""
    await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, event_id, minimum="admin")

    membership = await crud_membership.get(session, user_id=user_id, event_id=event_id)
    if not membership:
        raise_problem(
            404,
            code="event.member_not_found",
            detail="That user is not a member of this event",
        )
    if membership.role == "owner":
        raise_problem(
            422,
            code="event.cannot_demote_owner",
            detail=(
                "The owner's role cannot be changed directly. "
                "Transfer ownership instead."
            ),
        )

    updated = await crud_membership.upsert(
        session, user_id=user_id, event_id=event_id, role=body.role
    )
    user = await crud_user.get(session, id=user_id, raise_404_error=True)

    from app.logic.notifications.triggers import dispatch_event_role_changed

    background_tasks.add_task(
        dispatch_event_role_changed,
        event_id=event_id,
        user_id=user_id,
        role=body.role,
    )

    return EventMemberRead(
        user_id=updated.user_id,
        event_id=updated.event_id,
        role=updated.role,  # type: ignore[arg-type]
        joined_at=updated.created_at,
        name=user.name,
        email=user.email,
        avatar_etag=user.avatar_etag,
    )


@router.delete("/{event_id}/members/{user_id}", status_code=204)
async def remove_member(
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Remove someone from an event, or leave it yourself.

    Anyone may remove themselves; removing *others* needs admin. The owner
    cannot be removed at all — ownership has to be transferred first, so an
    event is never left without someone in charge.
    """
    await crud_event.get(session, event_id, raise_404_error=True)
    is_self = user_id == current_user.id
    if not is_self:
        await require_event_role(current_user, session, event_id, minimum="admin")

    membership = await crud_membership.get(session, user_id=user_id, event_id=event_id)
    if not membership:
        raise_problem(
            404,
            code="event.member_not_found",
            detail="That user is not a member of this event",
        )
    if membership.role == "owner":
        raise_problem(
            422,
            code="event.cannot_remove_owner",
            detail=("The event owner cannot be removed. Transfer ownership first."),
        )

    await crud_membership.remove(session, user_id=user_id, event_id=event_id)

    # Clear the selection so the removed user is not stranded on an event
    # they can no longer open.
    removed_user = await crud_user.get(session, id=user_id)
    if removed_user and removed_user.selected_event_id == event_id:
        removed_user.selected_event_id = None
        session.add(removed_user)
        await session.flush()


@router.post("/{event_id}/transfer-ownership", response_model=list[EventMemberRead])
async def transfer_event_ownership(
    event_id: uuid.UUID,
    body: EventOwnershipTransfer,
    session: DBDep,
    current_user: CurrentUser,
) -> list[EventMemberRead]:
    """Hand the event to another member. Owner only.

    The outgoing owner stays on as an admin rather than losing access.
    """
    await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, event_id, minimum="owner")

    target = await crud_membership.get(
        session, user_id=body.new_owner_id, event_id=event_id
    )
    if not target:
        raise_problem(
            422,
            code="event.new_owner_not_member",
            detail="The new owner must already be a member of this event",
        )
    if body.new_owner_id == current_user.id:
        raise_problem(
            422,
            code="event.already_owner",
            detail="That user already owns this event",
        )

    await crud_membership.upsert(
        session, user_id=body.new_owner_id, event_id=event_id, role="owner"
    )
    # The platform superadmin can transfer an event they do not personally
    # belong to; only demote a real membership row.
    if await crud_membership.get(session, user_id=current_user.id, event_id=event_id):
        await crud_membership.upsert(
            session, user_id=current_user.id, event_id=event_id, role="admin"
        )

    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    db_event.created_by_id = body.new_owner_id
    session.add(db_event)
    await session.flush()

    return await list_event_members(event_id, session, current_user)


# --- Invitations --------------------------------------------------------


@router.get("/{event_id}/invitations", response_model=list[EventInvitationRead])
async def list_event_invitations(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> list[EventInvitationRead]:
    await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, event_id, minimum="admin")
    invitations = await crud_invitation.list_open_for_event(session, event_id=event_id)
    return [EventInvitationRead.model_validate(i) for i in invitations]


@router.post(
    "/{event_id}/invitations",
    response_model=EventInvitationRead,
    status_code=201,
)
async def create_event_invitation(
    event_id: uuid.UUID,
    body: EventInvitationCreate,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EventInvitationRead:
    """Invite one person by email, or mint a shareable link (omit ``email``)."""
    await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, event_id, minimum="admin")
    await _refuse_if_sandbox(session, event_id)

    if body.email:
        existing_user = await crud_user.get_by_email(session, email=str(body.email))
        if existing_user:
            already = await crud_membership.get(
                session, user_id=existing_user.id, event_id=event_id
            )
            if already:
                raise_problem(
                    409,
                    code="event.already_member",
                    detail="That person is already a member of this event",
                )
        open_invite = await crud_invitation.find_pending_for_email(
            session, event_id=event_id, email=str(body.email)
        )
        if open_invite and invitation_invalid_reason(open_invite) is None:
            raise_problem(
                409,
                code="event.already_invited",
                detail="That address already has an open invitation",
            )

    invitation = await crud_invitation.create(
        session,
        event_id=event_id,
        email=str(body.email) if body.email else None,
        role=body.role,
        invited_by_id=current_user.id,
        expires_in_days=body.expires_in_days,
    )

    if invitation.email:
        from app.logic.notifications.triggers import dispatch_event_invitation

        background_tasks.add_task(
            dispatch_event_invitation,
            invitation_id=invitation.id,
        )

    return EventInvitationRead.model_validate(invitation)


@router.post(
    "/{event_id}/invitations/bulk",
    response_model=EventInvitationBulkResult,
    status_code=201,
)
async def create_event_invitations_bulk(
    event_id: uuid.UUID,
    body: EventInvitationBulkCreate,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EventInvitationBulkResult:
    """Invite a list of addresses at once.

    Addresses that are already members or already invited are reported back
    rather than failing the whole batch — pasting a team list twice should be
    harmless.
    """
    await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, event_id, minimum="admin")
    await _refuse_if_sandbox(session, event_id)

    created: list[EventInvitationRead] = []
    skipped_members: list[str] = []
    skipped_invited: list[str] = []

    for address in body.emails:
        email = str(address)
        existing_user = await crud_user.get_by_email(session, email=email)
        if existing_user and await crud_membership.get(
            session, user_id=existing_user.id, event_id=event_id
        ):
            skipped_members.append(email)
            continue
        open_invite = await crud_invitation.find_pending_for_email(
            session, event_id=event_id, email=email
        )
        if open_invite and invitation_invalid_reason(open_invite) is None:
            skipped_invited.append(email)
            continue

        invitation = await crud_invitation.create(
            session,
            event_id=event_id,
            email=email,
            role=body.role,
            invited_by_id=current_user.id,
            expires_in_days=body.expires_in_days,
        )
        created.append(EventInvitationRead.model_validate(invitation))

        from app.logic.notifications.triggers import dispatch_event_invitation

        background_tasks.add_task(
            dispatch_event_invitation, invitation_id=invitation.id
        )

    return EventInvitationBulkResult(
        created=created,
        skipped_existing_members=skipped_members,
        skipped_already_invited=skipped_invited,
    )


@router.delete("/{event_id}/invitations/{invitation_id}", status_code=204)
async def revoke_event_invitation(
    event_id: uuid.UUID,
    invitation_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, event_id, minimum="admin")
    invitation = await crud_invitation.get(session, invitation_id=invitation_id)
    if not invitation or invitation.event_id != event_id:
        raise_problem(
            404,
            code="event.invitation_not_found",
            detail="Invitation not found",
        )
    await crud_invitation.revoke(session, invitation=invitation)


# --- Join requests ------------------------------------------------------


@router.post(
    "/{event_id}/join-request",
    response_model=EventJoinRequestRead,
    status_code=201,
)
async def request_to_join_event(
    event_id: uuid.UUID,
    body: EventJoinRequestCreate,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EventJoinRequestRead:
    """Ask to be let into a public event.

    Private events are invitation-only, and are 404 to non-members anyway, so
    this only ever applies to the public catalogue.
    """
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_visible(current_user, session, db_event)

    if db_event.visibility != "public":
        raise_problem(
            403,
            code="event.not_joinable",
            detail="This event is invitation-only",
        )
    if await crud_membership.get(session, user_id=current_user.id, event_id=event_id):
        raise_problem(
            409,
            code="event.already_member",
            detail="You are already a member of this event",
        )

    request = await crud_join_request.upsert_pending(
        session,
        user_id=current_user.id,
        event_id=event_id,
        message=body.message,
    )

    from app.logic.notifications.triggers import dispatch_event_join_requested

    background_tasks.add_task(
        dispatch_event_join_requested,
        event_id=event_id,
        user_id=current_user.id,
    )

    return EventJoinRequestRead(
        **request.model_dump(),
        user_name=current_user.name,
        user_email=current_user.email,
        user_avatar_etag=current_user.avatar_etag,
    )


@router.delete("/{event_id}/join-request", status_code=204)
async def withdraw_join_request(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Withdraw your own pending request."""
    deleted = await crud_join_request.delete_for_user(
        session, user_id=current_user.id, event_id=event_id
    )
    if not deleted:
        raise_problem(
            404,
            code="event.join_request_not_found",
            detail="No join request to withdraw",
        )


@router.get("/{event_id}/join-requests", response_model=list[EventJoinRequestRead])
async def list_join_requests(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    status: str | None = Query(default="pending"),
) -> list[EventJoinRequestRead]:
    await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, event_id, minimum="admin")
    rows = await crud_join_request.list_for_event(
        session, event_id=event_id, status=status
    )
    return [
        EventJoinRequestRead(
            **request.model_dump(),
            user_name=user.name,
            user_email=user.email,
            user_avatar_etag=user.avatar_etag,
        )
        for request, user in rows
    ]


@router.post(
    "/{event_id}/join-requests/{request_id}/decide",
    response_model=EventJoinRequestRead,
)
async def decide_join_request(
    event_id: uuid.UUID,
    request_id: uuid.UUID,
    body: EventJoinRequestDecision,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EventJoinRequestRead:
    """Approve or decline someone's request to join."""
    await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, event_id, minimum="admin")

    request = await crud_join_request.get_by_id(session, request_id=request_id)
    if not request or request.event_id != event_id:
        raise_problem(
            404,
            code="event.join_request_not_found",
            detail="Join request not found",
        )
    if request.status != "pending":
        raise_problem(
            409,
            code="event.join_request_decided",
            detail="That request has already been decided",
        )

    decided = await crud_join_request.decide(
        session,
        request=request,
        approve=body.approve,
        decided_by_id=current_user.id,
    )
    if body.approve:
        await crud_membership.upsert(
            session,
            user_id=decided.user_id,
            event_id=event_id,
            role=body.role,
        )

    from app.logic.notifications.triggers import dispatch_event_join_decided

    background_tasks.add_task(
        dispatch_event_join_decided,
        event_id=event_id,
        user_id=decided.user_id,
        approved=body.approve,
    )

    applicant = await crud_user.get(session, id=decided.user_id)
    return EventJoinRequestRead(
        **decided.model_dump(),
        user_name=applicant.name if applicant else None,
        user_email=applicant.email if applicant else None,
        user_avatar_etag=applicant.avatar_etag if applicant else None,
    )
