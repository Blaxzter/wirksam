import uuid

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentSuperuser, CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.duty_slot import duty_slot as crud_duty_slot
from app.crud.event import event as crud_event
from app.models.duty_slot import DutySlot
from app.schemas.booking import SlotBookingEntry
from app.schemas.duty_slot import (
    DutySlotCreate,
    DutySlotListResponse,
    DutySlotRead,
    DutySlotUpdate,
)

router = APIRouter(prefix="/duty-slots", tags=["duty-slots"])


async def _enrich_slot(
    session: AsyncSession,
    slot: DutySlot,
    user_id: uuid.UUID | None = None,
) -> DutySlotRead:
    """Add current_bookings count and is_booked_by_me to a DutySlotRead."""
    count = await crud_booking.get_confirmed_count(session, duty_slot_id=slot.id)
    read = DutySlotRead.model_validate(slot)
    read.current_bookings = count
    if user_id:
        my_booking = await crud_booking.get_by_slot_and_user(
            session, duty_slot_id=slot.id, user_id=user_id
        )
        read.is_booked_by_me = my_booking is not None and my_booking.status == "confirmed"
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
            raise_problem(
                403, code="event.not_published", detail="Event is not published"
            )

    items = await crud_duty_slot.get_multi_filtered(
        session,
        skip=skip,
        limit=limit,
        event_id=event_id,
        category=category,
        search=search,
    )
    enriched = [await _enrich_slot(session, s, user_id=current_user.id) for s in items]
    total = await crud_duty_slot.get_count_filtered(
        session, event_id=event_id, category=category, search=search
    )
    return DutySlotListResponse(items=enriched, total=total, skip=skip, limit=limit)


@router.get("/{slot_id}", response_model=DutySlotRead)
async def get_duty_slot(
    slot_id: str | None,
    session: DBDep,
    _current_user: CurrentUser,
) -> DutySlotRead:
    if slot_id is None:
        raise_problem(400, code="invalid_request", detail="slot_id is required")

    slot = await crud_duty_slot.get(session, slot_id, raise_404_error=True)
    return await _enrich_slot(session, slot, user_id=_current_user.id)


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
    cancellation_reason: str | None = Query(default=None),
) -> None:
    slot = await crud_duty_slot.get(session, slot_id, raise_404_error=True)

    # Get event name for snapshot
    db_event = await crud_event.get(session, str(slot.event_id), raise_404_error=True)

    # Cancel confirmed bookings with snapshot before deleting the slot
    await crud_booking.cancel_bookings_for_slots(
        session,
        slot_ids=[slot.id],
        event_name=db_event.name,
        cancellation_reason=cancellation_reason,
    )

    await session.delete(slot)
    await session.commit()


@router.get("/{slot_id}/bookings", response_model=list[SlotBookingEntry])
async def list_slot_bookings(
    slot_id: str,
    session: DBDep,
    _current_user: CurrentUser,
) -> list[SlotBookingEntry]:
    """List confirmed bookings for a slot with basic user info."""
    await crud_duty_slot.get(session, slot_id, raise_404_error=True)
    bookings = await crud_booking.get_multi_by_slot(
        session, duty_slot_id=slot_id, status="confirmed", with_user=True
    )
    return [
        SlotBookingEntry(
            id=b.id,
            user_id=b.user_id,
            user_name=b.user.name if b.user else None,
            user_email=b.user.email if b.user else None,
            user_picture=b.user.picture if b.user else None,
            notes=b.notes,
            created_at=b.created_at,
        )
        for b in bookings
    ]
