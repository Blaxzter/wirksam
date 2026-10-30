"""Volunteer vouchers: earn them per shift, redeem them at a stand without paper

Many events give volunteers food and drink vouchers, for example two per
shift, counted out by hand at a desk with no record of who already got theirs.
The app knows who worked which shift, so it can work out the balance and let a
stand take vouchers in the app.

What a volunteer has earned is never stored: it is derived from their
confirmed bookings on shifts that have ended and the task's
``vouchers_per_shift``, like worked hours. This migration adds:

* three task columns: ``vouchers_per_shift`` (0 = none), ``is_voucher_point``
  (vouchers can be redeemed here) and ``is_voucher_desk`` (staff on shift may
  also redeem without a code);
* ``voucher_entries``, the stored half of a balance: redemptions and the
  corrections event admins make;
* ``voucher_passes``, the two-minute, single-use codes a volunteer shows.

``event_id`` and ``user_id`` are ON DELETE CASCADE in both tables. ``task_id``,
``actor_id`` and ``pass_id`` have no foreign key on purpose: a CASCADE would
delete debits with a deleted point task or redeemer, which refunds them, and
SET NULL next to ``event_id`` is the trap in app/models/CLAUDE.md. Name
snapshots keep the rows readable instead.

Revision ID: 20261030_0002
Revises: 20261030_0001
Create Date: 2026-10-30 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "20261030_0002"
down_revision = "20261030_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tasks",
        sa.Column(
            "vouchers_per_shift", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "is_voucher_point",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "is_voucher_desk",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_check_constraint(
        "ck_tasks_vouchers_per_shift_non_negative",
        "tasks",
        "vouchers_per_shift >= 0",
    )

    op.create_table(
        "voucher_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("task_name", sa.String(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_name", sa.String(), nullable=True),
        sa.Column("pass_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "kind IN ('redemption', 'adjustment')", name="ck_voucher_entries_kind"
        ),
        sa.CheckConstraint("amount <> 0", name="ck_voucher_entries_amount_nonzero"),
        sa.CheckConstraint(
            "kind <> 'redemption' OR amount < 0",
            name="ck_voucher_entries_redemption_negative",
        ),
    )
    op.create_index("ix_voucher_entries_id", "voucher_entries", ["id"])
    op.create_index("ix_voucher_entries_event_id", "voucher_entries", ["event_id"])
    op.create_index("ix_voucher_entries_user_id", "voucher_entries", ["user_id"])
    op.create_index(
        "ix_voucher_entries_pass_id", "voucher_entries", ["pass_id"], unique=True
    )
    op.create_index(
        "ix_voucher_entries_request_id",
        "voucher_entries",
        ["request_id"],
        unique=True,
    )
    op.create_index(
        "ix_voucher_entries_event_id_user_id",
        "voucher_entries",
        ["event_id", "user_id"],
    )
    op.create_index(
        "ix_voucher_entries_event_id_task_id",
        "voucher_entries",
        ["event_id", "task_id"],
    )

    op.create_table(
        "voucher_passes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=6), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_voucher_passes_code"),
    )
    op.create_index("ix_voucher_passes_id", "voucher_passes", ["id"])
    op.create_index("ix_voucher_passes_event_id", "voucher_passes", ["event_id"])
    op.create_index("ix_voucher_passes_user_id", "voucher_passes", ["user_id"])
    op.create_index(
        "ix_voucher_passes_event_id_user_id",
        "voucher_passes",
        ["event_id", "user_id"],
    )


def downgrade():
    op.drop_index("ix_voucher_passes_event_id_user_id", table_name="voucher_passes")
    op.drop_index("ix_voucher_passes_user_id", table_name="voucher_passes")
    op.drop_index("ix_voucher_passes_event_id", table_name="voucher_passes")
    op.drop_index("ix_voucher_passes_id", table_name="voucher_passes")
    op.drop_table("voucher_passes")

    op.drop_index("ix_voucher_entries_event_id_task_id", table_name="voucher_entries")
    op.drop_index("ix_voucher_entries_event_id_user_id", table_name="voucher_entries")
    op.drop_index("ix_voucher_entries_request_id", table_name="voucher_entries")
    op.drop_index("ix_voucher_entries_pass_id", table_name="voucher_entries")
    op.drop_index("ix_voucher_entries_user_id", table_name="voucher_entries")
    op.drop_index("ix_voucher_entries_event_id", table_name="voucher_entries")
    op.drop_index("ix_voucher_entries_id", table_name="voucher_entries")
    op.drop_table("voucher_entries")

    op.drop_constraint(
        "ck_tasks_vouchers_per_shift_non_negative", "tasks", type_="check"
    )
    op.drop_column("tasks", "is_voucher_desk")
    op.drop_column("tasks", "is_voucher_point")
    op.drop_column("tasks", "vouchers_per_shift")
