"""Take email off the unfilled-shift alert for everyone who never chose it

Nothing ever scheduled this alert, so nobody has received it. Now that the poller
runs it, email would be new mail to real people, one per unfilled shift, and its
default became push only.

A new default alone would miss the organisers most likely to read the alert. Saving
any switch on the settings page writes a row for every type with the values on
screen, so anyone who has ever changed a preference holds a row saying "email: on"
for a message they have never seen. That row says nothing about what they want, so
this turns it off. It also catches the rare person who really chose email for it;
they lose the mail and keep the alert in their inbox, and can switch it back on.

The downgrade leaves the rows alone: it can't tell which ones this changed.

Revision ID: 20261104_0004
Revises: 20261104_0003
"""

import sqlalchemy as sa
from alembic import op

revision = "20261104_0004"
down_revision = "20261104_0003"
branch_labels = None
depends_on = None

EMAIL_OFF = """
UPDATE notification_subscriptions
SET email_enabled = false
WHERE email_enabled
  AND notification_type_id IN (
    SELECT id FROM notification_types WHERE code = 'shift.starting_soon_unfilled'
  )
"""


def upgrade():
    op.execute(sa.text(EMAIL_OFF))


def downgrade():
    pass
