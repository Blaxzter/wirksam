"""Work logs: hours an event admin credits to a volunteer by hand

Shift hours are derived from bookings on every read and need no table. This
one holds only the manual entries — work no shift describes.

``created_by_id`` has no foreign key on purpose. CASCADE would delete a
volunteer's hours together with the admin who entered them, and SET NULL on a
user FK in a table that also points at events breaks user deletion (see
``app/models/CLAUDE.md``). ``created_by_name`` keeps the entry attributable once
that account is gone.

Revision ID: 20261016_0002
Revises: 20261016_0001
Create Date: 2026-10-13 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "20261016_0002"
down_revision = "20261016_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "work_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_name", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_logs_id", "work_logs", ["id"])
    op.create_index("ix_work_logs_event_id", "work_logs", ["event_id"])
    op.create_index("ix_work_logs_user_id", "work_logs", ["user_id"])
    op.create_index(
        "ix_work_logs_event_id_user_id", "work_logs", ["event_id", "user_id"]
    )


def downgrade():
    op.drop_index("ix_work_logs_event_id_user_id", table_name="work_logs")
    op.drop_index("ix_work_logs_user_id", table_name="work_logs")
    op.drop_index("ix_work_logs_event_id", table_name="work_logs")
    op.drop_index("ix_work_logs_id", table_name="work_logs")
    op.drop_table("work_logs")
