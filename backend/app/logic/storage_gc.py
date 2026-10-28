"""Deleting the files whose rows are gone.

The four file tables carry triggers (migration ``20261027_0001``) that, when a
row is deleted or its ``storage_key`` replaced, do two things in the deleting
transaction: delete the ``stored_objects`` row of that key, and queue the key
in ``storage_deletions``. That covers every way a row can go — an ORM delete,
a bulk ``DELETE``, an ``ON DELETE CASCADE`` from a user, an event or a team,
the sandbox purge — without any of those places knowing about files.

With the Postgres backend the bytes are therefore already gone at commit, and
the queue only has to be emptied. With S3 the object is deleted here, after
the commit, by ``drain``. Two things run it:

* ``run_storage_gc``, a loop started in the app lifespan, every
  ``STORAGE_GC_INTERVAL_SECONDS``;
* ``app.core.storage.drain_after_commit(db)``, which the CRUD calls when it
  deletes or replaces a file, so the loop wakes as soon as that transaction
  has committed. A team document is meant to go when its request is
  decided, not a minute later.

A failed S3 delete raises, the queue rows stay, and the next run retries.
Several workers can drain at once: ``FOR UPDATE SKIP LOCKED`` hands each
of them different rows.
"""

import asyncio

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.core.db import async_session
from app.core.logger import get_logger
from app.core.storage import gc_wake_event, get_storage
from app.models.stored_object import StorageDeletion

logger = get_logger(__name__)

_BATCH = 500


async def drain(db: AsyncSession, *, limit: int = _BATCH) -> int:
    """Delete up to ``limit`` queued objects. Returns how many. Does not commit."""
    rows = (
        await db.execute(
            select(col(StorageDeletion.id), col(StorageDeletion.key))
            .order_by(col(StorageDeletion.id))
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
    if not rows:
        return 0
    keys = sorted({key for _, key in rows})
    await get_storage().delete(db, keys)
    await db.execute(
        delete(StorageDeletion).where(col(StorageDeletion.id).in_([i for i, _ in rows]))
    )
    return len(rows)


async def drain_all() -> int:
    """Empty the queue, one committed batch at a time. Returns how many."""
    total = 0
    while True:
        async with async_session.begin() as db:
            done = await drain(db)
        total += done
        if done < _BATCH:
            return total


async def run_storage_gc() -> None:
    """Drain the queue forever; started from the app lifespan."""
    wake = gc_wake_event()
    while True:
        try:
            await asyncio.wait_for(
                wake.wait(), timeout=settings.STORAGE_GC_INTERVAL_SECONDS
            )
        except TimeoutError:
            pass
        wake.clear()
        try:
            done = await drain_all()
            if done:
                logger.info("storage objects deleted", extra={"count": done})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("storage cleanup failed; retrying on the next run")
