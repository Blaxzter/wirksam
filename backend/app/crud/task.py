import datetime as dt
import uuid
from typing import Any, Literal, cast

from sqlalchemy import CursorResult, and_, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlmodel import col

from app.crud.base import CRUDBase
from app.models.booking import Booking
from app.models.shift import Shift
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate

TaskSortField = Literal["name", "start_date", "end_date", "status", "created_at"]


class CRUDTask(CRUDBase[Task, TaskCreate, TaskUpdate]):
    def _apply_common_filters(
        self,
        query: Select[Any],
        *,
        search: str | None = None,
        status: str | None = None,
        created_by_id: str | None = None,
        booked_by_user_id: str | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        has_future_shifts: dt.date | dt.datetime | None = None,
        also_include_group_ids: list[uuid.UUID] | None = None,
        event_id: uuid.UUID | None = None,
        restrict_to_event_ids: list[uuid.UUID] | None = None,
        location_id: uuid.UUID | None = None,
        bookable_team_ids: list[uuid.UUID] | None = None,
        bookable_admin_event_ids: list[uuid.UUID] | None = None,
    ) -> Select[Any]:
        if restrict_to_event_ids is not None:
            # A hard AND, unlike also_include_group_ids which widens the status
            # filter. None means unrestricted; an empty list means nothing is
            # visible, and must not silently degrade to unrestricted.
            query = query.where(col(Task.event_id).in_(restrict_to_event_ids))
        else:
            # Unrestricted means the platform superadmin. Demo tasks are still
            # excluded - and the flag is read from the task rather than from
            # its event because ``tasks.event_id`` is ON DELETE SET NULL, so a
            # task can outlive its event and a NULL matches no ``IN`` list.
            query = query.where(col(Task.is_sandbox).is_(False))
        if event_id is not None:
            query = query.where(col(Task.event_id) == event_id)
        if bookable_team_ids is not None:
            # "Only tasks I can book": no team, a team the caller is approved
            # in, or an event they run (admins pass every team gate). Mirrors
            # app.logic.permissions.may_book_task for a whole list.
            query = query.where(
                or_(
                    col(Task.team_id).is_(None),
                    col(Task.team_id).in_(bookable_team_ids),
                    col(Task.event_id).in_(bookable_admin_event_ids or []),
                )
            )
        if location_id is not None:
            # The task itself, or any one of its shifts: a task held in the
            # foyer with one shift at the entrance shows up for both.
            query = query.where(
                or_(
                    col(Task.location_id) == location_id,
                    exists(
                        select(col(Shift.id)).where(
                            col(Shift.task_id) == col(Task.id),
                            col(Shift.location_id) == location_id,
                        )
                    ),
                )
            )
        if search:
            query = query.where(
                col(Task.name).ilike(f"%{search}%")
                | col(Task.description).ilike(f"%{search}%")
            )
        if status:
            status_filter = col(Task.status) == status
            if also_include_group_ids:
                status_filter = or_(
                    status_filter,
                    col(Task.event_id).in_(also_include_group_ids),
                )
            query = query.where(status_filter)
        if created_by_id:
            query = query.where(col(Task.created_by_id) == created_by_id)
        if booked_by_user_id:
            query = query.where(
                col(Task.id).in_(
                    select(col(Shift.task_id))
                    .join(Booking, col(Booking.shift_id) == col(Shift.id))
                    .where(
                        col(Booking.user_id) == booked_by_user_id,
                        col(Booking.status) == "confirmed",
                    )
                )
            )
        if date_from:
            query = query.where(col(Task.end_date) >= date_from)
        if date_to:
            query = query.where(col(Task.start_date) <= date_to)
        if has_future_shifts:
            # Only include tasks that have at least one bookable shift in the future
            booking_count_sq = (
                select(func.count())
                .select_from(Booking)
                .where(
                    col(Booking.shift_id) == col(Shift.id),
                    col(Booking.status) == "confirmed",
                )
                .correlate(Shift)
                .scalar_subquery()
            )
            today = (
                has_future_shifts.date()
                if isinstance(has_future_shifts, dt.datetime)
                else has_future_shifts
            )
            now_time = (
                has_future_shifts.time()
                if isinstance(has_future_shifts, dt.datetime)
                else None
            )

            # Shift is in the future if:
            #   date > today, OR
            #   date == today AND (start_time is NULL OR start_time >= now)
            future_condition = col(Shift.date) > today
            if now_time is not None:
                future_condition = or_(
                    col(Shift.date) > today,
                    and_(
                        col(Shift.date) == today,
                        or_(
                            col(Shift.start_time).is_(None),
                            col(Shift.start_time) >= now_time,
                        ),
                    ),
                )

            query = query.where(
                col(Task.id).in_(
                    select(col(Shift.task_id)).where(
                        future_condition,
                        col(Shift.max_bookings) > booking_count_sq,
                    )
                )
            )
        return query

    async def get_multi_filtered(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        status: str | None = None,
        created_by_id: str | None = None,
        booked_by_user_id: str | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        has_future_shifts: dt.date | None = None,
        sort_by: TaskSortField = "start_date",
        sort_dir: Literal["asc", "desc"] = "asc",
        also_include_group_ids: list[uuid.UUID] | None = None,
        event_id: uuid.UUID | None = None,
        restrict_to_event_ids: list[uuid.UUID] | None = None,
        location_id: uuid.UUID | None = None,
        bookable_team_ids: list[uuid.UUID] | None = None,
        bookable_admin_event_ids: list[uuid.UUID] | None = None,
    ) -> list[Task]:
        query = select(Task)
        query = self._apply_common_filters(
            query,
            search=search,
            status=status,
            created_by_id=created_by_id,
            booked_by_user_id=booked_by_user_id,
            date_from=date_from,
            date_to=date_to,
            has_future_shifts=has_future_shifts,
            also_include_group_ids=also_include_group_ids,
            event_id=event_id,
            restrict_to_event_ids=restrict_to_event_ids,
            location_id=location_id,
            bookable_team_ids=bookable_team_ids,
            bookable_admin_event_ids=bookable_admin_event_ids,
        )
        order_col = getattr(Task, sort_by)
        query = query.order_by(
            col(order_col).asc() if sort_dir == "asc" else col(order_col).desc()
        )
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_count_filtered(
        self,
        db: AsyncSession,
        *,
        search: str | None = None,
        status: str | None = None,
        created_by_id: str | None = None,
        booked_by_user_id: str | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        has_future_shifts: dt.date | None = None,
        also_include_group_ids: list[uuid.UUID] | None = None,
        event_id: uuid.UUID | None = None,
        restrict_to_event_ids: list[uuid.UUID] | None = None,
        location_id: uuid.UUID | None = None,
        bookable_team_ids: list[uuid.UUID] | None = None,
        bookable_admin_event_ids: list[uuid.UUID] | None = None,
    ) -> int:
        query = select(func.count()).select_from(Task)
        query = self._apply_common_filters(
            query,
            search=search,
            status=status,
            created_by_id=created_by_id,
            booked_by_user_id=booked_by_user_id,
            date_from=date_from,
            date_to=date_to,
            has_future_shifts=has_future_shifts,
            also_include_group_ids=also_include_group_ids,
            event_id=event_id,
            restrict_to_event_ids=restrict_to_event_ids,
            location_id=location_id,
            bookable_team_ids=bookable_team_ids,
            bookable_admin_event_ids=bookable_admin_event_ids,
        )
        result = await db.execute(query)
        return result.scalar_one()

    async def count_owned_by(self, db: AsyncSession, *, user_id: uuid.UUID) -> int:
        """Count tasks created by the given user."""
        result = await db.execute(
            select(func.count())
            .select_from(Task)
            .where(col(Task.created_by_id) == user_id)
        )
        return result.scalar_one()

    async def reassign_owner(
        self,
        db: AsyncSession,
        *,
        from_user_id: uuid.UUID,
        to_user_id: uuid.UUID,
    ) -> int:
        """Reassign all tasks created by one user to another. Returns row count."""
        result = cast(
            CursorResult[Any],
            await db.execute(
                update(Task)
                .where(col(Task.created_by_id) == from_user_id)
                .values(created_by_id=to_user_id)
            ),
        )
        return result.rowcount if result.rowcount > 0 else 0


task = CRUDTask(Task)
