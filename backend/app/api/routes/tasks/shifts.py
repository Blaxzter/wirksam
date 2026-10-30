import uuid
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.event import event as crud_event
from app.crud.event_membership import event_membership as crud_membership
from app.crud.shift import shift as crud_shift
from app.crud.shift_batch import shift_batch as crud_shift_batch
from app.crud.task import task as crud_task
from app.crud.task_manager import task_manager as crud_task_manager
from app.logic import clock
from app.logic.locations import resolve_location
from app.logic.permissions import (
    check_shift_history,
    require_event_role,
    require_task_manager,
    shift_history_refuses,
)
from app.logic.shift_generator import generate_shifts
from app.logic.task_managers import decorate_task_reads
from app.logic.teams import ensure_team_in_event
from app.models.booking import Booking
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User
from app.schemas.event import EventRead
from app.schemas.shift import ShiftCreate
from app.schemas.shift_batch import ShiftBatchCreate
from app.schemas.task import (
    AddShiftsResponse,
    AddShiftsToTask,
    AffectedBookingInfo,
    ShiftRegenerationResult,
    TaskCreate,
    TaskCreateWithShifts,
    TaskCreateWithShiftsResponse,
    TaskRead,
    TaskUpdateWithShifts,
)

router = APIRouter()


async def _task_read(session: AsyncSession, user: User, task: Task) -> TaskRead:
    """The task inside a write response, with its viewer-relative fields."""
    read = TaskRead.model_validate(task)
    await decorate_task_reads(session, user, [read])
    return read


async def _validate_manager_ids(
    session: AsyncSession, payload: TaskCreateWithShifts
) -> list[uuid.UUID]:
    """The deduplicated ``manager_ids``, each a member of ``payload.event_id``.

    Checked before anything is written. A task in a brand-new event (or in no
    event) has nobody to put in charge yet.
    """
    ids = list(dict.fromkeys(payload.manager_ids))
    if not ids:
        return []
    member_ids: set[uuid.UUID] = (
        set(await crud_membership.list_user_ids(session, event_id=payload.event_id))
        if payload.event_id is not None and payload.new_event is None
        else set()
    )
    if any(i not in member_ids for i in ids):
        raise_problem(
            422,
            code="task.manager_not_event_member",
            detail="Only members of this event can be put in charge of its tasks",
        )
    return ids


@router.post(
    "/with-shifts", response_model=TaskCreateWithShiftsResponse, status_code=201
)
async def create_task_with_shifts(
    payload: TaskCreateWithShifts,
    session: DBDep,
    current_user: CurrentUser,
) -> TaskCreateWithShiftsResponse:
    """Create a task with auto-generated duty shifts in a single transaction."""
    # Check access for the target event (if any)
    await require_event_role(current_user, session, payload.event_id)
    manager_ids = await _validate_manager_ids(session, payload)
    # A location belongs to an existing event. Resolved before anything is
    # written, against ``payload.event_id`` only: an event created by this
    # very request has no locations yet, so any id is foreign to it.
    loc = await resolve_location(
        session, event_id=payload.event_id, location_id=payload.location_id
    )
    # A brand-new event has no teams, so this is checked against
    # ``payload.event_id`` like the location above.
    await ensure_team_in_event(
        session, team_id=payload.team_id, event_id=payload.event_id
    )
    location_text = loc.name if loc else payload.location
    location_id = loc.id if loc else None
    # 1. Optionally create a new event
    event_read: EventRead | None = None
    event_id = payload.event_id

    if payload.new_event:
        payload.new_event.created_by_id = current_user.id
        db_group = await crud_event.create(session, obj_in=payload.new_event)
        event_id = db_group.id
        event_read = EventRead.model_validate(db_group)

    # 2. Create the task with generation config stored
    task_in = TaskCreate(
        name=payload.name,
        description=payload.description,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=payload.status,
        location=location_text,
        location_id=location_id,
        category=payload.category,
        team_id=payload.team_id,
        event_id=event_id,
        created_by_id=current_user.id,
    )
    db_task = await crud_task.create(session, obj_in=task_in)

    # Store generation config on the task (kept for backwards compat)
    db_task.shift_duration_minutes = payload.schedule.shift_duration_minutes
    db_task.default_start_time = payload.schedule.default_start_time
    db_task.default_end_time = payload.schedule.default_end_time
    db_task.people_per_shift = payload.schedule.people_per_shift
    db_task.schedule_overrides = [
        o.model_dump(mode="json") for o in payload.schedule.overrides
    ]
    session.add(db_task)
    await session.flush()

    # 3. Create a ShiftBatch to store the generation config
    batch_in = ShiftBatchCreate(
        task_id=db_task.id,
        label=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        location=location_text,
        location_id=location_id,
        category=payload.category,
        default_start_time=payload.schedule.default_start_time,
        default_end_time=payload.schedule.default_end_time,
        shift_duration_minutes=payload.schedule.shift_duration_minutes,
        people_per_shift=payload.schedule.people_per_shift,
        remainder_mode=payload.schedule.remainder_mode,
        schedule_overrides=[
            o.model_dump(mode="json") for o in payload.schedule.overrides
        ],
    )
    db_batch = await crud_shift_batch.create(session, obj_in=batch_in)

    # 4. Generate and bulk-insert duty shifts linked to the batch
    slot_creates = generate_shifts(
        task_id=db_task.id,
        task_name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        default_start_time=payload.schedule.default_start_time,
        default_end_time=payload.schedule.default_end_time,
        shift_duration_minutes=payload.schedule.shift_duration_minutes,
        people_per_shift=payload.schedule.people_per_shift,
        remainder_mode=payload.schedule.remainder_mode,
        location=location_text,
        location_id=location_id,
        category=payload.category,
        overrides=payload.schedule.overrides,
        excluded_shifts=payload.schedule.excluded_shifts,
        specific_dates=payload.schedule.specific_dates,
    )

    for slot_in in slot_creates:
        slot_in.batch_id = db_batch.id
        await crud_shift.create(session, obj_in=slot_in)

    # 5. The people in charge, validated above.
    for user_id in manager_ids:
        await crud_task_manager.add(
            session, task_id=db_task.id, user_id=user_id, added_by=current_user
        )

    await session.flush()
    await session.refresh(db_task)

    return TaskCreateWithShiftsResponse(
        task=await _task_read(session, current_user, db_task),
        shifts_created=len(slot_creates),
        event=event_read,
    )


