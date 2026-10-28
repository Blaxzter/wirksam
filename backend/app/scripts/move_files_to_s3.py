"""Move uploaded files from Postgres into the S3 bucket.

For an install switching to ``STORAGE_BACKEND=s3`` (see docs/STORAGE.md).
Switch first, then run this: until a file is moved, ``S3Storage`` still reads
it from ``stored_objects``, so nothing is missing in between.

    python -m app.scripts.move_files_to_s3
    python -m app.scripts.move_files_to_s3 --sweep-orphans

Each batch is uploaded and only then deleted from Postgres, in one
transaction, so the script can be stopped and run again at any point: a batch
that did not commit is uploaded again (an overwrite with the same bytes), and
a committed one is not in ``stored_objects`` any more.

``--sweep-orphans`` afterwards deletes bucket objects that no row points at
and that are older than a day: files of a request that failed after the
upload, which no trigger ever saw.
"""

import argparse
import asyncio
import datetime as dt

import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col

from app.core.db import async_session
from app.core.logger import get_logger
from app.core.storage import S3Storage, get_storage
from app.models.event_team import EventTeamDocument
from app.models.stored_object import StorageDeletion, StoredObject
from app.models.user_avatar import UserAvatar
from app.models.venue_plan import VenuePlanImage
from app.models.venue_template import VenueTemplateImage

logger = get_logger(__name__)

# Rows per transaction. Each holds up to a few MB of bytes in memory.
BATCH = 50
ORPHAN_MIN_AGE = dt.timedelta(days=1)

_KEY_COLUMNS = [
    col(UserAvatar.storage_key),
    col(VenuePlanImage.storage_key),
    col(VenueTemplateImage.storage_key),
    col(EventTeamDocument.storage_key),
    col(StorageDeletion.key),
]


async def move_files(
    storage: S3Storage,
    *,
    sessions: async_sessionmaker[AsyncSession] = async_session,
    batch: int = BATCH,
) -> int:
    """Upload every ``stored_objects`` row and delete it. Returns how many."""
    moved = 0
    while True:
        async with sessions.begin() as db:
            rows = list(
                (
                    await db.execute(
                        select(StoredObject)
                        .order_by(col(StoredObject.key))
                        .limit(batch)
                        .with_for_update(skip_locked=True)
                    )
                ).scalars()
            )
            if not rows:
                return moved
            for row in rows:
                await storage.put(db, row.key, bytes(row.data), row.content_type)
            await db.execute(
                delete(StoredObject).where(
                    col(StoredObject.key).in_([row.key for row in rows])
                )
            )
        moved += len(rows)
        logger.info("moved files to the bucket", extra={"total": moved})


async def sweep_orphans(
    storage: S3Storage,
    *,
    sessions: async_sessionmaker[AsyncSession] = async_session,
    now: dt.datetime | None = None,
) -> int:
    """Delete bucket objects no row refers to, older than a day. Returns how many."""
    cutoff = (now or dt.datetime.now(dt.UTC)) - ORPHAN_MIN_AGE
    async with sessions() as db:
        referenced: set[str] = set()
        for column in _KEY_COLUMNS:
            referenced.update((await db.execute(sa.select(column))).scalars())
        candidates = [
            key
            for key in await storage.list_keys(older_than=cutoff)
            if key not in referenced
        ]
        await storage.delete(db, candidates)
        await db.commit()
    if candidates:
        logger.info("deleted orphaned files", extra={"count": len(candidates)})
    return len(candidates)


async def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Move uploaded files from Postgres into the S3 bucket."
    )
    parser.add_argument(
        "--sweep-orphans",
        action="store_true",
        help="also delete bucket objects that no row points at",
    )
    args = parser.parse_args(argv)
    storage = get_storage()
    if not isinstance(storage, S3Storage):
        raise SystemExit("Set STORAGE_BACKEND=s3 (and the S3_* settings) first.")
    moved = await move_files(storage)
    print(f"Moved {moved} files to bucket {storage.bucket}.")
    if args.sweep_orphans:
        swept = await sweep_orphans(storage)
        print(f"Deleted {swept} orphaned files.")


if __name__ == "__main__":  # pragma: no cover - CLI entry point; the logic it
    # calls is covered by tests/scripts/test_move_files_to_s3.py
    asyncio.run(main())
