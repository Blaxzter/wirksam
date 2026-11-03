"""Invite people in charge by e-mail: task links on event invitations

An organiser who wants their neighbour to run the grill had to invite them to
the event, wait for them to accept, and then come back to the task. Now the
people-in-charge dialog takes an e-mail address, and the address gets an
ordinary targeted event invitation that also names the task:

* ``event_invitation_tasks`` links an invitation to the tasks it asks the
  invitee to run; on acceptance they are put in charge of every task still
  linked. Both foreign keys CASCADE, so a deleted task or invitation takes its
  links along; ``added_by_id`` has no foreign key, like
  ``task_managers.added_by_id``. No SET NULL anywhere, so the trap in
  app/models/CLAUDE.md cannot fire;
* ``event_invitations.for_tasks_only`` marks the invitations this flow
  created. Only those are revoked when their last task link goes; an
  invitation from the event settings just loses the link. Every existing row
  is a plain invitation, which the server default says;
* ``event_invitations.last_sent_at`` records when the last mail or
  notification for an invitation was queued, so adding a second task or
  "send again" mails at most once every ten minutes. Existing rows have no
  value, which reads as "may be sent".

Revision ID: 20261102_0003
Revises: 20261102_0002
Create Date: 2026-11-02 20:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "20261102_0003"
down_revision = "20261102_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "event_invitation_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("invitation_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("added_by_id", sa.Uuid(), nullable=True),
        sa.Column("added_by_name", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["invitation_id"], ["event_invitations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "invitation_id", "task_id", name="uq_event_invitation_task"
        ),
    )
    op.create_index("ix_event_invitation_tasks_id", "event_invitation_tasks", ["id"])
    op.create_index(
        "ix_event_invitation_tasks_invitation_id",
        "event_invitation_tasks",
        ["invitation_id"],
    )
    op.create_index(
        "ix_event_invitation_tasks_task_id", "event_invitation_tasks", ["task_id"]
    )
    op.add_column(
        "event_invitations",
        sa.Column(
            "for_tasks_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "event_invitations",
        sa.Column("last_sent_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_column("event_invitations", "last_sent_at")
    op.drop_column("event_invitations", "for_tasks_only")
    op.drop_index(
        "ix_event_invitation_tasks_task_id", table_name="event_invitation_tasks"
    )
    op.drop_index(
        "ix_event_invitation_tasks_invitation_id", table_name="event_invitation_tasks"
    )
    op.drop_index("ix_event_invitation_tasks_id", table_name="event_invitation_tasks")
    op.drop_table("event_invitation_tasks")
