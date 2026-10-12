"""Locations as entities, and the venue map

Adds per-event ``locations`` and the venue map built on them (``venue_plans``,
their image bytes in ``venue_plan_images``, and ``venue_markers``), and points
``tasks``, ``shift_batches`` and ``shifts`` at a location through a new
nullable ``location_id``.

The existing ``location`` text columns stay, as a denormalised display string:
whenever ``location_id`` is set the application also writes the location's name
there, and a rename rewrites it. That keeps every read path (dashboard, CSV,
ICS, reminders, print) working off the text alone. ``location_id`` is
``ON DELETE SET NULL``, so deleting a location leaves the last name behind as
free text, which is the fallback the feature asks for. On ``tasks`` that FK's
check is ``DEFERRABLE INITIALLY DEFERRED``: tasks also point at events with
SET NULL, and without the deferral a user delete (cascading to their events
and on to the events' locations) would re-check ``tasks.location_id`` against
a location the same statement had already removed.

Backfill: one location per distinct trimmed, non-empty ``location`` string per
event, collected from tasks, batches and shifts (the latter two through their
task, since neither carries an ``event_id``). Matching is exact and
case-sensitive after trimming, in line with the unique constraint, and names
are cut to the column's 120 characters. The text columns are not rewritten.
Tasks whose event is gone (``event_id IS NULL``) keep their text only.
Sandbox rows are included like any other.

Revision ID: 20261012_0001
Revises: 20261005_0001
Create Date: 2026-10-12 19:51:26.019432

"""

import sqlalchemy as sa
from alembic import op

revision = "20261012_0001"
down_revision = "20261005_0001"
branch_labels = None
depends_on = None

# The tables that gain a ``location_id``. The FK names are the ones Postgres
# would pick itself, written out so the downgrade can drop them by name.
_REFERENCING_TABLES = ("tasks", "shift_batches", "shifts")

# Kept at module level so tests/migrations/test_location_backfill.py can import
# and run exactly what the upgrade runs. Every statement is idempotent.
BACKFILL_SQL: tuple[str, ...] = (
    """
    INSERT INTO locations (id, created_at, updated_at, event_id, name)
    SELECT gen_random_uuid(), (now() at time zone 'utc'), (now() at time zone 'utc'),
           s.event_id, s.name
    FROM (
        SELECT t.event_id, left(btrim(t.location), 120) AS name
          FROM tasks t
         WHERE t.event_id IS NOT NULL AND btrim(coalesce(t.location, '')) <> ''
        UNION
        SELECT t.event_id, left(btrim(b.location), 120)
          FROM shift_batches b JOIN tasks t ON t.id = b.task_id
         WHERE t.event_id IS NOT NULL AND btrim(coalesce(b.location, '')) <> ''
        UNION
        SELECT t.event_id, left(btrim(sh.location), 120)
          FROM shifts sh JOIN tasks t ON t.id = sh.task_id
         WHERE t.event_id IS NOT NULL AND btrim(coalesce(sh.location, '')) <> ''
    ) s
    ON CONFLICT ON CONSTRAINT uq_locations_event_name DO NOTHING
    """,
    """
    UPDATE tasks t SET location_id = l.id
      FROM locations l
     WHERE l.event_id = t.event_id AND l.name = left(btrim(t.location), 120)
    """,
    """
    UPDATE shift_batches b SET location_id = l.id
      FROM tasks t, locations l
     WHERE t.id = b.task_id AND l.event_id = t.event_id
       AND l.name = left(btrim(b.location), 120)
    """,
    """
    UPDATE shifts sh SET location_id = l.id
      FROM tasks t, locations l
     WHERE t.id = sh.task_id AND l.event_id = t.event_id
       AND l.name = left(btrim(sh.location), 120)
    """,
)


def upgrade():
    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("map_url", sa.String(length=2048), nullable=True),
        sa.Column("contact", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "name", name="uq_locations_event_name"),
    )
    op.create_index(op.f("ix_locations_id"), "locations", ["id"], unique=False)
    op.create_index(
        op.f("ix_locations_event_id"), "locations", ["event_id"], unique=False
    )

    op.create_table(
        "venue_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("image_etag", sa.String(length=64), nullable=True),
        sa.Column("image_width", sa.Integer(), nullable=True),
        sa.Column("image_height", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_venue_plans_id"), "venue_plans", ["id"], unique=False)
    op.create_index(
        op.f("ix_venue_plans_event_id"), "venue_plans", ["event_id"], unique=False
    )

    op.create_table(
        "venue_plan_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column(
            "content_type",
            sa.String(length=64),
            server_default="image/webp",
            nullable=False,
        ),
        sa.Column("etag", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["venue_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_venue_plan_images_id"), "venue_plan_images", ["id"], unique=False
    )
    # unique=True + index=True on the model renders as one unique index.
    op.create_index(
        op.f("ix_venue_plan_images_plan_id"),
        "venue_plan_images",
        ["plan_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_venue_plan_images_etag"), "venue_plan_images", ["etag"], unique=False
    )

    op.create_table(
        "venue_markers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["venue_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_id", "location_id", name="uq_venue_markers_plan_location"
        ),
    )
    op.create_index(op.f("ix_venue_markers_id"), "venue_markers", ["id"], unique=False)
    op.create_index(
        op.f("ix_venue_markers_plan_id"), "venue_markers", ["plan_id"], unique=False
    )
    op.create_index(
        op.f("ix_venue_markers_location_id"),
        "venue_markers",
        ["location_id"],
        unique=False,
    )

    for table in _REFERENCING_TABLES:
        op.add_column(table, sa.Column("location_id", sa.Uuid(), nullable=True))
        # tasks also points at events (SET NULL). Deferring its location check
        # keeps a user delete -> event CASCADE from re-checking location_id
        # against a location the same statement already removed. See the
        # comment on Task.location_id.
        deferred = (
            {"deferrable": True, "initially": "DEFERRED"} if table == "tasks" else {}
        )
        op.create_foreign_key(
            f"{table}_location_id_fkey",
            table,
            "locations",
            ["location_id"],
            ["id"],
            ondelete="SET NULL",
            **deferred,
        )
        op.create_index(
            op.f(f"ix_{table}_location_id"), table, ["location_id"], unique=False
        )

    for statement in BACKFILL_SQL:
        op.execute(statement)


def downgrade():
    for table in reversed(_REFERENCING_TABLES):
        op.drop_index(op.f(f"ix_{table}_location_id"), table_name=table)
        op.drop_constraint(f"{table}_location_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "location_id")

    op.drop_index(op.f("ix_venue_markers_location_id"), table_name="venue_markers")
    op.drop_index(op.f("ix_venue_markers_plan_id"), table_name="venue_markers")
    op.drop_index(op.f("ix_venue_markers_id"), table_name="venue_markers")
    op.drop_table("venue_markers")

    op.drop_index(op.f("ix_venue_plan_images_etag"), table_name="venue_plan_images")
    op.drop_index(op.f("ix_venue_plan_images_plan_id"), table_name="venue_plan_images")
    op.drop_index(op.f("ix_venue_plan_images_id"), table_name="venue_plan_images")
    op.drop_table("venue_plan_images")

    op.drop_index(op.f("ix_venue_plans_event_id"), table_name="venue_plans")
    op.drop_index(op.f("ix_venue_plans_id"), table_name="venue_plans")
    op.drop_table("venue_plans")

    op.drop_index(op.f("ix_locations_event_id"), table_name="locations")
    op.drop_index(op.f("ix_locations_id"), table_name="locations")
    op.drop_table("locations")
