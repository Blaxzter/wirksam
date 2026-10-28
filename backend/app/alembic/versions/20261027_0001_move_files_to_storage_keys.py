"""Uploaded files: rows hold a storage key, the bytes move to ``stored_objects``

The four file tables (``user_avatars``, ``venue_plan_images``,
``venue_template_images``, ``event_team_documents``) lose their ``data``
column and get a ``storage_key``. The bytes move into ``stored_objects``,
which is what ``STORAGE_BACKEND=postgres`` (the default) reads; with
``STORAGE_BACKEND=s3`` the copy script moves them on into the bucket.

Each of those tables gets an ``AFTER DELETE OR UPDATE OF storage_key``
trigger. It deletes the ``stored_objects`` row of the old key and queues the
key in ``storage_deletions``, so a file goes however its row goes, including
an ``ON DELETE CASCADE`` that no Python code sees. ``app/logic/storage_gc.py``
works the queue.

The downgrade only works while every file is still in Postgres: a file that
was moved to a bucket has no bytes here to put back.

Revision ID: 20261027_0001
Revises: 20261026_0001
Create Date: 2026-10-27 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "20261027_0001"
down_revision = "20261026_0001"
branch_labels = None
depends_on = None

# (table, key prefix) — the prefixes are app.core.storage.FileKind
FILE_TABLES = [
    ("user_avatars", "avatars"),
    ("venue_plan_images", "venue-plans"),
    ("venue_template_images", "venue-templates"),
    ("event_team_documents", "team-documents"),
]


def upgrade():
    op.create_table(
        "stored_objects",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "storage_deletions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
    )

    for table, prefix in FILE_TABLES:
        op.add_column(table, sa.Column("storage_key", sa.String(255), nullable=True))
        op.execute(
            f"UPDATE {table} SET storage_key = "
            f"'{prefix}/' || replace(gen_random_uuid()::text, '-', '')"
        )
        op.execute(
            f"INSERT INTO stored_objects (key, data, content_type, created_at) "
            f"SELECT storage_key, data, content_type, created_at FROM {table}"
        )
        op.alter_column(table, "storage_key", nullable=False)
        op.create_index(
            f"ix_{table}_storage_key", table, ["storage_key"], unique=True
        )
        op.drop_column(table, "data")

    op.execute(
        """
        CREATE FUNCTION queue_storage_deletion() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' OR NEW.storage_key IS DISTINCT FROM OLD.storage_key
            THEN
                DELETE FROM stored_objects WHERE key = OLD.storage_key;
                INSERT INTO storage_deletions (key) VALUES (OLD.storage_key);
            END IF;
            RETURN NULL;
        END
        $$
        """
    )
    for table, _ in FILE_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_queue_storage_deletion "
            f"AFTER DELETE OR UPDATE OF storage_key ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION queue_storage_deletion()"
        )


def downgrade():
    for table, _ in FILE_TABLES:
        op.execute(f"DROP TRIGGER {table}_queue_storage_deletion ON {table}")
    op.execute("DROP FUNCTION queue_storage_deletion()")

    for table, _ in FILE_TABLES:
        missing = (
            op.get_bind()
            .execute(
                sa.text(
                    f"SELECT count(*) FROM {table} t "
                    f"LEFT JOIN stored_objects o ON o.key = t.storage_key "
                    f"WHERE o.key IS NULL"
                )
            )
            .scalar_one()
        )
        if missing:
            raise RuntimeError(
                f"{missing} files of {table} are not in Postgres (moved to a "
                "bucket?); copy them back into stored_objects before downgrading"
            )
        op.add_column(table, sa.Column("data", sa.LargeBinary(), nullable=True))
        op.execute(
            f"UPDATE {table} t SET data = o.data "
            f"FROM stored_objects o WHERE o.key = t.storage_key"
        )
        op.alter_column(table, "data", nullable=False)
        op.drop_index(f"ix_{table}_storage_key", table_name=table)
        op.drop_column(table, "storage_key")

    op.drop_table("storage_deletions")
    op.drop_table("stored_objects")
