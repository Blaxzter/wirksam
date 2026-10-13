import uuid

from fastapi import APIRouter, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.event import event as crud_event
from app.crud.shift import shift as crud_shift
from app.crud.task import task as crud_task
from app.logic.booking_conflicts import mark_collisions
from app.logic.event_scope import get_visible_event_ids
from app.logic.permissions import (
    get_event_role,
    require_event_role,
    require_event_visible,
)
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
        role = await get_event_role(current_user, session, db_task.event_id)
        if role is None:
            raise_problem(404, code="task.not_found", detail="Task not found")
        if db_task.status != "published" and role not in ("owner", "admin"):
            raise_problem(
                403, code="task.not_published", detail="Task is not published"
            )

    # Without a task_id this route used to enumerate every shift in the
    # database - the check above only runs when one is supplied. The scope is
    # applied unconditionally now, so the unfiltered form answers with the
    # caller's own events rather than with everyone's.
    visible_event_ids = await get_visible_event_ids(session, current_user)

    items = await crud_shift.get_multi_filtered(
        session,
        skip=skip,
        limit=limit,
        task_id=task_id,
        category=category,
        search=search,
        restrict_to_event_ids=visible_event_ids,
    )
    enriched = [await _enrich_shift(session, s, user_id=current_user.id) for s in items]
    await mark_collisions(session, user_id=current_user.id, entries=enriched)
    total = await crud_shift.get_count_filtered(
        session,
        task_id=task_id,
        category=category,
        search=search,
        restrict_to_event_ids=visible_event_ids,
    )
    return ShiftListResponse(items=enriched, total=total, skip=skip, limit=limit)


@router.get("/{slot_id}", response_model=ShiftRead)
async def get_shift(
    slot_id: str | None,
    session: DBDep,
    _current_user: CurrentUser,
) -> ShiftRead:
    if slot_id is None:
        raise_problem(400, code="invalid_request", detail="slot_id is required")

    shift = await crud_shift.get(session, slot_id, raise_404_error=True)
    # This route had no permission check at all: any signed-in account could
    # read any shift in the installation by id. Resolving the task and running
    # the standard visibility gate is what also keeps demo shifts private,
    # since that gate is where the sandbox test lives.
    db_task = await crud_task.get(session, str(shift.task_id), raise_404_error=True)
    if db_task.event_id is None:
        raise_problem(404, code="task.not_found", detail="Task not found")
    event = await crud_event.get(session, db_task.event_id, raise_404_error=True)
    await require_event_visible(_current_user, session, event)
    read = await _enrich_shift(session, shift, user_id=_current_user.id)
    await mark_collisions(session, user_id=_current_user.id, entries=[read])
    return read


@router.post("/", response_model=ShiftRead, status_code=201)
async def create_shift(
    slot_in: ShiftCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> ShiftRead:
    db_task = await crud_task.get(session, str(slot_in.task_id), raise_404_error=True)
    await require_event_role(current_user, session, db_task.event_id)
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
    await require_event_role(current_user, session, db_task.event_id)
    old_start = db_shift.start_time
    old_end = db_shift.end_time
    old_date = db_shift.date
    updated = await crud_shift.update(session, db_obj=db_shift, obj_in=slot_in)

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
    await require_event_role(current_user, session, db_task.event_id)

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
    slot_id: str,
    session: DBDep,
    _current_user: CurrentUser,
) -> list[ShiftBookingEntry]:
    """List confirmed bookings for a shift with basic user info."""
    await crud_shift.get(session, slot_id, raise_404_error=True)
    bookings = await crud_booking.get_multi_by_shift(
        session, shift_id=uuid.UUID(slot_id), status="confirmed", with_user=True
    )
    return [
        ShiftBookingEntry(
            id=b.id,
            user_id=b.user_id,
            user_name=b.user.name if b.user else None,
            user_email=b.user.email if b.user else None,
            user_avatar_etag=b.user.avatar_etag if b.user else None,
            user_phone_number=b.user.phone_number if b.user else None,
            notes=b.notes,
            created_at=b.created_at,
        )
        for b in bookings
    ]
