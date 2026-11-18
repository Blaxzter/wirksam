"""The reads behind the shared-list management views of one event.

A fixed number of queries per request, however many lists, tasks or shifts the
event has: which tasks each list links, which shifts it leaves out, every shift
of the event's published tasks with its confirmed bookings, and how many people
signed up through each list. What that means on the event's clock is worked out
in ``app.logic.shared_lists.overview``.

Who may read what is decided by the shared-list gates in ``app.logic.permissions``
before any of this runs.
"""

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlmodel import col

from app.crud.search import like_pattern
from app.logic.shared_lists.offer import confirmed_sql, starts_at_sql
from app.models.booking import Booking
from app.models.event_team import EventTeam
from app.models.shared_list import SharedList, SharedListExcludedShift, SharedListTask
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User


@dataclass(frozen=True, slots=True)
class ListedTask:
    """A task linked to a list, with where and what the task is now."""

    shared_list_id: uuid.UUID
    task_id: uuid.UUID
    name: str
    #: None once the task's event was deleted; another event once it moved.
    event_id: uuid.UUID | None
    status: str
    team_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class ShiftFill:
    """A shift and how many confirmed bookings it has."""

    id: uuid.UUID
    task_id: uuid.UUID
    date: dt.date
    start_time: dt.time | None
    end_time: dt.time | None
    max_bookings: int
    confirmed: int

    @property
    def free(self) -> int:
        """Places left. Never negative: ``max_bookings`` can be lowered below
        the bookings a shift already has."""
        return max(0, self.max_bookings - self.confirmed)


@dataclass(frozen=True, slots=True)
class SignupCounts:
    """Confirmed bookings made through one list, and those of guests."""

    signups: int
    guests: int


#: The columns of a :class:`ShiftFill`, in order.
_FillSelect = Select[
    uuid.UUID, uuid.UUID, dt.date, dt.time | None, dt.time | None, int, int
]


def _fill_select() -> _FillSelect:
    return (
        select(
            col(Shift.id),
            col(Shift.task_id),
            col(Shift.date),
            col(Shift.start_time),
            col(Shift.end_time),
            col(Shift.max_bookings),
            confirmed_sql(),
        )
        .join(Task, col(Task.id) == col(Shift.task_id))
        .order_by(
            col(Shift.date), col(Shift.start_time).asc().nulls_first(), col(Shift.id)
        )
    )


def _lists_of(event_id: uuid.UUID) -> Select[uuid.UUID]:
    return select(col(SharedList.id)).where(col(SharedList.event_id) == event_id)


