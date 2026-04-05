"""Event fixtures for testing."""

from datetime import date

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.user import User


@pytest_asyncio.fixture
async def test_event(db_session: AsyncSession, test_user: User) -> Event:
    """Create a published test event."""
    event = Event(
        name="Pfingsten 2026",
        description="Überregionale Dienstliste Pfingsten",
        start_date=date(2026, 5, 24),
        end_date=date(2026, 5, 26),
        status="published",
        created_by_id=test_user.id,
    )
    db_session.add(event)
    await db_session.flush()
    await db_session.refresh(event)
    return event


@pytest_asyncio.fixture
async def test_draft_event(db_session: AsyncSession, test_user: User) -> Event:
    """Create a draft test event."""
    event = Event(
        name="Kirchentag 2026",
        description="Draft event",
        start_date=date(2026, 6, 10),
        end_date=date(2026, 6, 14),
        status="draft",
        created_by_id=test_user.id,
    )
    db_session.add(event)
    await db_session.flush()
    await db_session.refresh(event)
    return event
