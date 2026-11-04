"""Earned vouchers are final: freeze them before a change would take them back

Until now what a volunteer earned was derived from the task's current rate and
its current shifts every time it was asked for. Lowering the rate, deleting a
worked shift or the task, or moving a shift into the future took vouchers
back, possibly below what was already spent at a stand, and raising the rate
paid more for shifts long over.

``voucher_earnings`` holds what one ended, worked booking earned. It is written
by ``app.logic.vouchers.settle_earnings`` just before any change that would
alter that derivation (rate changes, shift and task deletes and moves, the
event's shift dates, deleting the account that created a task), once per
booking (``booking_id`` is unique, the idempotency key). Bookings without a row
are still derived as before, so nothing needs backfilling.

``event_id`` and ``user_id`` are ON DELETE CASCADE. ``booking_id``, ``task_id``
and ``shift_id`` have no foreign key on purpose: a CASCADE would take earned
vouchers away with a deleted shift, task or booking, which is what this table
exists to prevent, and SET NULL next to ``event_id`` is the trap in
app/models/CLAUDE.md. Snapshots of the task and shift keep the row readable.

Revision ID: 20261102_0001
Revises: 20261030_0002
Create Date: 2026-11-02 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "20261102_0001"
down_revision = "20261030_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "voucher_earnings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("task_name", sa.String(), nullable=False),
        sa.Column("shift_id", sa.Uuid(), nullable=True),
        sa.Column("shift_title", sa.String(), nullable=False),
        sa.Column("shift_date", sa.Date(), nullable=False),
        sa.Column("shift_start_time", sa.Time(), nullable=True),
        sa.Column("shift_end_time", sa.Time(), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "amount >= 0", name="ck_voucher_earnings_amount_non_negative"
        ),
    )
    op.create_index("ix_voucher_earnings_id", "voucher_earnings", ["id"])
    op.create_index("ix_voucher_earnings_event_id", "voucher_earnings", ["event_id"])
    op.create_index("ix_voucher_earnings_user_id", "voucher_earnings", ["user_id"])
    op.create_index(
        "ix_voucher_earnings_booking_id",
        "voucher_earnings",
        ["booking_id"],
        unique=True,
    )
    op.create_index(
        "ix_voucher_earnings_event_id_user_id",
        "voucher_earnings",
        ["event_id", "user_id"],
    )


def downgrade():
    op.drop_index(
        "ix_voucher_earnings_event_id_user_id", table_name="voucher_earnings"
    )
    op.drop_index("ix_voucher_earnings_booking_id", table_name="voucher_earnings")
    op.drop_index("ix_voucher_earnings_user_id", table_name="voucher_earnings")
    op.drop_index("ix_voucher_earnings_event_id", table_name="voucher_earnings")
    op.drop_index("ix_voucher_earnings_id", table_name="voucher_earnings")
    op.drop_table("voucher_earnings")
