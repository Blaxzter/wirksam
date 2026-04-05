"""Unit tests for DutySlot CRUD operations."""

from datetime import date, time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.duty_slot import duty_slot as crud_duty_slot
from app.models.duty_slot import DutySlot
from app.models.event import Event
from app.schemas.duty_slot import DutySlotCreate, DutySlotUpdate


@pytest.mark.asyncio
class TestCRUDDutySlot:
    """Test suite for DutySlot CRUD operations."""

    async def test_create_duty_slot(self, db_session: AsyncSession, test_event: Event):
        """Test creating a new duty slot."""
        slot_in = DutySlotCreate(
            event_id=test_event.id,
            title="Morning Shift",
            date=date(2026, 6, 1),
            start_time=time(8, 0),
            end_time=time(12, 0),
            max_bookings=3,
        )
        slot = await crud_duty_slot.create(db_session, obj_in=slot_in)

        assert slot.title == "Morning Shift"
        assert slot.date == date(2026, 6, 1)
        assert slot.max_bookings == 3
        assert slot.id is not None

    async def test_get_duty_slot(
        self, db_session: AsyncSession, test_duty_slot: DutySlot
    ):
        """Test getting a duty slot by ID."""
        found = await crud_duty_slot.get(db_session, test_duty_slot.id)

        assert found is not None
        assert found.id == test_duty_slot.id

    async def test_update_duty_slot(
        self, db_session: AsyncSession, test_duty_slot: DutySlot
    ):
        """Test updating a duty slot."""
        updated = await crud_duty_slot.update(
            db_session,
            db_obj=test_duty_slot,
            obj_in=DutySlotUpdate(title="Updated Shift"),
        )

        assert updated.title == "Updated Shift"

    async def test_get_multi_filtered_by_event(
        self, db_session: AsyncSession, test_duty_slot: DutySlot, test_event: Event
    ):
        """Test filtering duty slots by event."""
        slots = await crud_duty_slot.get_multi_filtered(
            db_session, event_id=str(test_event.id)
        )

        assert len(slots) >= 1
        assert all(s.event_id == test_event.id for s in slots)

    async def test_get_multi_filtered_by_search(
        self, db_session: AsyncSession, test_duty_slot: DutySlot
    ):
        """Test searching duty slots by title."""
        slots = await crud_duty_slot.get_multi_filtered(
            db_session, search=test_duty_slot.title[:5]
        )

        assert len(slots) >= 1
        assert any(s.id == test_duty_slot.id for s in slots)

    async def test_get_multi_filtered_no_results(self, db_session: AsyncSession):
        """Test searching with no matching results."""
        slots = await crud_duty_slot.get_multi_filtered(
            db_session, search="zzz_nonexistent_zzz"
        )

        assert len(slots) == 0

    async def test_get_count_filtered(
        self, db_session: AsyncSession, test_duty_slot: DutySlot, test_event: Event
    ):
        """Test counting filtered duty slots."""
        count = await crud_duty_slot.get_count_filtered(
            db_session, event_id=str(test_event.id)
        )

        assert count >= 1

    async def test_get_count_filtered_empty(self, db_session: AsyncSession):
        """Test counting with no matching results."""
        count = await crud_duty_slot.get_count_filtered(
            db_session, search="zzz_nonexistent_zzz"
        )

        assert count == 0

    async def test_get_multi_filtered_sort_desc(
        self, db_session: AsyncSession, test_event: Event
    ):
        """Test sorting duty slots in descending order."""
        # Create two slots with different dates
        for i, d in enumerate([date(2026, 7, 1), date(2026, 7, 10)]):
            slot_in = DutySlotCreate(
                event_id=test_event.id,
                title=f"Slot {i}",
                date=d,
                start_time=time(9, 0),
                end_time=time(12, 0),
            )
            await crud_duty_slot.create(db_session, obj_in=slot_in)

        slots = await crud_duty_slot.get_multi_filtered(
            db_session,
            event_id=str(test_event.id),
            sort_by="date",
            sort_dir="desc",
        )

        assert len(slots) >= 2
        dates = [s.date for s in slots]
        assert dates == sorted(dates, reverse=True)

    async def test_remove_duty_slot(self, db_session: AsyncSession, test_event: Event):
        """Test removing a duty slot."""
        slot_in = DutySlotCreate(
            event_id=test_event.id,
            title="To Delete",
            date=date(2026, 8, 1),
            start_time=time(10, 0),
            end_time=time(14, 0),
        )
        slot = await crud_duty_slot.create(db_session, obj_in=slot_in)
        slot_id = slot.id

        await crud_duty_slot.remove(db_session, id=slot_id)

        deleted = await crud_duty_slot.get(db_session, slot_id)
        assert deleted is None
