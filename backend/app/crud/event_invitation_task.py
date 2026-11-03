"""The tasks an event invitation asks its invitee to be in charge of.

Never commits; the request owns the transaction. Who may call what is decided
in the routes (event admins only, ``app/api/routes/tasks/managers.py``), and
the invite flow itself lives in ``app/logic/invitations.py``.

"Open" means neither revoked nor accepted; "valid" means open and not expired.
Links only ever hang off targeted invitations (``email`` set).
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from typing import Any, cast

from sqlalchemy import CursorResult, delete, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.errors import raise_problem
from app.crud.event_invitation import event_invitation as crud_invitation
from app.logic import clock
from app.models.event_invitation import EventInvitation
from app.models.event_invitation_task import EventInvitationTask
from app.models.task import Task
from app.models.user import User


def _open() -> list[Any]:
    """Neither revoked nor accepted; expired ones included."""
    return [
        col(EventInvitation.revoked_at).is_(None),
        col(EventInvitation.accepted_at).is_(None),
    ]


class CRUDEventInvitationTask:
    async def add(
        self,
        session: AsyncSession,
        *,
        invitation_id: uuid.UUID,
        task_id: uuid.UUID,
        added_by: User,
    ) -> EventInvitationTask:
        """Link one task to an invitation; a duplicate is ``409``.

        Inside a savepoint, so a link that a concurrent request added first
        fails this statement only, not the caller's transaction.
        """
        row = EventInvitationTask(
            invitation_id=invitation_id,
            task_id=task_id,
            added_by_id=added_by.id,
            added_by_name=added_by.name or added_by.email,
        )
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
        except IntegrityError:
            raise_problem(
                409,
                code="task.manager_already_invited",
                detail="That address is already invited to be in charge of this task",
            )
        return row

    async def is_linked(
        self,
        session: AsyncSession,
        *,
        invitation_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> bool:
        row = await session.execute(
            select(col(EventInvitationTask.id)).where(
                col(EventInvitationTask.invitation_id) == invitation_id,
                col(EventInvitationTask.task_id) == task_id,
            )
        )
        return row.first() is not None

    async def link_count(
        self, session: AsyncSession, *, invitation_id: uuid.UUID
    ) -> int:
        return int(
            await session.scalar(
                select(func.count(col(EventInvitationTask.id))).where(
                    col(EventInvitationTask.invitation_id) == invitation_id
                )
            )
            or 0
        )

    async def remove(
        self,
        session: AsyncSession,
        *,
        invitation: EventInvitation,
        task_id: uuid.UUID,
    ) -> bool:
        """Take one task off an invitation. False when it was not linked.

        An invitation created only for its tasks (``for_tasks_only``) is
        revoked when its last link goes: the person was only ever invited to
        run those. An invitation from the event settings stays valid.
        """
        result = cast(
            CursorResult[Any],
            await session.execute(
                delete(EventInvitationTask).where(
                    col(EventInvitationTask.invitation_id) == invitation.id,
                    col(EventInvitationTask.task_id) == task_id,
                )
            ),
        )
        await session.flush()
        if result.rowcount == 0:
            return False
        if (
            invitation.for_tasks_only
            and invitation.revoked_at is None
            and invitation.accepted_at is None
            and await self.link_count(session, invitation_id=invitation.id) == 0
        ):
            await crud_invitation.revoke(session, invitation=invitation)
        return True

    async def move_links(
        self,
        session: AsyncSession,
        *,
        from_id: uuid.UUID,
        to_id: uuid.UUID,
    ) -> None:
        """Move every link of one invitation onto another.

        A task both already name stays linked once; the duplicate goes.
        """
        already = select(col(EventInvitationTask.task_id)).where(
            col(EventInvitationTask.invitation_id) == to_id
        )
        await session.execute(
            update(EventInvitationTask)
            .where(
                col(EventInvitationTask.invitation_id) == from_id,
                col(EventInvitationTask.task_id).not_in(already),
            )
            .values(invitation_id=to_id)
            .execution_options(synchronize_session=False)
        )
        await session.execute(
            delete(EventInvitationTask).where(
                col(EventInvitationTask.invitation_id) == from_id
            )
        )
        await session.flush()

    async def tasks_for_invitations(
        self,
        session: AsyncSession,
        *,
        invitation_ids: Iterable[uuid.UUID],
    ) -> dict[uuid.UUID, list[Task]]:
        """``{invitation_id: [task, ...]}``, each list ordered by task name.

        Invitations without links are left out of the mapping.
        """
        ids = set(invitation_ids)
        if not ids:
            return {}
        rows = await session.execute(
            select(col(EventInvitationTask.invitation_id), Task)
            .join(Task, col(Task.id) == col(EventInvitationTask.task_id))
            .where(col(EventInvitationTask.invitation_id).in_(ids))
            .order_by(col(Task.name), col(Task.id))
        )
        out: dict[uuid.UUID, list[Task]] = defaultdict(list)
        for invitation_id, task in rows.all():
            out[invitation_id].append(task)
        return dict(out)

    async def open_invitations_for_task(
        self,
        session: AsyncSession,
        *,
        task_id: uuid.UUID,
    ) -> list[EventInvitation]:
        """Open invitations linked to this task, expired ones included, oldest first."""
        rows = await session.execute(
            select(EventInvitation)
            .join(
                EventInvitationTask,
                col(EventInvitationTask.invitation_id) == col(EventInvitation.id),
            )
            .where(col(EventInvitationTask.task_id) == task_id, *_open())
            .order_by(col(EventInvitation.created_at), col(EventInvitation.id))
        )
        return list(rows.scalars().all())

    async def open_for_address(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        email: str,
        include_expired: bool = False,
    ) -> list[EventInvitation]:
        """Open targeted invitations to ``email`` in this event, newest first.

        Valid ones only, unless ``include_expired``. Addresses are stored
        lowercased (``crud.event_invitation.create``), so the comparison is on
        the lowercased address and the index on ``(event_id, email)`` serves
        it.
        """
        where = [
            col(EventInvitation.event_id) == event_id,
            col(EventInvitation.email) == email.lower(),
            *_open(),
        ]
        if not include_expired:
            where.append(
                or_(
                    col(EventInvitation.expires_at).is_(None),
                    col(EventInvitation.expires_at) > clock.utc_now(),
                )
            )
        rows = await session.execute(
            select(EventInvitation)
            .where(*where)
            .order_by(col(EventInvitation.created_at).desc(), col(EventInvitation.id))
        )
        return list(rows.scalars().all())

    async def detach_task(self, session: AsyncSession, *, task_id: uuid.UUID) -> None:
        """Drop a task from every invitation, before it is deleted or moved.

        Every open ``for_tasks_only`` invitation whose only link is this task
        is revoked first, so its link answers "This invitation was withdrawn"
        rather than making someone a plain member of an event they were only
        asked to run one task in. Invitations from the event settings, and
        task invitations that still name other tasks, stay valid.
        """
        linked = select(col(EventInvitationTask.invitation_id)).where(
            col(EventInvitationTask.task_id) == task_id
        )
        other_link = exists().where(
            col(EventInvitationTask.invitation_id) == col(EventInvitation.id),
            col(EventInvitationTask.task_id) != task_id,
        )
        await session.execute(
            update(EventInvitation)
            .where(
                col(EventInvitation.id).in_(linked),
                col(EventInvitation.for_tasks_only).is_(True),
                *_open(),
                ~other_link,
            )
            .values(revoked_at=clock.utc_now())
            .execution_options(synchronize_session="fetch")
        )
        await session.execute(
            delete(EventInvitationTask).where(
                col(EventInvitationTask.task_id) == task_id
            )
        )
        await session.flush()


event_invitation_task = CRUDEventInvitationTask()
