import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.base import CRUDBase
from app.models.shift_batch import ShiftBatch
from app.schemas.shift_batch import ShiftBatchCreate, ShiftBatchUpdate


class CRUDShiftBatch(CRUDBase[ShiftBatch, ShiftBatchCreate, ShiftBatchUpdate]):
    async def get_by_task(
        self,
        db: AsyncSession,
        *,
        task_id: str,
    ) -> list[ShiftBatch]:
        query = (
            select(ShiftBatch)
            .where(col(ShiftBatch.task_id) == task_id)
            .order_by(col(ShiftBatch.created_at).asc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def follow_task_rename(
        self,
        db: AsyncSession,
        *,
        task_id: uuid.UUID,
        old_name: str,
        new_name: str,
    ) -> None:
        """Rename the batches that carry the task's name as their label.

        The task page heads each series of shifts with its batch's label. A
        batch created with the task is labelled with the task's name, and so is
        one added later without a place or category; those follow a rename, or
        the first series keeps the old name with nothing to change it. A label
        that is a place or a category is not the task's name and stays.
        """
        batches = (
            await db.execute(
                select(ShiftBatch).where(
                    col(ShiftBatch.task_id) == task_id,
                    col(ShiftBatch.label) == old_name,
                )
            )
        ).scalars()
        for batch in batches:
            batch.label = new_name
            db.add(batch)


shift_batch = CRUDShiftBatch(ShiftBatch)
