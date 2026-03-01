from fastapi import APIRouter, Query

from app.api.deps import CurrentSuperuser, CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.event import event as crud_event
from app.models.event import Event
from app.schemas.event import (
    EventCreate,
    EventListResponse,
    EventRead,
    EventStatus,
    EventUpdate,
)

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/", response_model=EventListResponse)
async def list_events(
    session: DBDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    search: str | None = None,
    status: EventStatus | None = None,
) -> EventListResponse:
    """List published events (all users) or all events (admin)."""
    effective_status = status
    if not current_user.is_admin and effective_status is None:
        effective_status = "published"

    items = await crud_event.get_multi_filtered(
        session, skip=skip, limit=limit, search=search, status=effective_status
    )
    total = await crud_event.get_count_filtered(
        session, search=search, status=effective_status
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
) -> Event:
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    return await crud_event.update(session, db_obj=db_event, obj_in=event_in)


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    session: DBDep,
    _current_user: CurrentSuperuser,
) -> None:
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    await session.delete(db_event)
    await session.commit()
