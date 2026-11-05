import uuid

from fastapi import APIRouter, BackgroundTasks, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.crud.event import event as crud_event
from app.crud.event_invitation_task import (
    event_invitation_task as crud_invitation_task,
)
from app.crud.event_membership import event_membership as crud_membership
from app.crud.shift_batch import shift_batch as crud_shift_batch
from app.crud.task import task as crud_task
from app.crud.task_manager import task_manager as crud_task_manager
from app.logic import clock, vouchers
from app.logic.event_scope import get_user_event_scope, get_visible_event_ids
from app.logic.location_assignment import location_patch
from app.logic.locations import (
    apply_location,
    follow_task_place,
    resolve_location,
    unlink_task_children,
)
from app.logic.notifications.triggers import dispatch_booking_cancelled_by_admin
from app.logic.permissions import (
    require_event_role,
    require_task_manager,
    require_task_visible,
    task_access,
)
from app.logic.shift_generator import renamed_shift_title
from app.logic.task_managers import decorate_task_reads
from app.logic.teams import ensure_team_in_event
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.booking import TaskBookingEntry
from app.schemas.task import (
    TaskCreate,
    TaskListResponse,
    TaskRead,
    TaskStatus,
    TaskUpdate,
)

router = APIRouter()

#: What only event admins may change on a task, even when a person in charge
#: sends the edit: publishing fans a notification out to the event's members,
#: ``team_id`` decides who may book, moving needs admin in both events, and
#: vouchers are currency, so the rate and the places that take them are the
#: organisers' decision.
ADMIN_ONLY_TASK_FIELDS: tuple[str, ...] = (
    "status",
    "event_id",
    "team_id",
    "vouchers_per_shift",
    "is_voucher_point",
)

