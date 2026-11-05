"""A time zone per event

One setting, ``EVENT_TIMEZONE``, decided for the whole installation when a shift
starts and ends. An event somewhere else was off by the difference in everything
that follows from it: reminders, booking cut-offs, hours and vouchers.

Every existing event gets the installation's setting, so a self-hosted
installation keeps the zone its events have been read in all along. No reminder
moves, because the zone they were converted through is the same one. There is no
server default: the setting differs per installation, and the model fills the
column in. The downgrade drops the column, and the events go back to the setting.

Revision ID: 20261104_0002
Revises: 20261104_0001
"""

import sqlalchemy as sa
from alembic import op

from app.core.config import settings

revision = "20261104_0002"
down_revision = "20261104_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("events", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.execute(
        sa.text("UPDATE events SET timezone = :zone").bindparams(
            zone=settings.EVENT_TIMEZONE
        )
    )
    op.alter_column("events", "timezone", nullable=False)


def downgrade():
    op.drop_column("events", "timezone")
