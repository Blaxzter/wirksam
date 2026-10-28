"""The schema ``20261027_0001_move_files_to_storage_keys`` creates.

What matters is that every file table carries the trigger that queues a file
when its row goes: without it a deleted avatar or team document would stay in
the bucket forever, and nothing else would notice.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FILE_TABLES = {
    "user_avatars",
    "venue_plan_images",
    "venue_template_images",
    "event_team_documents",
}


@pytest.mark.asyncio
async def test_every_file_table_queues_deleted_files(db_session: AsyncSession) -> None:
    rows = await db_session.execute(
        text(
            "SELECT tgrelid::regclass::text AS tbl FROM pg_trigger "
            "WHERE tgname LIKE '%_queue_storage_deletion' AND NOT tgisinternal"
        )
    )
    assert set(rows.scalars()) == FILE_TABLES


@pytest.mark.asyncio
async def test_no_file_table_keeps_bytes(db_session: AsyncSession) -> None:
    rows = await db_session.execute(
        text(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "AND column_name = 'data' AND data_type = 'bytea'"
        )
    )
    assert set(rows.scalars()) == {"stored_objects"}
