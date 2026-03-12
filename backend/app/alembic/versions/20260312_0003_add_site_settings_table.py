"""Add site_settings table

Revision ID: 20260312_0003
Revises: 20260312_0002
Create Date: 2026-03-12 23:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260312_0003"
down_revision = "20260312_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "site_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("approval_password", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_site_settings_id"), "site_settings", ["id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_site_settings_id"), table_name="site_settings")
    op.drop_table("site_settings")
