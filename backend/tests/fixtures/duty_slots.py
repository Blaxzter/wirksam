"""DutySlot fixtures for testing."""

from datetime import date, time

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.duty_slot import DutySlot
from app.models.event import Event


@pytest_asyncio.fixture
async def test_duty_slot(db_session: AsyncSession, test_event: Event) -> DutySlot:
    """Create a test duty slot."""
    slot = DutySlot(
        event_id=test_event.id,
        title="Einlasskontrolle",
        description="Einlass am Haupteingang",
        date=date(2026, 5, 24),
        start_time=time(8, 0),
        end_time=time(12, 0),
        location="Haupteingang",
        category="Sicherheit",
        max_bookings=2,
    )
    db_session.add(slot)
    await db_session.flush()
    await db_session.refresh(slot)
    return slot
