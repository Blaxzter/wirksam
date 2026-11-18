import datetime as dt
import secrets
import uuid
from collections.abc import Iterable, Sequence
from typing import Literal

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.shared_list import (
    AskMode,
    EndsMode,
    SharedList,
    SharedListExcludedShift,
    SharedListTask,
    ShowNames,
)
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User

#: No i, l, o, I, O, 0 or 1: a link is sometimes read aloud or typed off a
#: poster. Also no ".", which keeps ``/l/<code>`` from looking like a file to
#: ``vite preview``'s SPA fallback.
CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
#: 55 symbols, twelve of them: about 69 bits, enough against a scan of every
#: list once there are thousands of them.
CODE_LENGTH = 12
_CODE_ATTEMPTS = 5

#: Row locks :meth:`CRUDSharedList.get_by_code` can take: ``key_share`` for a
#: sign-up, which a pause or an end (:meth:`CRUDSharedList.get_for_update`)
#: then waits for.
CodeLock = Literal["key_share"]


def generate_code() -> str:
    """A fresh random list code. Unique only once stored (``ix_shared_lists_code``)."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def _is_code_collision(exc: IntegrityError) -> bool:
    return "ix_shared_lists_code" in str(exc.orig)


class CRUDSharedList:
    """Shared lists and the tasks and shifts they offer.

    Never commits; the request owns the transaction. Who may call what is
    decided by the shared-list gates in ``app.logic.permissions``.
    """

    async def create(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        created_by: User,
        title: str,
        intro: str | None,
        share_note: str | None,
        ask_email: AskMode,
        ask_phone: AskMode,
        show_names: ShowNames,
        max_per_person: int | None,
        ends_mode: EndsMode,
        ends_on: dt.date | None,
    ) -> SharedList:
        """Insert a live list under a fresh code, retrying a taken one.

        Its tasks and excluded shifts follow with :meth:`set_tasks` and
        :meth:`set_excluded`, in that order.
        """
        for _ in range(_CODE_ATTEMPTS):
            candidate = SharedList(
                event_id=event_id,
                code=generate_code(),
                title=title,
                intro=intro,
                share_note=share_note,
                ask_email=ask_email,
                ask_phone=ask_phone,
                show_names=show_names,
                max_per_person=max_per_person,
                ends_mode=ends_mode,
                ends_on=ends_on,
                created_by_id=created_by.id,
                created_by_name=created_by.name or created_by.email,
            )
            try:
                async with session.begin_nested():
                    session.add(candidate)
                    await session.flush()
            except IntegrityError as exc:
                if not _is_code_collision(exc):
                    raise
                continue
            return candidate
        msg = "Could not find a free shared list code"
        raise RuntimeError(msg)

    async def rotate_code(
        self,
        session: AsyncSession,
        *,
        shared_list: SharedList,
        now: dt.datetime,
    ) -> SharedList:
        """Give the list a fresh code; the old link stops working at once.

        ``now`` is naive UTC (``clock.utc_now()``), stored as ``rotated_at``.
        """
        # Flushed first: rolling back a failed attempt expires what changed
        # inside it, and the caller's own unflushed changes must not be among
        # them.
        await session.flush()
        for _ in range(_CODE_ATTEMPTS):
            try:
                async with session.begin_nested():
                    shared_list.code = generate_code()
                    shared_list.rotated_at = now
                    await session.flush()
            except IntegrityError as exc:
                if not _is_code_collision(exc):
                    raise
                continue
            await session.refresh(shared_list)
            return shared_list
        msg = "Could not find a free shared list code"
        raise RuntimeError(msg)

    async def get(
        self, session: AsyncSession, *, shared_list_id: uuid.UUID
    ) -> SharedList | None:
        result = await session.execute(
            select(SharedList).where(col(SharedList.id) == shared_list_id)
        )
        return result.scalar_one_or_none()

    async def get_for_update(
        self, session: AsyncSession, *, shared_list_id: uuid.UUID
    ) -> SharedList | None:
        """The list, locked ``FOR UPDATE`` until commit.

        For every change to the list itself (pause, resume, end, rotate, edit):
        it waits for the sign-ups in flight, which hold the row ``FOR KEY
        SHARE``, and once it has committed no sign-up that read the old state
        can complete.
        """
        result = await session.execute(
            select(SharedList)
            .where(col(SharedList.id) == shared_list_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_by_code(
        self,
        session: AsyncSession,
        *,
        code: str,
        lock: CodeLock | None = None,
    ) -> SharedList | None:
        """The list behind a public link, optionally locked until commit.

        ``key_share`` is for a sign-up: it conflicts with :meth:`get_for_update`,
        so a pause waits for the sign-ups in flight, but not with the
        ``view_count`` increment of a page view, so a crowd opening the link
        never queues behind them.
        """
        query = select(SharedList).where(col(SharedList.code) == code)
        if lock == "key_share":
            query = query.with_for_update(read=True, key_share=True)
            query = query.execution_options(populate_existing=True)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def set_tasks(
        self,
        session: AsyncSession,
        *,
        shared_list_id: uuid.UUID,
        task_ids: Sequence[uuid.UUID],
    ) -> None:
        """Make ``task_ids`` the list's tasks, in this order.

        Exclusions of shifts whose task is no longer on the list go with it, so
        adding the task back later offers all its shifts again.
        """
        await session.execute(
            delete(SharedListTask).where(
                col(SharedListTask.shared_list_id) == shared_list_id
            )
        )
        session.add_all(
            SharedListTask(shared_list_id=shared_list_id, task_id=task_id, position=i)
            for i, task_id in enumerate(dict.fromkeys(task_ids))
        )
        await session.flush()
        listed = select(col(SharedListTask.task_id)).where(
            col(SharedListTask.shared_list_id) == shared_list_id
        )
        await session.execute(
            delete(SharedListExcludedShift).where(
                col(SharedListExcludedShift.shared_list_id) == shared_list_id,
                col(SharedListExcludedShift.shift_id).in_(
                    select(col(Shift.id)).where(col(Shift.task_id).not_in(listed))
                ),
            )
        )

    async def set_excluded(
        self,
        session: AsyncSession,
        *,
        shared_list_id: uuid.UUID,
        shift_ids: Iterable[uuid.UUID],
    ) -> list[uuid.UUID]:
        """Make ``shift_ids`` the shifts the list leaves out; returns those kept.

        Only shifts of the list's tasks are kept (call :meth:`set_tasks` first).
        Unknown ids and shifts of other tasks are dropped without a word, as
        the client may still hold the selection of a task it just removed.
        """
        await session.execute(
            delete(SharedListExcludedShift).where(
                col(SharedListExcludedShift.shared_list_id) == shared_list_id
            )
        )
        wanted = set(shift_ids)
        if not wanted:
            return []
        result = await session.execute(
            select(col(Shift.id))
            .join(SharedListTask, col(SharedListTask.task_id) == col(Shift.task_id))
            .where(
                col(SharedListTask.shared_list_id) == shared_list_id,
                col(Shift.id).in_(wanted),
            )
            .order_by(col(Shift.id))
        )
        kept = list(result.scalars().all())
        session.add_all(
            SharedListExcludedShift(shared_list_id=shared_list_id, shift_id=shift_id)
            for shift_id in kept
        )
        await session.flush()
        return kept

    async def task_ids(
        self, session: AsyncSession, *, shared_list_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Every task linked to the list, in its order, wherever the task is now."""
        result = await session.execute(
            select(col(SharedListTask.task_id))
            .where(col(SharedListTask.shared_list_id) == shared_list_id)
            .order_by(col(SharedListTask.position), col(SharedListTask.task_id))
        )
        return list(result.scalars().all())

    async def current_task_ids(
        self, session: AsyncSession, *, shared_list: SharedList
    ) -> list[uuid.UUID]:
        """The linked tasks that are still in the list's event, in order.

        What decides who may manage the list. A task that moved to another
        event is detached (:meth:`detach_task_from_lists`); this is the defence
        should a link survive anyway.
        """
        result = await session.execute(
            select(col(SharedListTask.task_id))
            .join(Task, col(Task.id) == col(SharedListTask.task_id))
            .where(
                col(SharedListTask.shared_list_id) == shared_list.id,
                col(Task.event_id) == shared_list.event_id,
            )
            .order_by(col(SharedListTask.position), col(SharedListTask.task_id))
        )
        return list(result.scalars().all())

    async def excluded_ids(
        self, session: AsyncSession, *, shared_list_id: uuid.UUID
    ) -> list[uuid.UUID]:
        result = await session.execute(
            select(col(SharedListExcludedShift.shift_id))
            .where(col(SharedListExcludedShift.shared_list_id) == shared_list_id)
            .order_by(col(SharedListExcludedShift.shift_id))
        )
        return list(result.scalars().all())

    async def detach_task_from_lists(
        self, session: AsyncSession, *, task_id: uuid.UUID
    ) -> None:
        """Take a task off every list, e.g. when it moves to another event.

        Its shifts' exclusions go too. Bookings made through a list stay.
        """
        await session.execute(
            delete(SharedListExcludedShift).where(
                col(SharedListExcludedShift.shift_id).in_(
                    select(col(Shift.id)).where(col(Shift.task_id) == task_id)
                )
            )
        )
        await session.execute(
            delete(SharedListTask).where(col(SharedListTask.task_id) == task_id)
        )

    async def shift_ends_on(
        self, session: AsyncSession, *, event_id: uuid.UUID, delta: dt.timedelta
    ) -> None:
        """Move the closing day of the event's lists along with its shifts.

        For ``POST /events/{id}/shift-dates``, whose ``delta`` is whole days.
        """
        await session.execute(
            update(SharedList)
            .where(
                col(SharedList.event_id) == event_id,
                col(SharedList.ends_on).is_not(None),
            )
            .values(ends_on=col(SharedList.ends_on) + delta.days)
        )


shared_list = CRUDSharedList()