class CRUDSharedListOverview:
    """Reads only; the request owns the transaction."""

    async def lists(
        self, session: AsyncSession, *, event_id: uuid.UUID
    ) -> list[SharedList]:
        result = await session.execute(
            select(SharedList)
            .where(col(SharedList.event_id) == event_id)
            .order_by(col(SharedList.id))
        )
        return list(result.scalars().all())

    async def count_lists(self, session: AsyncSession, *, event_id: uuid.UUID) -> int:
        """Every list of the event, ended ones included."""
        result = await session.execute(
            select(func.count())
            .select_from(SharedList)
            .where(col(SharedList.event_id) == event_id)
        )
        return result.scalar_one()

    async def listed_tasks(
        self, session: AsyncSession, *, event_id: uuid.UUID
    ) -> dict[uuid.UUID, list[ListedTask]]:
        """``{list_id: [task, ...]}`` for the event's lists, each in its order."""
        result = await session.execute(
            select(
                col(SharedListTask.shared_list_id),
                col(SharedListTask.task_id),
                col(Task.name),
                col(Task.event_id),
                col(Task.status),
                col(Task.team_id),
            )
            .join(Task, col(Task.id) == col(SharedListTask.task_id))
            .where(col(SharedListTask.shared_list_id).in_(_lists_of(event_id)))
            .order_by(
                col(SharedListTask.shared_list_id),
                col(SharedListTask.position),
                col(SharedListTask.task_id),
            )
        )
        out: dict[uuid.UUID, list[ListedTask]] = defaultdict(list)
        for list_id, task_id, name, task_event_id, status, team_id in result.all():
            out[list_id].append(
                ListedTask(
                    shared_list_id=list_id,
                    task_id=task_id,
                    name=name,
                    event_id=task_event_id,
                    status=status,
                    team_id=team_id,
                )
            )
        return dict(out)

    async def excluded(
        self, session: AsyncSession, *, event_id: uuid.UUID
    ) -> dict[uuid.UUID, frozenset[uuid.UUID]]:
        """``{list_id: shift ids}`` the event's lists leave out."""
        result = await session.execute(
            select(
                col(SharedListExcludedShift.shared_list_id),
                col(SharedListExcludedShift.shift_id),
            ).where(
                col(SharedListExcludedShift.shared_list_id).in_(_lists_of(event_id))
            )
        )
        out: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        for list_id, shift_id in result.all():
            out[list_id].add(shift_id)
        return {list_id: frozenset(ids) for list_id, ids in out.items()}

    async def published_tasks(
        self, session: AsyncSession, *, event_id: uuid.UUID
    ) -> list[Task]:
        result = await session.execute(
            select(Task).where(
                col(Task.event_id) == event_id, col(Task.status) == "published"
            )
        )
        return list(result.scalars().all())

    async def event_shifts(
        self, session: AsyncSession, *, event_id: uuid.UUID
    ) -> list[ShiftFill]:
        """Every shift of the event's published tasks, started or not, by start."""
        result = await session.execute(
            _fill_select().where(
                col(Task.event_id) == event_id, col(Task.status) == "published"
            )
        )
        return [ShiftFill(*row) for row in result.all()]

    async def task_shifts(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        task_ids: Collection[uuid.UUID],
    ) -> list[ShiftFill]:
        """Every shift of those of ``task_ids`` that are in the event, by start."""
        result = await session.execute(
            _fill_select().where(
                col(Task.event_id) == event_id, col(Task.id).in_(task_ids)
            )
        )
        return [ShiftFill(*row) for row in result.all()]

    async def signup_counts(
        self, session: AsyncSession, *, event_id: uuid.UUID
    ) -> dict[uuid.UUID, SignupCounts]:
        """``{list_id: counts}`` of confirmed bookings made through each list.

        Only on tasks still in the event, as its table of sign-ups lists them
        (``signups_query``): a task moved away took its bookings out of view.
        """
        result = await session.execute(
            select(
                col(Booking.shared_list_id),
                func.count(),
                func.count().filter(col(User.is_list_guest)),
            )
            .join(User, col(User.id) == col(Booking.user_id))
            .join(Shift, col(Shift.id) == col(Booking.shift_id))
            .join(Task, col(Task.id) == col(Shift.task_id))
            .where(
                col(Booking.status) == "confirmed",
                col(Booking.shared_list_id).in_(_lists_of(event_id)),
                col(Task.event_id) == event_id,
            )
            .group_by(col(Booking.shared_list_id))
        )
        return {
            list_id: SignupCounts(signups=signups, guests=guests)
            for list_id, signups, guests in result.all()
            if list_id is not None
        }

    async def team_names(
        self, session: AsyncSession, *, team_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        if not team_ids:
            return {}
        result = await session.execute(
            select(col(EventTeam.id), col(EventTeam.name)).where(
                col(EventTeam.id).in_(team_ids)
            )
        )
        return dict(result.all())

    def _candidate_filter(
        self,
        *,
        event_id: uuid.UUID,
        managed_task_ids: frozenset[uuid.UUID] | None,
        now_wall: dt.datetime,
    ) -> list[ColumnElement[bool]]:
        """A published task of the event with a shift that has not started,
        among ``managed_task_ids`` unless that is None (an event admin)."""
        ahead = exists().where(
            col(Shift.task_id) == col(Task.id), starts_at_sql() > now_wall
        )
        conditions = [
            col(Task.event_id) == event_id,
            col(Task.status) == "published",
            ahead,
        ]
        if managed_task_ids is not None:
            conditions.append(col(Task.id).in_(managed_task_ids))
        return conditions

    async def candidates(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        managed_task_ids: frozenset[uuid.UUID] | None,
        now_wall: dt.datetime,
        q: str | None,
        skip: int,
        limit: int,
    ) -> tuple[list[Task], int]:
        """A page of the tasks the caller may put on a list, by name, and how
        many there are.

        ``managed_task_ids`` is None for an event admin, who may use every task;
        an empty set means none. Team tasks, which no list can offer, are
        included only when searching, so the wizard can say why they are
        missing.
        """
        conditions = self._candidate_filter(
            event_id=event_id, managed_task_ids=managed_task_ids, now_wall=now_wall
        )
        if q:
            pattern = like_pattern(q)
            conditions.append(
                or_(col(Task.name).ilike(pattern), col(Task.location).ilike(pattern))
            )
        else:
            conditions.append(col(Task.team_id).is_(None))
        total = await session.execute(
            select(func.count()).select_from(Task).where(*conditions)
        )
        page = await session.execute(
            select(Task)
            .where(*conditions)
            .order_by(col(Task.name), col(Task.id))
            .offset(skip)
            .limit(limit)
        )
        return list(page.scalars().all()), total.scalar_one()

    async def team_task_names(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        managed_task_ids: frozenset[uuid.UUID] | None,
        now_wall: dt.datetime,
    ) -> list[str]:
        """The names of the team tasks :meth:`candidates` leaves out without a
        search, by name."""
        result = await session.execute(
            select(col(Task.name))
            .where(
                *self._candidate_filter(
                    event_id=event_id,
                    managed_task_ids=managed_task_ids,
                    now_wall=now_wall,
                ),
                col(Task.team_id).is_not(None),
            )
            .order_by(col(Task.name), col(Task.id))
        )
        return list(result.scalars().all())


shared_list_overview = CRUDSharedListOverview()
