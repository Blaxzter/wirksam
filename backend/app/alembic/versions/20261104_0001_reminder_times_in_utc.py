"""Store booking reminder times in UTC

``remind_at`` was the shift's wall-clock start minus the offset, but the poller
compares it with UTC. In Berlin that fired every reminder one hour late in winter
and two in summer, so "15 minutes before" arrived after the shift had begun.

New rows are written in UTC. This converts the existing ones, read in the zone the
shifts are read in. A reminder that is already due on the corrected clock goes out
on the poller's next cycle, or expires if it is more than an hour overdue, which is
what would have happened to it anyway.

Revision ID: 20261104_0001
Revises: 20261102_0003
"""

import sqlalchemy as sa
from alembic import op

from app.core.config import settings

revision = "20261104_0001"
down_revision = "20261102_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            "UPDATE booking_reminders "
            "SET remind_at = (remind_at AT TIME ZONE :zone) AT TIME ZONE 'UTC'"
        ).bindparams(zone=settings.EVENT_TIMEZONE)
    )


def downgrade():
    op.execute(
        sa.text(
            "UPDATE booking_reminders "
            "SET remind_at = (remind_at AT TIME ZONE 'UTC') AT TIME ZONE :zone"
        ).bindparams(zone=settings.EVENT_TIMEZONE)
    )
