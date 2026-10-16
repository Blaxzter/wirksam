import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.base import CRUDBase
from app.models.work_log import WorkLog
from app.schemas.work_hours import WorkLogCreate, WorkLogUpdate


class CRUDWorkLog(CRUDBase[WorkLog, WorkLogCreate, WorkLogUpdate]):
    async def get_in_event(
        self,
        session: AsyncSession,
        *,
        work_log_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> WorkLog | None:
        """Fetch an entry only if it belongs to this event.

        Scoping the lookup by event is what stops an admin of one event from
        editing another event's entries by guessing an id.
        """
        result = await session.execute(
            select(WorkLog).where(
                col(WorkLog.id) == work_log_id,
                col(WorkLog.event_id) == event_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_event(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> list[WorkLog]:
        query = select(WorkLog).where(col(WorkLog.event_id) == event_id)
        if user_id is not None:
            query = query.where(col(WorkLog.user_id) == user_id)
        query = query.order_by(col(WorkLog.date).desc(), col(WorkLog.created_at).desc())
        result = await session.execute(query)
        return list(result.scalars().all())


work_log = CRUDWorkLog(WorkLog)
