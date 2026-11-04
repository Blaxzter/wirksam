"""``20261104_0004_unfilled_shift_alert_no_email`` stops the mail for stored rows.

Saving the settings page writes a row for every type, so a new default alone would
still mail everyone who has ever changed a preference. This runs the upgrade's SQL,
imported from the migration module, over the rows a production database holds.
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic.notifications.seeder import seed_notification_types
from app.models.notification import NotificationSubscription, NotificationType
from app.models.user import User

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "alembic"
    / "versions"
    / "20261104_0004_unfilled_shift_alert_no_email.py"
)


def _email_off_sql() -> str:
    spec = importlib.util.spec_from_file_location("unfilled_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.EMAIL_OFF


@pytest.mark.asyncio
async def test_email_goes_off_for_this_alert_only(
    db_session: AsyncSession, test_user: User
) -> None:
    await seed_notification_types(db_session)
    rows = await db_session.execute(
        select(col(NotificationType.code), col(NotificationType.id))
    )
    types = {row.code: row.id for row in rows.all()}
    alert = NotificationSubscription(
        user_id=test_user.id,
        notification_type_id=types["shift.starting_soon_unfilled"],
        email_enabled=True,
        push_enabled=True,
    )
    other = NotificationSubscription(
        user_id=test_user.id,
        notification_type_id=types["booking.confirmed"],
        email_enabled=True,
        push_enabled=True,
    )
    db_session.add_all([alert, other])
    await db_session.flush()

    await db_session.execute(text(_email_off_sql()))
    await db_session.refresh(alert)
    await db_session.refresh(other)

    assert alert.email_enabled is False
    assert alert.push_enabled is True
    assert other.email_enabled is True
