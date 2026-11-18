"""Who gets the last place on a shift when two ask at once.

Adding a confirmed booking counts the confirmed bookings and then inserts one;
two requests doing that at the same moment both see the free place. Every path
that adds a confirmed booking therefore takes :func:`lock_shifts` before it
counts.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def lock_shifts(session: AsyncSession, shift_ids: Iterable[uuid.UUID]) -> None:
    """Serialise the bookings of these shifts until commit.

    A transaction-scoped advisory lock per shift, as ``crud.voucher.lock_ledger``
    takes, rather than ``FOR UPDATE`` on the shift row: that would also block
    the ``FOR KEY SHARE`` every booking insert takes on its shift for the
    foreign key, and every edit of the shift. Under READ COMMITTED each count
    after the lock sees what the previous holder committed.

    The ids are locked once each and in sorted order, so two requests over
    overlapping shifts cannot deadlock; a path that needs several takes them in
    one call. Take it after any lock on a guest row or a membership, never
    before.
    """
    for shift_id in sorted(set(shift_ids)):
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"shift-capacity:{shift_id}"},
        )
