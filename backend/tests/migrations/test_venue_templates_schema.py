"""The schema ``20261016_0001_add_venue_plan_templates`` creates.

The test database is built by running the migrations, so this reads the
catalogue of that database. What matters is that templates go with their
owner: both foreign keys must be ``ON DELETE CASCADE``, or an account delete
(or the sandbox purge, which deletes guests last) would fail or strand rows.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_FK_ACTIONS = text(
    """
    SELECT conrelid::regclass::text AS tbl,
           confrelid::regclass::text AS ref,
           confdeltype::text AS confdeltype
    FROM pg_constraint
    WHERE contype = 'f'
      AND conrelid::regclass::text IN ('venue_templates', 'venue_template_images')
    """
)


@pytest.mark.asyncio
async def test_template_foreign_keys_cascade(db_session: AsyncSession) -> None:
    rows = (await db_session.execute(_FK_ACTIONS)).all()
    actions = {(r.tbl, r.ref): r.confdeltype for r in rows}
    assert actions == {
        ("venue_templates", "users"): "c",
        ("venue_template_images", "venue_templates"): "c",
    }


@pytest.mark.asyncio
async def test_one_image_per_template(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'ix_venue_template_images_template_id'"
        )
    )
    assert "UNIQUE" in result.scalar_one()
