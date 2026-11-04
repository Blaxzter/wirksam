import uuid

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import Base


class TaskManager(Base, table=True):
    """A person in charge of one task ("Verantwortliche").

    They may edit the task's details and its shifts, and see the contact
    details of the people booked on it; status, team and deletion stay with
    the event admins. Who may do what is decided in
    ``app.logic.permissions.task_access``, which also requires the person to
    still be a member of the task's event, so a row left behind grants nothing.

    No ORM relationship from ``Task`` or ``User``: without ``passive_deletes``
    deleting a task through the ORM would try to NULL ``task_id``, which is
    NOT NULL. Both CASCADEs live in the database only, like
    ``event_team_members``. For the same reason the unit of work cannot order
    inserts against ``users``: flush new users before adding rows here.
    """

    __tablename__ = "task_managers"  # type: ignore[assignment]

    __table_args__ = (
        sa.UniqueConstraint("task_id", "user_id", name="uq_task_manager_task_user"),
    )

    task_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    # Deliberately no foreign key, like WorkLog.created_by_id: a CASCADE would
    # take the grant away when the admin who made it deletes their account,
    # and SET NULL is the trap described in app/models/CLAUDE.md. The name is
    # kept for display.
    added_by_id: uuid.UUID | None = Field(
        default=None, sa_column=sa.Column(sa.Uuid, nullable=True)
    )
    added_by_name: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