#: Task columns that are NOT NULL, where an explicit ``null`` in a PATCH can
#: only mean "leave it".
_NOT_NULL_VOUCHER_FIELDS = ("vouchers_per_shift", "is_voucher_point")


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
    manage the event and to a task's people in charge; everyone else sees
    published tasks.

    Defaults to scoping by the current user's selected event. Pass an explicit
    ``event_id`` to override, or ``all_events=true`` to disable that scoping
    (membership still applies).

    ``status`` narrows that further and never widens it: a member asking for
    ``draft`` gets the drafts they may see, which is none.
    """
    # What the caller may see, as opposed to the ``status`` they asked for.
    # None for the superadmin, who sees every status.
    visible_status: str | None = None
    also_include_group_ids = None
    also_include_task_ids = None

    visible_event_ids = await get_visible_event_ids(session, current_user)
    if visible_event_ids is not None:
        manageable_ids = await crud_membership.list_event_ids_for_user(
            session, user_id=current_user.id, minimum_role="admin"
        )
        visible_status = "published"
        if manageable_ids:
            # Within events they run, admins also see drafts.
            also_include_group_ids = manageable_ids
        # And people in charge the drafts of their own tasks.
        also_include_task_ids = await crud_task_manager.task_ids_for_user(
            session, user_id=current_user.id
        )

    effective_event_id = event_id
    if effective_event_id is None and not all_events:
        effective_event_id = get_user_event_scope(current_user)

    booked_by_user_id = str(current_user.id) if my_bookings else None

    items = await crud_task.get_multi_filtered(
        session,
        skip=skip,
        limit=limit,
        search=search,
        status=visible_status,
        only_status=status,
        booked_by_user_id=booked_by_user_id,
        also_include_group_ids=also_include_group_ids,
        also_include_task_ids=also_include_task_ids,
        event_id=effective_event_id,
        restrict_to_event_ids=visible_event_ids,
    )
    total = await crud_task.get_count_filtered(
        session,
        search=search,
        status=visible_status,
        only_status=status,
        booked_by_user_id=booked_by_user_id,
        also_include_group_ids=also_include_group_ids,
        also_include_task_ids=also_include_task_ids,
        event_id=effective_event_id,
        restrict_to_event_ids=visible_event_ids,
    )
    reads = [TaskRead.model_validate(i) for i in items]
    await decorate_task_reads(session, current_user, reads)
    return TaskListResponse(
        items=reads,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> TaskRead:
    db_task = await crud_task.get(session, task_id, raise_404_error=True)
    await require_task_visible(current_user, session, db_task)
    return await _decorated(session, current_user, db_task)


async def _decorated(session: AsyncSession, user: User, task: Task) -> TaskRead:
    """A task read with its viewer-relative fields (team lock, access) filled."""
    read = TaskRead.model_validate(task)
    await decorate_task_reads(session, user, [read])
    return read


@router.post("/", response_model=TaskRead, status_code=201)
async def create_task(
    task_in: TaskCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> TaskRead:
    await require_event_role(current_user, session, task_in.event_id)
    loc = await resolve_location(
        session, event_id=task_in.event_id, location_id=task_in.location_id
    )
    apply_location(task_in, loc, task_in.location)
    await ensure_team_in_event(
        session, team_id=task_in.team_id, event_id=task_in.event_id
    )
    task_in.created_by_id = current_user.id
    created = await crud_task.create(session, obj_in=task_in)
    return await _decorated(session, current_user, created)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: str,
    task_in: TaskUpdate,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> TaskRead:
    """Edit a task. Event admins, and its people in charge.

    A person in charge may not change ``ADMIN_ONLY_TASK_FIELDS``: a changed
    value is refused with 403 ``task.admin_only_field`` (naming the fields),
    while one sent with its current value is ignored, so a form that always
    sends the whole task keeps working for them.
    """
    db_task = await crud_task.get(session, task_id, raise_404_error=True)
    access = await require_task_manager(current_user, session, db_task)
    old_status = db_task.status
    update_data = task_in.model_dump(exclude_unset=True)
    for f in _NOT_NULL_VOUCHER_FIELDS:
        if f in update_data and update_data[f] is None:
            del update_data[f]
    if access == "manager":
        changed = [
            f
            for f in ADMIN_ONLY_TASK_FIELDS
            if f in update_data and update_data[f] != getattr(db_task, f)
        ]
        if changed:
            raise_problem(
                403,
                code="task.admin_only_field",
                detail="Only event admins can change this",
                extensions={"fields": changed},
            )
        for f in ADMIN_ONLY_TASK_FIELDS:
            update_data.pop(f, None)
    target_event_id = update_data.get("event_id", db_task.event_id)
    moving = target_event_id != db_task.event_id
    rate_changing = (
        "vouchers_per_shift" in update_data
        and update_data["vouchers_per_shift"] != db_task.vouchers_per_shift
    )
    if moving:
        # Moving a task is a write into the target event as well.
        await require_event_role(current_user, session, target_event_id)
    if rate_changing or moving:
        # Earned is earned: what ended shifts earned is frozen at the old rate,
        # and in the source event, before either changes. A rate change also
        # freezes zero-rate bookings, so raising a rate from 0 pays only for
        # shifts not over yet.
        await vouchers.settle_earnings(
            session,
            now=clock.wall_clock_now(
                await crud_event.zone_of(session, db_task.event_id)
            ),
            task_ids=[db_task.id],
            include_zero=rate_changing,
        )
    if moving:
        # A location belongs to one event; moving the task drops the link on
        # it and on its batches and shifts, keeping the names as free text.
        await unlink_task_children(session, db_task.id)
        if "location_id" not in update_data:
            update_data["location_id"] = None
        # Teams belong to one event too, and unlike a location there is no
        # text to fall back on: the gate simply goes.
        if "team_id" not in update_data:
            update_data["team_id"] = None
        # People in charge are members of the source event, not the target,
        # and an invitation to run it was an invitation into the source event.
        await crud_task_manager.remove_all_for_task(session, task_id=db_task.id)
        await crud_invitation_task.detach_task(session, task_id=db_task.id)
    await ensure_team_in_event(
        session,
        team_id=update_data.get("team_id", db_task.team_id),
        event_id=target_event_id,
    )
    update_data.update(
        await location_patch(session, db_task, update_data, event_id=target_event_id)
    )
    old_place = (db_task.location, db_task.location_id)
    new_place = (
        update_data.get("location", db_task.location),
        update_data.get("location_id", db_task.location_id),
    )
    if new_place != old_place:
        await follow_task_place(session, db_task.id, old=old_place, new=new_place)
    new_name = update_data.get("name")
    if new_name and new_name != db_task.name:
        await _retitle_shifts(
            session, db_task.id, old_name=db_task.name, new_name=new_name
        )
        await crud_shift_batch.follow_task_rename(
            session, task_id=db_task.id, old_name=db_task.name, new_name=new_name
        )
    updated = await crud_task.update(session, db_obj=db_task, obj_in=update_data)
    if moving:
        # Its shifts are now read in the target event's zone.
        await crud_reminder.reschedule(session, task_id=updated.id)

    # Notify when task is published
    if old_status != "published" and updated.status == "published":
        from app.logic.notifications.triggers import dispatch_task_published

        background_tasks.add_task(
            dispatch_task_published,
            task_id=updated.id,
            task_name=updated.name,
            event_id=updated.event_id,
            is_sandbox=updated.is_sandbox,
        )

    return await _decorated(session, current_user, updated)


async def _retitle_shifts(
    session: AsyncSession, task_id: uuid.UUID, *, old_name: str, new_name: str
) -> None:
    """Take a rename to the shifts whose titles carry the task's name.

    Generated shifts are titled "<task name> 10:00-12:00", and the dashboard,
    the bookings and the print views show that title. Regenerating renames the
    shifts it keeps; a plain save of the details has to do the same, or a task
    with several batches (whose edit never regenerates) keeps its old name on
    every shift. Titles someone typed stay (``renamed_shift_title``).
    """
    shifts = (
        await session.execute(select(Shift).where(col(Shift.task_id) == task_id))
    ).scalars()
    for shift in shifts:
        title = renamed_shift_title(shift.title, old_name=old_name, new_name=new_name)
        if title is not None:
            shift.title = title
            session.add(shift)


@router.get("/{task_id}/bookings", response_model=list[TaskBookingEntry])
async def list_task_bookings(
    task_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> list[TaskBookingEntry]:
    """List all confirmed bookings for every shift in a task, with user info.

    Phone numbers only for the event admins and the task's people in charge.
    """
    db_task = await crud_task.get(session, task_id, raise_404_error=True)
    await require_task_visible(current_user, session, db_task)
    show_contact = await task_access(current_user, session, db_task) is not None
    bookings = await crud_booking.get_confirmed_by_task(session, task_id=db_task.id)
    return [
        TaskBookingEntry(
            id=b.id,
            shift_id=b.shift_id,  # type: ignore[arg-type]
            user_name=b.user.name if b.user else None,
            user_phone_number=(
                b.user.phone_number if b.user and show_contact else None
            ),
        )
        for b in bookings
    ]


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: str,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    cancellation_reason: str | None = Query(default=None),
) -> None:
    db_task = await crud_task.get(session, task_id, raise_404_error=True)
    await require_event_role(current_user, session, db_task.event_id)

    # Collect all shift IDs for this task
    stmt = select(col(Shift.id)).where(col(Shift.task_id) == db_task.id)
    result = await session.execute(stmt)
    slot_ids = list(result.scalars().all())

    now = clock.wall_clock_now(await crud_event.zone_of(session, db_task.event_id))
    # What the worked shifts earned stays earned, under the task's name.
    await vouchers.settle_earnings(session, now=now, task_ids=[db_task.id])
    # An invitation that existed only to run this task is withdrawn, so its
    # link says so; the links themselves would go by cascade.
    await crud_invitation_task.detach_task(session, task_id=db_task.id)
    # Cancel confirmed bookings with snapshot before deleting
    cancelled = await crud_booking.cancel_bookings_for_shifts(
        session,
        slot_ids=slot_ids,
        task_name=db_task.name,
        cancellation_reason=cancellation_reason,
    )
    background_tasks.add_task(
        dispatch_booking_cancelled_by_admin,
        cancelled=cancelled,
        actor_id=current_user.id,
        task_id=db_task.id,
        task_name=db_task.name,
        task_is_open=False,
        now=now,
        event_id=db_task.event_id,
        reason=cancellation_reason,
        is_sandbox=db_task.is_sandbox,
    )

    await session.delete(db_task)
    await session.commit()
