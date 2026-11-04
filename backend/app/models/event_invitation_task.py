import uuid

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import Base


class EventInvitationTask(Base, table=True):
    """A task an event invitation asks the invitee to be in charge of.

    An organiser can type the address of someone who is not in the event yet
    into a task's people-in-charge dialog. That person gets an ordinary
    targeted event invitation, and one row here per task it asks them to run.
    On acceptance they become a member and are put in charge of every task
    still linked (``POST /invitations/{token}/accept``). Links only ever hang
    off targeted invitations (``email`` set); the app enforces that, since a
    CHECK cannot look across tables.

    Both foreign keys CASCADE: a deleted task or invitation takes its links
    along. Before a task is deleted or moved to another event,
    ``crud.event_invitation_task.detach_task`` revokes the invitations that
    existed only for it, so their link answers "withdrawn" instead of
    quietly making someone a plain member.

    No ORM relationships, for the reason ``TaskManager`` has none: an ORM
    delete of the parent would try to NULL a NOT NULL column. The unit of work
    therefore cannot order the inserts either, so flush the invitation before
    adding a link (``crud.event_invitation.create`` flushes). There is no
    SET NULL anywhere in this table, so the trap in ``app/models/CLAUDE.md``
    cannot fire, and ``added_by_id`` has no foreign key, like
    ``TaskManager.added_by_id``.
    """

    __tablename__ = "event_invitation_tasks"  # type: ignore[assignment]

    __table_args__ = (
        sa.UniqueConstraint(
            "invitation_id", "task_id", name="uq_event_invitation_task"
        ),
    )

    invitation_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("event_invitations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    task_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    # No foreign key, like TaskManager.added_by_id: who asked is kept for
    # display, and must not take the link away when that organiser deletes
    # their account (their invitations go with them anyway, by CASCADE).
    added_by_id: uuid.UUID | None = Field(
        default=None, sa_column=sa.Column(sa.Uuid, nullable=True)
    )
    added_by_name: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
