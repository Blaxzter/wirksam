"""add_picture_to_users

Revision ID: 20260311_0001
Revises: 20260310_0002
Create Date: 2026-03-11 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260311_0001"
down_revision = "20260310_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("picture", sa.String(), nullable=True))


def downgrade():
    op.drop_column("users", "picture")
