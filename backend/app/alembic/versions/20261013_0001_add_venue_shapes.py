"""Drawn venue maps: blank canvases and shapes

Lets an organiser draw the venue map in the app instead of (or on top of)
uploading a picture (#185 phase 2).

``venue_plans`` gains ``canvas_width``/``canvas_height``, the logical size of a
plan that has no picture (existing rows get the 1600 x 1000 landscape default;
a plan with a picture keeps using the image size), and ``shapes_revision``, a
counter every successful shape batch bumps, used as cache key and as the
optimistic-concurrency token of the batch endpoint.

``venue_shapes`` holds the drawing: rects, polygons, paths and text labels with
points normalised to the plan size, a preset style token and an optional link to
a location. That link is ``ON DELETE SET NULL`` with a ``DEFERRABLE INITIALLY
DEFERRED`` check, like ``tasks.location_id``: an event delete cascades to both
the locations (SET NULL here) and the plans (CASCADE here) in one statement, and
an immediate check would re-validate a location the same statement removed.

Revision ID: 20261013_0001
Revises: 20261012_0001
Create Date: 2026-10-13 09:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261013_0001"
down_revision = "20261012_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "venue_plans",
        sa.Column("canvas_width", sa.Integer(), server_default="1600", nullable=False),
    )
    op.add_column(
        "venue_plans",
        sa.Column("canvas_height", sa.Integer(), server_default="1000", nullable=False),
    )
    op.add_column(
        "venue_plans",
        sa.Column("shapes_revision", sa.Integer(), server_default="0", nullable=False),
    )

    op.create_table(
        "venue_shapes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("style", sa.String(length=16), nullable=False),
        sa.Column("points", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("label_size", sa.String(length=8), server_default="md", nullable=False),
        sa.Column("label_x", sa.Float(), nullable=True),
        sa.Column("label_y", sa.Float(), nullable=True),
        sa.Column("stroke_width", sa.Float(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["venue_plans.id"],
            name="venue_shapes_plan_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name="venue_shapes_location_id_fkey",
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_venue_shapes_id"), "venue_shapes", ["id"], unique=False)
    op.create_index(
        op.f("ix_venue_shapes_plan_id"), "venue_shapes", ["plan_id"], unique=False
    )
    op.create_index(
        op.f("ix_venue_shapes_location_id"),
        "venue_shapes",
        ["location_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_venue_shapes_location_id"), table_name="venue_shapes")
    op.drop_index(op.f("ix_venue_shapes_plan_id"), table_name="venue_shapes")
    op.drop_index(op.f("ix_venue_shapes_id"), table_name="venue_shapes")
    op.drop_table("venue_shapes")

    op.drop_column("venue_plans", "shapes_revision")
    op.drop_column("venue_plans", "canvas_height")
    op.drop_column("venue_plans", "canvas_width")
