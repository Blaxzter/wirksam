import uuid

from fastapi import APIRouter, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.event_membership import event_membership as crud_membership
from app.crud.shift import shift as crud_shift
from app.crud.shift_batch import shift_batch as crud_shift_batch
from app.crud.task import task as crud_task
from app.crud.task_manager import task_manager as crud_task_manager
from app.logic import clock
from app.logic.booking_conflicts import mark_collisions
from app.logic.event_scope import get_visible_event_ids
from app.logic.location_assignment import location_patch
from app.logic.locations import apply_location, resolve_location
from app.logic.permissions import (
    check_shift_history,
    require_task_manager,
    require_task_visible,
    task_access,
)
from app.logic.teams import mark_team_locks
from app.models.shift import Shift
from app.schemas.booking import ShiftBookingEntry
from app.schemas.shift import (
    ShiftCreate,
    ShiftListResponse,
    ShiftRead,
    ShiftUpdate,
)

router = APIRouter(prefix="/shifts", tags=["shifts"])


async def _enrich_shift(
    session: AsyncSession,
    shift: Shift,
    user_id: uuid.UUID | None = None,
) -> ShiftRead:
    """Add current_bookings count and is_booked_by_me to a ShiftRead."""
    count = await crud_booking.get_confirmed_count(session, shift_id=shift.id)
    read = ShiftRead.model_validate(shift)
    read.current_bookings = count
    if user_id:
        my_booking = await crud_booking.get_by_shift_and_user(
            session, shift_id=shift.id, user_id=user_id
        )
        read.is_booked_by_me = (
            my_booking is not None and my_booking.status == "confirmed"
        )
    return read


