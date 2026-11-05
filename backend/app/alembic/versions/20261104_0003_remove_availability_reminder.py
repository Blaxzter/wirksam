"""Remove the availability reminder

The settings offered "Availability Reminder", but nothing has ever sent it.
Starting up only adds and updates notification types, so without this the row
would stay and the settings would keep offering a message that never comes. A
person's preferences for it go with the row (``ON DELETE CASCADE``), and nothing
in the inbox can refer to it, since no such message ever existed.

The downgrade adds nothing back: the older code seeds the type on startup, and
the preferences only said what to do with a message nobody got.

Revision ID: 20261104_0003
Revises: 20261104_0002
"""

import sqlalchemy as sa
from alembic import op

revision = "20261104_0003"
down_revision = "20261104_0002"
branch_labels = None
depends_on = None

REMOVE_TYPE = "DELETE FROM notification_types WHERE code = 'availability.reminder'"


def upgrade():
    op.execute(sa.text(REMOVE_TYPE))


def downgrade():
    pass
