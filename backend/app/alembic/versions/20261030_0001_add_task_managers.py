"""People in charge of a task: edit its details and shifts without being event admin

An event with twenty stands either made twenty people event admin, which also
lets them change the member list, or sent every "add a shift at the bar" through
the organisers. ``task_managers`` names the people who run one task. They may
edit its details and its shifts and see who is booked on it; status, team and
deletion stay with the event admins (``app/logic/permissions.py``).

Both foreign keys are ON DELETE CASCADE: deleting the task or the person takes
the row with it. ``added_by_id`` has no foreign key on purpose, like
``work_logs.created_by_id``: a CASCADE would revoke the grant when the admin who
made it deletes their account, and SET NULL is the trap in
app/models/CLAUDE.md. ``added_by_name`` keeps it attributable.

Revision ID: 20261030_0001
Revises: 20261027_0001
Create Date: 2026-10-30 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "20261030_0001"
down_revision = "20261027_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_managers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("added_by_id", sa.Uuid(), nullable=True),
        sa.Column("added_by_name", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "user_id", name="uq_task_manager_task_user"),
    )
    op.create_index("ix_task_managers_id", "task_managers", ["id"])
    op.create_index("ix_task_managers_task_id", "task_managers", ["task_id"])
    op.create_index("ix_task_managers_user_id", "task_managers", ["user_id"])


def downgrade():
    op.drop_index("ix_task_managers_user_id", table_name="task_managers")
    op.drop_index("ix_task_managers_task_id", table_name="task_managers")
    op.drop_index("ix_task_managers_id", table_name="task_managers")
    op.drop_table("task_managers")
