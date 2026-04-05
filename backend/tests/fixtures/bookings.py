"""Booking fixtures for testing."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.duty_slot import DutySlot
from app.models.user import User


@pytest_asyncio.fixture
async def test_booking(
    db_session: AsyncSession, test_duty_slot: DutySlot, test_user: User
) -> Booking:
    """Create a test booking."""
    booking = Booking(
        duty_slot_id=test_duty_slot.id,
        user_id=test_user.id,
        status="confirmed",
        notes="I'll be there!",
    )
    db_session.add(booking)
    await db_session.flush()
    await db_session.refresh(booking)
    return booking
