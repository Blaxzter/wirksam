"""An event's look: its own colours and a logo

``events.primary_color``, ``events.secondary_color`` and ``events.base_color``
each name one of a fixed set of colours the frontend has tuned for contrast,
or hold an own colour as ``#rrggbb``, which the frontend lightens or darkens as
far as readability needs; NULL, which every existing event gets, keeps the
app's own. The secondary list is longer: it is only ever a fill under dark
text, so yellow and green work there. The base colour is the tone of the
background, cards and menu.
``events.logo_etag`` mirrors the logo's version so a list of events can build
the logo URLs without a join, and ``logo_width`` / ``logo_height`` its size, so
the sidebar knows before loading it whether it is a wordmark (shown alone) or
a mark (shown beside the event's name). The ``logo_dark_*`` columns do the same
for an optional second logo for dark mode, and ``logo_dark_tile`` says whether
dark mode puts the logo on a white tile; true for every existing event, since
most logos are drawn for a light page.

``event_logos`` holds the logos like ``user_avatars`` holds an avatar: a
storage key, never the bytes, one row per event and variant (``light`` or
``dark``). It gets the same ``queue_storage_deletion`` trigger as the other
file tables (``20261027_0001``), so a replaced logo, a removed one and a
deleted event all queue the old file for deletion.

Revision ID: 20261121_0001
Revises: 20261110_0001
Create Date: 2026-11-21 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "20261121_0001"
down_revision = "20261110_0001"
branch_labels = None
depends_on = None

PRIMARY_COLORS = ("red", "orange", "teal", "blue", "violet", "pink", "slate")
SECONDARY_COLORS = (
    "red",
    "orange",
    "yellow",
    "green",
    "teal",
    "blue",
    "violet",
    "pink",
    "slate",
)
BASE_COLORS = ("neutral", "primary", "blue", "teal", "green", "rose", "violet")


def _one_of(column: str, names: tuple[str, ...]) -> str:
    """One of the presets, or an own colour."""
    presets = ", ".join(f"'{c}'" for c in names)
    return f"{column} IN ({presets}) OR {column} ~ '^#[0-9a-f]{{6}}$'"


def upgrade():
    # ── Columns on events ──────────────────────────────────────────────────
    op.add_column("events", sa.Column("primary_color", sa.String(16), nullable=True))
    op.add_column("events", sa.Column("secondary_color", sa.String(16), nullable=True))
    op.add_column("events", sa.Column("base_color", sa.String(16), nullable=True))
    op.add_column("events", sa.Column("logo_etag", sa.String(64), nullable=True))
    op.add_column("events", sa.Column("logo_width", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("logo_height", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("logo_dark_etag", sa.String(64), nullable=True))
    op.add_column("events", sa.Column("logo_dark_width", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("logo_dark_height", sa.Integer(), nullable=True))
    op.add_column(
        "events",
        sa.Column(
            "logo_dark_tile", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_events_primary_color",
        "events",
        _one_of("primary_color", PRIMARY_COLORS),
    )
    op.create_check_constraint(
        "ck_events_secondary_color",
        "events",
        _one_of("secondary_color", SECONDARY_COLORS),
    )
    op.create_check_constraint(
        "ck_events_base_color",
        "events",
        _one_of("base_color", BASE_COLORS),
    )

    # ── event_logos ────────────────────────────────────────────────────────
    op.create_table(
        "event_logos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column(
            "content_type",
            sa.String(64),
            server_default="image/webp",
            nullable=False,
        ),
        sa.Column("etag", sa.String(64), nullable=False),
        sa.Column("variant", sa.String(8), server_default="light", nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "variant", name="uq_event_logos_event_variant"),
        sa.CheckConstraint("variant IN ('light', 'dark')", name="ck_event_logos_variant"),
    )
    op.create_index(op.f("ix_event_logos_id"), "event_logos", ["id"], unique=False)
    op.create_index(
        op.f("ix_event_logos_event_id"), "event_logos", ["event_id"], unique=False
    )
    op.create_index(
        op.f("ix_event_logos_storage_key"), "event_logos", ["storage_key"], unique=True
    )
    op.create_index(op.f("ix_event_logos_etag"), "event_logos", ["etag"], unique=False)
    op.execute(
        "CREATE TRIGGER event_logos_queue_storage_deletion "
        "AFTER DELETE OR UPDATE OF storage_key ON event_logos "
        "FOR EACH ROW EXECUTE FUNCTION queue_storage_deletion()"
    )


def downgrade():
    # Dropping the table fires no row trigger, so queue its files by hand.
    op.execute(
        "DELETE FROM stored_objects WHERE key IN (SELECT storage_key FROM event_logos)"
    )
    op.execute(
        "INSERT INTO storage_deletions (key) SELECT storage_key FROM event_logos"
    )
    op.execute("DROP TRIGGER event_logos_queue_storage_deletion ON event_logos")
    op.drop_table("event_logos")
    op.drop_constraint("ck_events_base_color", "events", type_="check")
    op.drop_constraint("ck_events_secondary_color", "events", type_="check")
    op.drop_constraint("ck_events_primary_color", "events", type_="check")
    op.drop_column("events", "logo_dark_tile")
    op.drop_column("events", "logo_dark_height")
    op.drop_column("events", "logo_dark_width")
    op.drop_column("events", "logo_dark_etag")
    op.drop_column("events", "logo_height")
    op.drop_column("events", "logo_width")
    op.drop_column("events", "logo_etag")
    op.drop_column("events", "base_color")
    op.drop_column("events", "secondary_color")
    op.drop_column("events", "primary_color")