@router.post("/{task_id}/add-shifts", response_model=AddShiftsResponse, status_code=201)
async def add_shifts_to_task(
    task_id: str,
    payload: AddShiftsToTask,
    session: DBDep,
    current_user: CurrentUser,
) -> AddShiftsResponse:
    """Add a new batch of duty shifts to an existing task without touching existing shifts."""
    db_task = await crud_task.get(session, task_id, raise_404_error=True)
    await require_task_manager(current_user, session, db_task)

    # Validate dates against event constraints
    if db_task.event_id:
        db_group = await crud_event.get(session, db_task.event_id, raise_404_error=True)
        if (
            payload.start_date < db_group.start_date
            or payload.end_date > db_group.end_date
        ):
            raise_problem(
                400,
                code="dates_outside_event",
                detail=(
                    f"Shift dates must fall within the event date range "
                    f"({db_group.start_date} to {db_group.end_date})"
                ),
            )

    loc = await resolve_location(
        session, event_id=db_task.event_id, location_id=payload.location_id
    )
    location_text = loc.name if loc else payload.location
    location_id = loc.id if loc else None

    # Create a ShiftBatch record
    batch_in = ShiftBatchCreate(
        task_id=db_task.id,
        label=location_text or payload.category or db_task.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        location=location_text,
        location_id=location_id,
        category=payload.category,
        default_start_time=payload.schedule.default_start_time,
        default_end_time=payload.schedule.default_end_time,
        shift_duration_minutes=payload.schedule.shift_duration_minutes,
        people_per_shift=payload.schedule.people_per_shift,
        remainder_mode=payload.schedule.remainder_mode,
        schedule_overrides=[
            o.model_dump(mode="json") for o in payload.schedule.overrides
        ],
    )
    db_batch = await crud_shift_batch.create(session, obj_in=batch_in)

    slot_creates = generate_shifts(
        task_id=db_task.id,
        task_name=db_task.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        default_start_time=payload.schedule.default_start_time,
        default_end_time=payload.schedule.default_end_time,
        shift_duration_minutes=payload.schedule.shift_duration_minutes,
        people_per_shift=payload.schedule.people_per_shift,
        remainder_mode=payload.schedule.remainder_mode,
        location=location_text,
        location_id=location_id,
        category=payload.category,
        overrides=payload.schedule.overrides,
        excluded_shifts=payload.schedule.excluded_shifts,
        specific_dates=payload.schedule.specific_dates,
    )

    for slot_in in slot_creates:
        slot_in.batch_id = db_batch.id
        await crud_shift.create(session, obj_in=slot_in)

    await session.flush()
    await session.refresh(db_task)

    return AddShiftsResponse(
        task=await _task_read(session, current_user, db_task),
        shifts_added=len(slot_creates),
    )


