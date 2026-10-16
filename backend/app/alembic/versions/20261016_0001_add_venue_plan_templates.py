"""Venue plan templates: reusable drawings saved on the user

An organiser can save a plan's drawing as a template and start new plans from
it in any event. ``venue_templates`` holds the canvas size, the denormalised
image fields and the shapes as a JSONB snapshot (no markers, no location
links); ``venue_template_images`` holds the picture bytes, like
``venue_plan_images``. Both go with the user (``ON DELETE CASCADE``), so
account deletion and the sandbox purge take them along.

Revision ID: 20261016_0001
Revises: 20261015_0001
Create Date: 2026-10-16 09:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261016_0001"
down_revision = "20261015_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "venue_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("canvas_width", sa.Integer(), nullable=False),
        sa.Column("canvas_height", sa.Integer(), nullable=False),
        sa.Column("image_etag", sa.String(length=64), nullable=True),
        sa.Column("image_width", sa.Integer(), nullable=True),
        sa.Column("image_height", sa.Integer(), nullable=True),
        sa.Column(
            "shapes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_venue_templates_id"), "venue_templates", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_venue_templates_user_id"),
        "venue_templates",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "venue_template_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column(
            "content_type",
            sa.String(length=64),
            server_default="image/webp",
            nullable=False,
        ),
        sa.Column("etag", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["template_id"], ["venue_templates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_venue_template_images_id"),
        "venue_template_images",
        ["id"],
        unique=False,
    )
    # unique=True + index=True on the model renders as one unique index.
    op.create_index(
        op.f("ix_venue_template_images_template_id"),
        "venue_template_images",
        ["template_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_venue_template_images_etag"),
        "venue_template_images",
        ["etag"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_venue_template_images_etag"), table_name="venue_template_images"
    )
    op.drop_index(
        op.f("ix_venue_template_images_template_id"),
        table_name="venue_template_images",
    )
    op.drop_index(
        op.f("ix_venue_template_images_id"), table_name="venue_template_images"
    )
    op.drop_table("venue_template_images")

    op.drop_index(op.f("ix_venue_templates_user_id"), table_name="venue_templates")
    op.drop_index(op.f("ix_venue_templates_id"), table_name="venue_templates")
    op.drop_table("venue_templates")