@router.get("/", response_model=ShiftListResponse)
async def list_shifts(
    session: DBDep,
    current_user: CurrentUser,
    task_id: str | None = None,
    category: str | None = None,
    search: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> ShiftListResponse:
    if task_id:
        db_task = await crud_task.get(session, task_id, raise_404_error=True)
        await require_task_visible(current_user, session, db_task)

    # Without a task_id this route used to enumerate every shift in the
    # database - the check above only runs when one is supplied. The scope is
    # applied unconditionally now, so the unfiltered form answers with the
    # caller's own events rather than with everyone's.
    visible_event_ids = await get_visible_event_ids(session, current_user)

    # And, like the task list, only the shifts of published tasks, plus the
    # drafts of events the caller runs and of tasks they are in charge of.
    # With a task_id the gate above has already decided.
    status: str | None = None
    also_include_event_ids: list[uuid.UUID] | None = None
    also_include_task_ids: list[uuid.UUID] | None = None
    if not task_id and visible_event_ids is not None:
        status = "published"
        also_include_event_ids = await crud_membership.list_event_ids_for_user(
            session, user_id=current_user.id, minimum_role="admin"
        )
        also_include_task_ids = await crud_task_manager.task_ids_for_user(
            session, user_id=current_user.id
        )

    items = await crud_shift.get_multi_filtered(
        session,
        skip=skip,
        limit=limit,
        task_id=task_id,
        category=category,
        search=search,
        restrict_to_event_ids=visible_event_ids,
        status=status,
        also_include_event_ids=also_include_event_ids,
        also_include_task_ids=also_include_task_ids,
    )
    enriched = [await _enrich_shift(session, s, user_id=current_user.id) for s in items]
    await mark_collisions(session, user_id=current_user.id, entries=enriched)
    await mark_team_locks(session, current_user, enriched)
    total = await crud_shift.get_count_filtered(
        session,
        task_id=task_id,
        category=category,
        search=search,
        restrict_to_event_ids=visible_event_ids,
        status=status,
        also_include_event_ids=also_include_event_ids,
        also_include_task_ids=also_include_task_ids,
    )
    return ShiftListResponse(items=enriched, total=total, skip=skip, limit=limit)


@router.get("/{slot_id}", response_model=ShiftRead)
async def get_shift(
    slot_id: str | None,
    session: DBDep,
    current_user: CurrentUser,
) -> ShiftRead:
    if slot_id is None:
        raise_problem(400, code="invalid_request", detail="slot_id is required")

    shift = await crud_shift.get(session, slot_id, raise_404_error=True)
    # This route had no permission check at all: any signed-in account could
    # read any shift in the installation by id. The task's visibility gate is
    # what also keeps demo shifts private, since it holds a sandbox test of its
    # own. A booker of the shift may always open it, whatever the task's status.
    db_task = await crud_task.get(session, str(shift.task_id), raise_404_error=True)
    await require_task_visible(current_user, session, db_task, booked_shift_id=shift.id)
    read = await _enrich_shift(session, shift, user_id=current_user.id)
    await mark_collisions(session, user_id=current_user.id, entries=[read])
    await mark_team_locks(session, current_user, [read])
    return read


@router.post("/", response_model=ShiftRead, status_code=201)
async def create_shift(
    slot_in: ShiftCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> ShiftRead:
    db_task = await crud_task.get(session, str(slot_in.task_id), raise_404_error=True)
    await require_task_manager(current_user, session, db_task)
    if slot_in.batch_id is not None:
        # Otherwise the person in charge of one task could hang a shift on
        # another task's batch, and deleting that batch would delete it.
        db_batch = await crud_shift_batch.get(session, slot_in.batch_id)
        if db_batch is None or db_batch.task_id != db_task.id:
            raise_problem(
                400,
                code="batch.wrong_task",
                detail="Batch does not belong to this task",
            )
    loc = await resolve_location(
        session, event_id=db_task.event_id, location_id=slot_in.location_id
    )
    apply_location(slot_in, loc, slot_in.location)
    shift = await crud_shift.create(session, obj_in=slot_in)
    return await _enrich_shift(session, shift)


@router.patch("/{slot_id}", response_model=ShiftRead)
async def update_shift(
    slot_id: str,
    slot_in: ShiftUpdate,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> ShiftRead:
    db_shift = await crud_shift.get(session, slot_id, raise_404_error=True)
    db_task = await crud_task.get(session, str(db_shift.task_id), raise_404_error=True)
    access = await require_task_manager(current_user, session, db_task)
    old_start = db_shift.start_time
    old_end = db_shift.end_time
    old_date = db_shift.date
    update_data = slot_in.model_dump(exclude_unset=True)
    if access == "manager" and any(
        k in update_data for k in ("date", "start_time", "end_time")
    ):
        count = await crud_booking.get_confirmed_count(session, shift_id=db_shift.id)
        check_shift_history(
            access,
            before=db_shift,
            has_bookings=count > 0,
            new_date=update_data.get("date") or db_shift.date,
            new_start=update_data.get("start_time", db_shift.start_time),
            new_end=update_data.get("end_time", db_shift.end_time),
            now=clock.wall_clock_now(),
        )
    update_data.update(
        await location_patch(session, db_shift, update_data, event_id=db_task.event_id)
    )
    updated = await crud_shift.update(session, db_obj=db_shift, obj_in=update_data)

    # Notify bookers if time changed
    time_changed = (
        (slot_in.start_time is not None and slot_in.start_time != old_start)
        or (slot_in.end_time is not None and slot_in.end_time != old_end)
        or (slot_in.date is not None and slot_in.date != old_date)
    )
    if time_changed:
        bookings = await crud_booking.get_multi_by_shift(
            session, shift_id=updated.id, status="confirmed"
        )
        booked_user_ids = [b.user_id for b in bookings]
        if booked_user_ids:
            from app.logic.notifications.triggers import dispatch_shift_time_changed

            background_tasks.add_task(
                dispatch_shift_time_changed,
                slot_id=updated.id,
                slot_title=updated.title,
                task_id=updated.task_id,
                booked_user_ids=booked_user_ids,
            )

    return await _enrich_shift(session, updated)


@router.delete("/{slot_id}", status_code=204)
async def delete_shift(
    slot_id: str,
    session: DBDep,
    current_user: CurrentUser,
    cancellation_reason: str | None = Query(default=None),
) -> None:
    shift = await crud_shift.get(session, slot_id, raise_404_error=True)

    # Get task name for snapshot
    db_task = await crud_task.get(session, str(shift.task_id), raise_404_error=True)
    access = await require_task_manager(current_user, session, db_task)
    if access == "manager":
        count = await crud_booking.get_confirmed_count(session, shift_id=shift.id)
        check_shift_history(
            access,
            before=shift,
            has_bookings=count > 0,
            deleting=True,
            now=clock.wall_clock_now(),
        )

    # Cancel confirmed bookings with snapshot before deleting the shift
    await crud_booking.cancel_bookings_for_shifts(
        session,
        slot_ids=[shift.id],
        task_name=db_task.name,
        cancellation_reason=cancellation_reason,
    )

    await session.delete(shift)
    await session.commit()


@router.get("/{slot_id}/bookings", response_model=list[ShiftBookingEntry])
async def list_shift_bookings(
    slot_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> list[ShiftBookingEntry]:
    """List confirmed bookings for a shift with basic user info.

    Every member who can see the task sees the names. E-mail, phone and notes
    only the event admins and the task's people in charge, and each booker on
    their own row.
    """
    shift = await crud_shift.get(session, slot_id, raise_404_error=True)
    db_task = await crud_task.get(session, shift.task_id, raise_404_error=True)
    await require_task_visible(current_user, session, db_task, booked_shift_id=shift.id)
    can_manage = await task_access(current_user, session, db_task) is not None
    bookings = await crud_booking.get_multi_by_shift(
        session, shift_id=shift.id, status="confirmed", with_user=True
    )
    entries: list[ShiftBookingEntry] = []
    for b in bookings:
        show = can_manage or b.user_id == current_user.id
        entries.append(
            ShiftBookingEntry(
                id=b.id,
                user_id=b.user_id,
                user_name=b.user.name if b.user else None,
                user_email=b.user.email if b.user and show else None,
                user_avatar_etag=b.user.avatar_etag if b.user else None,
                user_phone_number=b.user.phone_number if b.user and show else None,
                notes=b.notes if show else None,
                created_at=b.created_at,
            )
        )
    return entries
