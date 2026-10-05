"""Registration approval status on users

Backs ``REGISTRATION_MODE=approval``: a self-hosted deployment can put new
accounts in a queue that a superadmin works through. The status is its own
column rather than a reuse of ``is_active``, because ``is_active`` already
means "suspended by a moderator", and the retired queue that shared it left a
waiting account and a suspended one looking identical.

Every existing account is backfilled as ``approved`` through the server
default. They were all admitted under open signup, and anything else would
lock the whole user base out the moment an operator switches the mode on.

Revision ID: 20261005_0001
Revises: 20260824_0001
Create Date: 2026-10-05 14:49:02.480993

"""

import sqlalchemy as sa
from alembic import op

revision = "20261005_0001"
down_revision = "20260824_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "approval_status",
            sa.String(length=16),
            server_default="approved",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_users_approval_status"), "users", ["approval_status"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_users_approval_status"), table_name="users")
    op.drop_column("users", "approval_status")
