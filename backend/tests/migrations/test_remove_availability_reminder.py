"""``20261104_0003_remove_availability_reminder`` takes the type out of the settings.

The test database never holds the row, because nothing seeds it there. So this
puts in what a production database has at upgrade time and runs the upgrade's SQL,
imported from the migration module.
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic.notifications.registry import ALL_NOTIFICATION_TYPES
from app.models.notification import NotificationSubscription, NotificationType
from app.models.user import User

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "alembic"
    / "versions"
    / "20261104_0003_remove_availability_reminder.py"
)


def _remove_type_sql() -> str:
    spec = importlib.util.spec_from_file_location("availability_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.REMOVE_TYPE


def test_the_registry_no_longer_seeds_it() -> None:
    """Otherwise the next start would put the row straight back."""
    assert "availability.reminder" not in {t.code for t in ALL_NOTIFICATION_TYPES}


@pytest.mark.asyncio
async def test_the_type_and_its_preferences_go_and_others_stay(
    db_session: AsyncSession, test_user: User
) -> None:
    retired = NotificationType(
        code="availability.reminder",
        name="Availability Reminder",
        category="availability",
        default_channels=["email", "push"],
    )
    kept = NotificationType(
        code="test.kept", name="Kept", category="test", default_channels=["email"]
    )
    db_session.add_all([retired, kept])
    await db_session.flush()
    db_session.add_all(
        [
            NotificationSubscription(
                user_id=test_user.id, notification_type_id=retired.id
            ),
            NotificationSubscription(
                user_id=test_user.id, notification_type_id=kept.id
            ),
        ]
    )
    await db_session.flush()
    retired_id, kept_id = retired.id, kept.id

    await db_session.execute(text(_remove_type_sql()))

    codes = await db_session.execute(
        select(col(NotificationType.code)).where(
            col(NotificationType.code).in_(["availability.reminder", "test.kept"])
        )
    )
    assert list(codes.scalars()) == ["test.kept"]

    async def _preferences(type_id: object) -> int:
        result = await db_session.execute(
            select(func.count())
            .select_from(NotificationSubscription)
            .where(col(NotificationSubscription.notification_type_id) == type_id)
        )
        return result.scalar_one()

    assert await _preferences(retired_id) == 0
    assert await _preferences(kept_id) == 1
