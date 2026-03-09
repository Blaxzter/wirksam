import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select as sa_select

from app.api.deps import CurrentSuperuser, CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.event_group import event_group as crud_event_group
from app.crud.user_availability import user_availability as crud_availability
from app.models.event_group import EventGroup
from app.models.user import User as UserModel
from app.schemas.event_group import (
    EventGroupCreate,
    EventGroupListResponse,
    EventGroupRead,
    EventGroupStatus,
    EventGroupUpdate,
)
from app.schemas.user_availability import (
    UserAvailabilityCreate,
    UserAvailabilityRead,
    UserAvailabilityWithUser,
)

router = APIRouter(prefix="/event-groups", tags=["event-groups"])


@router.get("/", response_model=EventGroupListResponse)
async def list_event_groups(
    session: DBDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    search: str | None = None,
    status: EventGroupStatus | None = None,
) -> EventGroupListResponse:
    """List published event groups (all users) or all groups (admin)."""
    effective_status = status
    if not current_user.is_admin and effective_status is None:
        effective_status = "published"

    items = await crud_event_group.get_multi_filtered(
        session, skip=skip, limit=limit, search=search, status=effective_status
    )
    total = await crud_event_group.get_count_filtered(
        session, search=search, status=effective_status
    )
    return EventGroupListResponse(
        items=[EventGroupRead.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{group_id}", response_model=EventGroupRead)
async def get_event_group(
    group_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> EventGroup:
    db_group = await crud_event_group.get(session, group_id, raise_404_error=True)
    if not current_user.is_admin and db_group.status != "published":
        raise_problem(
            403,
            code="event_group.not_published",
            detail="Event group is not published",
        )
    return db_group


@router.post("/", response_model=EventGroupRead, status_code=201)
async def create_event_group(
    group_in: EventGroupCreate,
    session: DBDep,
    current_user: CurrentSuperuser,
) -> EventGroup:
    group_in.created_by_id = current_user.id
    return await crud_event_group.create(session, obj_in=group_in)


@router.patch("/{group_id}", response_model=EventGroupRead)
async def update_event_group(
    group_id: str,
    group_in: EventGroupUpdate,
    session: DBDep,
    _current_user: CurrentSuperuser,
) -> EventGroup:
    db_group = await crud_event_group.get(session, group_id, raise_404_error=True)
    return await crud_event_group.update(session, db_obj=db_group, obj_in=group_in)


@router.delete("/{group_id}", status_code=204)
async def delete_event_group(
    group_id: str,
    session: DBDep,
    _current_user: CurrentSuperuser,
) -> None:
    db_group = await crud_event_group.get(session, group_id, raise_404_error=True)
    await session.delete(db_group)
    await session.commit()


# --- Availability endpoints ---


@router.get("/{group_id}/availabilities", response_model=list[UserAvailabilityWithUser])
async def list_group_availabilities(
    group_id: str,
    session: DBDep,
    _current_user: CurrentSuperuser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[UserAvailabilityWithUser]:
    """Admin: list all user availabilities for this event group."""
    await crud_event_group.get(session, group_id, raise_404_error=True)
    availabilities = await crud_availability.get_multi_by_group(
        session, event_group_id=uuid.UUID(group_id), skip=skip, limit=limit
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
            user_full_name=users_map[avail.user_id].name
            if avail.user_id in users_map
            else None,
            user_email=users_map[avail.user_id].email
            if avail.user_id in users_map
            else None,
        )
        for avail in availabilities
    ]


@router.get("/{group_id}/availability/me", response_model=UserAvailabilityRead)
async def get_my_availability(
    group_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> UserAvailabilityRead:
    avail = await crud_availability.get_by_user_and_group(
        session,
        user_id=current_user.id,
        event_group_id=uuid.UUID(group_id),
    )
    if not avail:
        raise_problem(
            404,
            code="availability.not_found",
            detail="No availability registered",
        )
    return UserAvailabilityRead.model_validate(avail)


@router.post(
    "/{group_id}/availability",
    response_model=UserAvailabilityRead,
    status_code=201,
)
async def set_my_availability(
    group_id: str,
    avail_in: UserAvailabilityCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> UserAvailabilityRead:
    await crud_event_group.get(session, group_id, raise_404_error=True)
    await crud_availability.upsert_for_user(
        session,
        user_id=current_user.id,
        event_group_id=uuid.UUID(group_id),
        obj_in=avail_in,
    )
    await session.commit()
    # Re-fetch after commit to get eagerly-loaded available_dates
    avail = await crud_availability.get_by_user_and_group(
        session,
        user_id=current_user.id,
        event_group_id=uuid.UUID(group_id),
    )
    return UserAvailabilityRead.model_validate(avail)


@router.delete("/{group_id}/availability/me", status_code=204)
async def delete_my_availability(
    group_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    deleted = await crud_availability.delete_for_user(
        session,
        user_id=current_user.id,
        event_group_id=uuid.UUID(group_id),
    )
    if not deleted:
        raise_problem(
            404,
            code="availability.not_found",
            detail="No availability registered",
        )
    await session.commit()
