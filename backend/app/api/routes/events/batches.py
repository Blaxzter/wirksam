from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlmodel import col

from app.api.deps import CurrentSuperuser, CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.event import event as crud_event
from app.crud.slot_batch import slot_batch as crud_slot_batch
from app.models.duty_slot import DutySlot
from app.schemas.slot_batch import SlotBatchRead

router = APIRouter()


@router.get("/{event_id}/batches", response_model=list[SlotBatchRead])
async def list_batches(
    event_id: str,
    session: DBDep,
    _current_user: CurrentUser,
) -> list[SlotBatchRead]:
    """List all slot batches for an event."""
    await crud_event.get(session, event_id, raise_404_error=True)
    batches = await crud_slot_batch.get_by_event(session, event_id=event_id)
    return [SlotBatchRead.model_validate(b) for b in batches]


@router.delete("/{event_id}/batches/{batch_id}", status_code=204)
async def delete_batch(
    event_id: str,
    batch_id: str,
    session: DBDep,
    _current_user: CurrentSuperuser,
    cancellation_reason: str | None = Query(default=None),
) -> None:
    """Delete a slot batch and all its duty slots (cascade)."""
    db_batch = await crud_slot_batch.get(session, batch_id, raise_404_error=True)
    if str(db_batch.event_id) != event_id:
        raise_problem(400, code="batch.wrong_event", detail="Batch does not belong to this event")

    # Get event name for snapshot
    db_event = await crud_event.get(session, event_id, raise_404_error=True)

    # Collect slot IDs in this batch
    stmt = select(col(DutySlot.id)).where(col(DutySlot.batch_id) == db_batch.id)
    result = await session.execute(stmt)
    slot_ids = list(result.scalars().all())

    # Cancel confirmed bookings with snapshot
    await crud_booking.cancel_bookings_for_slots(
        session,
        slot_ids=slot_ids,
        event_name=db_event.name,
        cancellation_reason=cancellation_reason,
    )

    await session.delete(db_batch)
    await session.commit()
