import uuid

from fastapi import APIRouter, BackgroundTasks, Query
from sqlalchemy import select
from sqlmodel import col

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.event_membership import event_membership as crud_membership
from app.crud.task import task as crud_task
from app.logic.event_scope import get_user_event_scope, get_visible_event_ids
from app.logic.location_assignment import location_patch
from app.logic.locations import (
    apply_location,
    resolve_location,
    unlink_task_children,
)
from app.logic.permissions import get_event_role, require_event_role
from app.models.shift import Shift
from app.models.task import Task
from app.schemas.booking import TaskBookingEntry
from app.schemas.task import (
    TaskCreate,
    TaskListResponse,
    TaskRead,
    TaskStatus,
    TaskUpdate,
)

router = APIRouter()


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    session: DBDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    search: str | None = None,
    status: TaskStatus | None = None,
    my_bookings: bool = Query(default=False),
    event_id: uuid.UUID | None = Query(default=None),
    all_events: bool = Query(default=False),
) -> TaskListResponse:
    """List tasks from the events the caller belongs to.

    Membership is the outer boundary: you never see a task in an event you are
    not in. Within your events, drafts are visible only to those who can
    manage the event; everyone else sees published tasks.

    Defaults to scoping by the current user's selected event. Pass an explicit
    ``event_id`` to override, or ``all_events=true`` to disable that scoping
    (membership still applies).
    """
    effective_status = status
    also_include_group_ids = None

    visible_event_ids = await get_visible_event_ids(session, current_user)
    if visible_event_ids is not None:
        manageable_ids = await crud_membership.list_event_ids_for_user(
            session, user_id=current_user.id, minimum_role="admin"
        )
        if effective_status is None:
            effective_status = "published"
        if manageable_ids:
            # Within events they run, admins also see drafts.
            also_include_group_ids = manageable_ids

    effective_event_id = event_id
    if effective_event_id is None and not all_events:
        effective_event_id = get_user_event_scope(current_user)

    booked_by_user_id = str(current_user.id) if my_bookings else None

    items = await crud_task.get_multi_filtered(
        session,
        skip=skip,
        limit=limit,
        search=search,
        status=effective_status,
        booked_by_user_id=booked_by_user_id,
        also_include_group_ids=also_include_group_ids,
        event_id=effective_event_id,
        restrict_to_event_ids=visible_event_ids,
    )
    total = await crud_task.get_count_filtered(
        session,
        search=search,
        status=effective_status,
        booked_by_user_id=booked_by_user_id,
        also_include_group_ids=also_include_group_ids,
        event_id=effective_event_id,
        restrict_to_event_ids=visible_event_ids,
    )
    return TaskListResponse(
        items=[TaskRead.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> Task:
    db_task = await crud_task.get(session, task_id, raise_404_error=True)
    role = await get_event_role(current_user, session, db_task.event_id)
    if role is None:
        raise_problem(
            404,
            code="task.not_found",
            detail="Task not found",
        )
    if db_task.status != "published" and role not in ("owner", "admin"):
        raise_problem(403, code="task.not_published", detail="Task is not published")
    return db_task


@router.post("/", response_model=TaskRead, status_code=201)
async def create_task(
    task_in: TaskCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> Task:
    await require_event_role(current_user, session, task_in.event_id)
    loc = await resolve_location(
        session, event_id=task_in.event_id, location_id=task_in.location_id
    )
    apply_location(task_in, loc, task_in.location)
    task_in.created_by_id = current_user.id
    return await crud_task.create(session, obj_in=task_in)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: str,
    task_in: TaskUpdate,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> Task:
    db_task = await crud_task.get(session, task_id, raise_404_error=True)
    await require_event_role(current_user, session, db_task.event_id)
    old_status = db_task.status
    update_data = task_in.model_dump(exclude_unset=True)
    target_event_id = update_data.get("event_id", db_task.event_id)
    moving = target_event_id != db_task.event_id
    if moving:
        # Moving a task is a write into the target event as well.
        await require_event_role(current_user, session, target_event_id)
        # A location belongs to one event; moving the task drops the link on
        # it and on its batches and shifts, keeping the names as free text.
        await unlink_task_children(session, db_task.id)
        if "location_id" not in update_data:
            update_data["location_id"] = None
    update_data.update(
        await location_patch(session, db_task, update_data, event_id=target_event_id)
    )
    updated = await crud_task.update(session, db_obj=db_task, obj_in=update_data)

    # Notify when task is published
    if old_status != "published" and updated.status == "published":
        from app.logic.notifications.triggers import dispatch_task_published

        background_tasks.add_task(
            dispatch_task_published,
            task_id=updated.id,
            task_name=updated.name,
            event_id=updated.event_id,
            # This fan-out reaches every active account on the installation.
            # A demo guest publishing a seeded task - which the manager tour
            # walks them through - must not put their throwaway task name in
            # front of the whole user base.
            is_sandbox=updated.is_sandbox,
        )

    return updated


@router.get("/{task_id}/bookings", response_model=list[TaskBookingEntry])
async def list_task_bookings(
    task_id: str,
    session: DBDep,
    _current_user: CurrentUser,
) -> list[TaskBookingEntry]:
    """List all confirmed bookings for every shift in a task, with user info."""
    import uuid as _uuid

    await crud_task.get(session, task_id, raise_404_error=True)
    bookings = await crud_booking.get_confirmed_by_task(
        session, task_id=_uuid.UUID(task_id)
    )
    return [
        TaskBookingEntry(
            id=b.id,
            shift_id=b.shift_id,  # type: ignore[arg-type]
            user_name=b.user.name if b.user else None,
            user_phone_number=b.user.phone_number if b.user else None,
        )
        for b in bookings
    ]


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: str,
    session: DBDep,
    current_user: CurrentUser,
    cancellation_reason: str | None = Query(default=None),
) -> None:
    db_task = await crud_task.get(session, task_id, raise_404_error=True)
    await require_event_role(current_user, session, db_task.event_id)

    # Collect all shift IDs for this task
    stmt = select(col(Shift.id)).where(col(Shift.task_id) == db_task.id)
    result = await session.execute(stmt)
    slot_ids = list(result.scalars().all())

    # Cancel confirmed bookings with snapshot before deleting
    await crud_booking.cancel_bookings_for_shifts(
        session,
        slot_ids=slot_ids,
        task_name=db_task.name,
        cancellation_reason=cancellation_reason,
    )

    await session.delete(db_task)
    await session.commit()