@router.post(
    "/{task_id}/regenerate-shifts",
    response_model=ShiftRegenerationResult,
)
async def regenerate_task_shifts(
    task_id: str,
    payload: TaskUpdateWithShifts,
    session: DBDep,
    current_user: CurrentUser,
    dry_run: bool = Query(default=False),
    batch_id: str | None = Query(default=None),
) -> ShiftRegenerationResult:
    """Regenerate duty shifts for a task, preserving bookings where shifts match.

    When dry_run=True, returns a preview without making changes.
    When batch_id is provided, only regenerates shifts belonging to that batch.
    Shifts are matched by (date, start_time, end_time) — matched shifts keep their bookings.

    Bookings on removed shifts are cancelled with a snapshot, as on every other
    delete path. A person in charge may not remove a booked shift that has
    started (``check_shift_history``): the dry run marks such rows ``locked``,
    the real run refuses with 403 ``task.shift_history_admin_only``.
    """
    db_task = await crud_task.get(session, task_id, raise_404_error=True)
    access = await require_task_manager(current_user, session, db_task)

    # If batch_id provided, load the batch for defaults
    db_batch: ShiftBatch | None = None
    if batch_id:
        db_batch = await crud_shift_batch.get(session, batch_id, raise_404_error=True)
        if str(db_batch.task_id) != str(db_task.id):
            raise_problem(
                400,
                code="batch.wrong_task",
                detail="Batch does not belong to this task",
            )

    # Determine effective task fields (use payload overrides or existing/batch values)
    effective_name = payload.name or db_task.name
    # The batch's own values when scoped to one, otherwise the task's.
    source = db_batch if db_batch else db_task
    effective_start_date = payload.start_date or source.start_date
    effective_end_date = payload.end_date or source.end_date
    effective_location = (
        payload.location if payload.location is not None else source.location
    )
    effective_category = (
        payload.category if payload.category is not None else source.category
    )
    location_changed = payload.location is not None
    if "location_id" in payload.model_fields_set:
        # Sent explicitly, so it wins - ``null`` included, which unlinks and
        # keeps the text.
        loc = await resolve_location(
            session, event_id=db_task.event_id, location_id=payload.location_id
        )
        effective_location_id = loc.id if loc else None
        if loc:
            effective_location = loc.name
        location_changed = True
    elif payload.location is not None and payload.location != source.location:
        # New free text without an id: the old link no longer matches it.
        effective_location_id = None
    else:
        effective_location_id = source.location_id

    # 1. Generate new shift definitions
    new_shift_defs = generate_shifts(
        task_id=db_task.id,
        task_name=effective_name,
        start_date=effective_start_date,
        end_date=effective_end_date,
        default_start_time=payload.schedule.default_start_time,
        default_end_time=payload.schedule.default_end_time,
        shift_duration_minutes=payload.schedule.shift_duration_minutes,
        people_per_shift=payload.schedule.people_per_shift,
        remainder_mode=payload.schedule.remainder_mode,
        location=effective_location,
        location_id=effective_location_id,
        category=effective_category,
        overrides=payload.schedule.overrides,
        excluded_shifts=payload.schedule.excluded_shifts,
        specific_dates=payload.schedule.specific_dates,
    )

    # 2. Load existing shifts with their bookings (scoped to batch if provided)
    stmt = (
        select(Shift)
        .where(col(Shift.task_id) == db_task.id)
        .options(
            selectinload(Shift.bookings).selectinload(Booking.user)  # type: ignore[arg-type]
        )
    )
    if batch_id:
        stmt = stmt.where(col(Shift.batch_id) == batch_id)
    result = await session.execute(stmt)
    existing_shifts = list(result.scalars().all())

    # 3. Build lookup of existing shifts by (date, start_time, end_time)
    existing_lookup: dict[tuple[Any, ...], Shift] = {}
    for shift in existing_shifts:
        key = (shift.date, shift.start_time, shift.end_time)
        existing_lookup[key] = shift

    # 4. Match new shifts to existing
    matched_keys: set[tuple[Any, ...]] = set()
    shifts_to_create: list[ShiftCreate] = []
    for new_shift in new_shift_defs:
        key = (new_shift.date, new_shift.start_time, new_shift.end_time)
        if key in existing_lookup:
            matched_keys.add(key)
            # Update title and max_bookings on matched shifts
            existing = existing_lookup[key]
            existing.title = new_shift.title
            existing.max_bookings = new_shift.max_bookings
            existing.location = new_shift.location
            existing.location_id = new_shift.location_id
            existing.category = new_shift.category
        else:
            shifts_to_create.append(new_shift)

    # 5. Find unmatched existing shifts (to be deleted) and their confirmed bookings
    now = clock.wall_clock_now()
    affected_bookings: list[AffectedBookingInfo] = []
    shifts_to_delete: list[Shift] = []
    any_locked = False
    for key, shift in existing_lookup.items():
        if key not in matched_keys:
            shifts_to_delete.append(shift)
            confirmed = [b for b in shift.bookings if b.status == "confirmed"]
            locked = shift_history_refuses(
                access,
                before=shift,
                has_bookings=bool(confirmed),
                deleting=True,
                now=now,
            )
            any_locked = any_locked or locked
            for booking in confirmed:
                affected_bookings.append(
                    AffectedBookingInfo(
                        booking_id=booking.id,
                        user_id=booking.user_id,
                        user_name=booking.user.name if booking.user else None,
                        slot_title=shift.title,
                        slot_date=shift.date,
                        slot_start_time=shift.start_time,
                        slot_end_time=shift.end_time,
                        locked=locked,
                    )
                )

    if not dry_run and any_locked:
        # Raises: the same rule the dry run reported as ``locked``.
        for shift in shifts_to_delete:
            check_shift_history(
                access,
                before=shift,
                has_bookings=any(b.status == "confirmed" for b in shift.bookings),
                deleting=True,
                now=now,
            )

    if not dry_run:
        # 6a. Update task fields (only when not scoped to a batch)
        if not batch_id:
            if payload.name is not None:
                db_task.name = payload.name
            if payload.description is not None:
                db_task.description = payload.description
            if payload.start_date is not None:
                db_task.start_date = payload.start_date
            if payload.end_date is not None:
                db_task.end_date = payload.end_date
            if location_changed:
                db_task.location = effective_location
                db_task.location_id = effective_location_id
            if payload.category is not None:
                db_task.category = payload.category

            # Store generation config on task
            db_task.shift_duration_minutes = payload.schedule.shift_duration_minutes
            db_task.default_start_time = payload.schedule.default_start_time
            db_task.default_end_time = payload.schedule.default_end_time
            db_task.people_per_shift = payload.schedule.people_per_shift
            db_task.schedule_overrides = [
                o.model_dump(mode="json") for o in payload.schedule.overrides
            ]
            session.add(db_task)

        # 6b. Update batch record if scoped
        if db_batch:
            db_batch.start_date = effective_start_date
            db_batch.end_date = effective_end_date
            db_batch.location = effective_location
            db_batch.location_id = effective_location_id
            db_batch.category = effective_category
            db_batch.default_start_time = payload.schedule.default_start_time
            db_batch.default_end_time = payload.schedule.default_end_time
            db_batch.shift_duration_minutes = payload.schedule.shift_duration_minutes
            db_batch.people_per_shift = payload.schedule.people_per_shift
            db_batch.remainder_mode = payload.schedule.remainder_mode
            db_batch.schedule_overrides = [
                o.model_dump(mode="json") for o in payload.schedule.overrides
            ]
            session.add(db_batch)

        # 6c. Delete unmatched shifts. Their confirmed bookings are cancelled
        #     with a snapshot first, like every other delete path: the FK is
        #     SET NULL, so they would otherwise stay "confirmed" with no shift
        #     and drop out of everyone's hours without a word.
        await crud_booking.cancel_bookings_for_shifts(
            session,
            slot_ids=[s.id for s in shifts_to_delete],
            task_name=db_task.name,
        )
        for shift in shifts_to_delete:
            await session.delete(shift)

        # 6d. Create new shifts (linked to batch if scoped)
        for slot_in in shifts_to_create:
            if batch_id and db_batch:
                slot_in.batch_id = db_batch.id
            await crud_shift.create(session, obj_in=slot_in)

        await session.flush()
        await session.refresh(db_task)

    return ShiftRegenerationResult(
        task=await _task_read(session, current_user, db_task),
        shifts_added=len(shifts_to_create),
        shifts_removed=len(shifts_to_delete),
        shifts_kept=len(matched_keys),
        affected_bookings=affected_bookings,
    )
