from fastapi import APIRouter, BackgroundTasks, Query
from sqlalchemy import select
from sqlmodel import col

from app.api.deps import CurrentSuperuser, CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.event import event as crud_event
from app.models.duty_slot import DutySlot
from app.models.event import Event
from app.schemas.event import (
    EventCreate,
    EventListResponse,
    EventRead,
    EventStatus,
    EventUpdate,
)

router = APIRouter()


@router.get("/", response_model=EventListResponse)
async def list_events(
    session: DBDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    search: str | None = None,
    status: EventStatus | None = None,
    my_bookings: bool = Query(default=False),
) -> EventListResponse:
    """List published events (all users) or all events (admin)."""
    effective_status = status
    if not current_user.is_admin and effective_status is None:
        effective_status = "published"

    booked_by_user_id = str(current_user.id) if my_bookings else None

    items = await crud_event.get_multi_filtered(
        session,
        skip=skip,
        limit=limit,
        search=search,
        status=effective_status,
        booked_by_user_id=booked_by_user_id,
    )
    total = await crud_event.get_count_filtered(
        session,
        search=search,
        status=effective_status,
        booked_by_user_id=booked_by_user_id,
    )
    return EventListResponse(
        items=[EventRead.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{event_id}", response_model=EventRead)
async def get_event(
    event_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> Event:
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    if not current_user.is_admin and db_event.status != "published":
        raise_problem(403, code="event.not_published", detail="Event is not published")
    return db_event


@router.post("/", response_model=EventRead, status_code=201)
async def create_event(
    event_in: EventCreate,
    session: DBDep,
    current_user: CurrentSuperuser,
) -> Event:
    event_in.created_by_id = current_user.id
    return await crud_event.create(session, obj_in=event_in)


@router.patch("/{event_id}", response_model=EventRead)
async def update_event(
    event_id: str,
    event_in: EventUpdate,
    session: DBDep,
    _current_user: CurrentSuperuser,
    background_tasks: BackgroundTasks,
) -> Event:
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    old_status = db_event.status
    updated = await crud_event.update(session, db_obj=db_event, obj_in=event_in)

    # Notify when event is published
    if old_status != "published" and updated.status == "published":
        from app.logic.notifications.triggers import dispatch_event_published

        background_tasks.add_task(
            dispatch_event_published,
            event_id=updated.id,
            event_name=updated.name,
            event_group_id=updated.event_group_id,
        )

    return updated


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    session: DBDep,
    _current_user: CurrentSuperuser,
    cancellation_reason: str | None = Query(default=None),
) -> None:
    db_event = await crud_event.get(session, event_id, raise_404_error=True)

    # Collect all slot IDs for this event
    stmt = select(col(DutySlot.id)).where(col(DutySlot.event_id) == db_event.id)
    result = await session.execute(stmt)
    slot_ids = list(result.scalars().all())

    # Cancel confirmed bookings with snapshot before deleting
    await crud_booking.cancel_bookings_for_slots(
        session,
        slot_ids=slot_ids,
        event_name=db_event.name,
        cancellation_reason=cancellation_reason,
    )

    await session.delete(db_event)
    await session.commit()
