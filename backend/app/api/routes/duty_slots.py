from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentSuperuser, CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.duty_slot import duty_slot as crud_duty_slot
from app.crud.event import event as crud_event
from app.models.duty_slot import DutySlot
from app.schemas.duty_slot import (
    DutySlotCreate,
    DutySlotListResponse,
    DutySlotRead,
    DutySlotUpdate,
)

router = APIRouter(prefix="/duty-slots", tags=["duty-slots"])


async def _enrich_slot(session: AsyncSession, slot: DutySlot) -> DutySlotRead:
    """Add current_bookings count to a DutySlotRead."""
    count = await crud_booking.get_confirmed_count(session, duty_slot_id=slot.id)
    read = DutySlotRead.model_validate(slot)
    read.current_bookings = count
    return read


@router.get("/", response_model=DutySlotListResponse)
async def list_duty_slots(
    session: DBDep,
    current_user: CurrentUser,
    event_id: str | None = None,
    category: str | None = None,
    search: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> DutySlotListResponse:
    if event_id:
        db_event = await crud_event.get(session, event_id, raise_404_error=True)
        if not current_user.is_admin and db_event.status != "published":
            raise_problem(403, code="event.not_published", detail="Event is not published")

    items = await crud_duty_slot.get_multi_filtered(
        session, skip=skip, limit=limit, event_id=event_id, category=category, search=search
    )
    enriched = [await _enrich_slot(session, s) for s in items]
    total = await crud_duty_slot.get_count_filtered(
        session, event_id=event_id, category=category, search=search
    )
    return DutySlotListResponse(items=enriched, total=total, skip=skip, limit=limit)


@router.get("/{slot_id}", response_model=DutySlotRead)
async def get_duty_slot(
    slot_id: str,
    session: DBDep,
    _current_user: CurrentUser,
) -> DutySlotRead:
    slot = await crud_duty_slot.get(session, slot_id, raise_404_error=True)
    return await _enrich_slot(session, slot)


@router.post("/", response_model=DutySlotRead, status_code=201)
async def create_duty_slot(
    slot_in: DutySlotCreate,
    session: DBDep,
    _current_user: CurrentSuperuser,
) -> DutySlotRead:
    await crud_event.get(session, str(slot_in.event_id), raise_404_error=True)
    slot = await crud_duty_slot.create(session, obj_in=slot_in)
    return await _enrich_slot(session, slot)


@router.patch("/{slot_id}", response_model=DutySlotRead)
async def update_duty_slot(
    slot_id: str,
    slot_in: DutySlotUpdate,
    session: DBDep,
    _current_user: CurrentSuperuser,
) -> DutySlotRead:
    db_slot = await crud_duty_slot.get(session, slot_id, raise_404_error=True)
    updated = await crud_duty_slot.update(session, db_obj=db_slot, obj_in=slot_in)
    return await _enrich_slot(session, updated)


@router.delete("/{slot_id}", status_code=204)
async def delete_duty_slot(
    slot_id: str,
    session: DBDep,
    _current_user: CurrentSuperuser,
) -> None:
    slot = await crud_duty_slot.get(session, slot_id, raise_404_error=True)
    await session.delete(slot)
    await session.commit()
