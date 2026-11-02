from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlmodel import col

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.shift_batch import shift_batch as crud_shift_batch
from app.crud.task import task as crud_task
from app.logic import clock, vouchers
from app.logic.permissions import (
    check_shift_history,
    require_task_manager,
    require_task_visible,
)
from app.models.booking import Booking
from app.models.shift import Shift
from app.schemas.shift_batch import ShiftBatchRead

router = APIRouter()


@router.get("/{task_id}/batches", response_model=list[ShiftBatchRead])
async def list_batches(
    task_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> list[ShiftBatchRead]:
    """List all shift batches for a task."""
    db_task = await crud_task.get(session, task_id, raise_404_error=True)
    await require_task_visible(current_user, session, db_task)
    batches = await crud_shift_batch.get_by_task(session, task_id=task_id)
    return [ShiftBatchRead.model_validate(b) for b in batches]


@router.delete("/{task_id}/batches/{batch_id}", status_code=204)
async def delete_batch(
    task_id: str,
    batch_id: str,
    session: DBDep,
    current_user: CurrentUser,
    cancellation_reason: str | None = Query(default=None),
) -> None:
    """Delete a shift batch and all its duty shifts (cascade).

    A person in charge may not delete a batch holding a booked shift that has
    started (``check_shift_history``); nothing is deleted then.
    """
    db_batch = await crud_shift_batch.get(session, batch_id, raise_404_error=True)
    if str(db_batch.task_id) != task_id:
        raise_problem(
            400, code="batch.wrong_task", detail="Batch does not belong to this task"
        )

    # Get task name for snapshot
    db_task = await crud_task.get(session, task_id, raise_404_error=True)
    access = await require_task_manager(current_user, session, db_task)

    shifts = list(
        (
            await session.execute(
                select(Shift).where(col(Shift.batch_id) == db_batch.id)
            )
        ).scalars()
    )
    slot_ids = [s.id for s in shifts]

    if access == "manager" and slot_ids:
        booked = set(
            (
                await session.execute(
                    select(col(Booking.shift_id))
                    .where(
                        col(Booking.shift_id).in_(slot_ids),
                        col(Booking.status) == "confirmed",
                    )
                    .distinct()
                )
            ).scalars()
        )
        now = clock.wall_clock_now()
        for shift in shifts:
            check_shift_history(
                access,
                before=shift,
                has_bookings=shift.id in booked,
                deleting=True,
                now=now,
            )

    # What the batch's worked shifts earned stays earned; then cancel the
    # confirmed bookings with a snapshot.
    await vouchers.settle_earnings(
        session, now=clock.wall_clock_now(), shift_ids=slot_ids
    )
    await crud_booking.cancel_bookings_for_shifts(
        session,
        slot_ids=slot_ids,
        task_name=db_task.name,
        cancellation_reason=cancellation_reason,
    )

    await session.delete(db_batch)
    await session.commit()
