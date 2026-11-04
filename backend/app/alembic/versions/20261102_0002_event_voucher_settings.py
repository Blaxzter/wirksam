"""Event voucher rules: who may redeem without a code, who changes voucher shifts

Who may redeem without a code (by picking the person from the member list) was
set per task: ``tasks.is_voucher_desk`` marked a volunteer desk whose staff on
shift could, but only when the task also had a team, and organisers had to
understand both switches to get it right. It becomes one rule per event:

* ``events.voucher_manual_redeem``: ``on_shift`` (the default: besides the
  organisers and the point's people in charge, whoever is on a running shift
  at a point may pick a person there) or ``in_charge`` (only the organisers
  and the people in charge). Every existing event gets ``on_shift`` through
  the server default; nothing is released yet, so no organiser's expectations
  change. A CHECK keeps the column to those two values;
* ``events.managers_edit_voucher_shifts``: whether the people in charge of a
  task that earns vouchers may add, move, resize or delete its shifts. Off by
  default, because every extra shift earns vouchers and a person in charge
  could otherwise hand them out to friends. Organisers are never limited;
* ``tasks.is_voucher_desk`` goes. The downgrade adds it back switched off on
  every task, which is what a desk without its team meant anyway.

Revision ID: 20261102_0002
Revises: 20261102_0001
Create Date: 2026-11-02 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "20261102_0002"
down_revision = "20261102_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "events",
        sa.Column(
            "voucher_manual_redeem",
            sa.String(length=16),
            nullable=False,
            server_default="on_shift",
        ),
    )
    op.create_check_constraint(
        "ck_events_voucher_manual_redeem",
        "events",
        "voucher_manual_redeem IN ('on_shift', 'in_charge')",
    )
    op.add_column(
        "events",
        sa.Column(
            "managers_edit_voucher_shifts",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.drop_column("tasks", "is_voucher_desk")


def downgrade():
    op.add_column(
        "tasks",
        sa.Column(
            "is_voucher_desk",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.drop_column("events", "managers_edit_voucher_shifts")
    op.drop_constraint("ck_events_voucher_manual_redeem", "events", type_="check")
    op.drop_column("events", "voucher_manual_redeem")
