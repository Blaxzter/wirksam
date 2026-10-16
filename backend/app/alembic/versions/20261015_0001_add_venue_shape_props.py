"""Decoration on venue maps: the ``prop`` shape kind

A prop is a one-point shape that draws a pre-made glyph (a tree, a bench, a
gazebo, ...) to help people find their way. It is never a place: it cannot be
linked to a location. ``venue_shapes`` gains three nullable columns that only
props use: ``prop`` (the glyph), ``rotation`` (degrees clockwise) and ``scale``
(a size factor). Every other kind keeps them NULL, so no backfill is needed.

Revision ID: 20261015_0001
Revises: 20261013_0001
Create Date: 2026-10-15 09:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "20261015_0001"
down_revision = "20261013_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "venue_shapes", sa.Column("prop", sa.String(length=16), nullable=True)
    )
    op.add_column("venue_shapes", sa.Column("rotation", sa.Float(), nullable=True))
    op.add_column("venue_shapes", sa.Column("scale", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("venue_shapes", "scale")
    op.drop_column("venue_shapes", "rotation")
    op.drop_column("venue_shapes", "prop")
