"""Add ON DELETE CASCADE to user-referencing FKs

Revision ID: 20260404_0001
Revises: 20260328_0001
Create Date: 2026-04-04 01:23:25.247870

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260404_0001"
down_revision = "20260328_0001"
branch_labels = None
depends_on = None

# (table, constraint_name, referenced_table, local_cols, remote_cols, ondelete)
_FK_CHANGES: list[tuple[str, str, str, list[str], list[str], str]] = [
    (
        "user_availability_dates",
        "user_availability_dates_availability_id_fkey",
        "user_availabilities",
        ["availability_id"],
        ["id"],
        "CASCADE",
    ),
    (
        "bookings",
        "bookings_user_id_fkey",
        "users",
        ["user_id"],
        ["id"],
        "CASCADE",
    ),
    (
        "user_availabilities",
        "user_availabilities_user_id_fkey",
        "users",
        ["user_id"],
        ["id"],
        "CASCADE",
    ),
    (
        "events",
        "events_created_by_id_fkey",
        "users",
        ["created_by_id"],
        ["id"],
        "CASCADE",
    ),
    (
        "event_groups",
        "event_groups_created_by_id_fkey",
        "users",
        ["created_by_id"],
        ["id"],
        "CASCADE",
    ),
    (
        "duty_slots",
        "duty_slots_event_id_fkey",
        "events",
        ["event_id"],
        ["id"],
        "CASCADE",
    ),
    (
        "duty_slots",
        "duty_slots_batch_id_fkey",
        "slot_batches",
        ["batch_id"],
        ["id"],
        "CASCADE",
    ),
    (
        "slot_batches",
        "slot_batches_event_id_fkey",
        "events",
        ["event_id"],
        ["id"],
        "CASCADE",
    ),
    (
        "events",
        "events_event_group_id_fkey",
        "event_groups",
        ["event_group_id"],
        ["id"],
        "SET NULL",
    ),
    (
        "user_availabilities",
        "user_availabilities_event_group_id_fkey",
        "event_groups",
        ["event_group_id"],
        ["id"],
        "CASCADE",
    ),
]


def upgrade():
    for table, constraint, ref_table, local_cols, remote_cols, ondelete in _FK_CHANGES:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(
            constraint, table, ref_table, local_cols, remote_cols, ondelete=ondelete
        )


def downgrade():
    for table, constraint, ref_table, local_cols, remote_cols, _ondelete in _FK_CHANGES:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(constraint, table, ref_table, local_cols, remote_cols)
