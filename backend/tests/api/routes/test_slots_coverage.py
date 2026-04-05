"""Coverage gap tests for events/slots.py (add-slots validation, regenerate with batch, matching)."""

from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.duty_slot import DutySlot
from app.models.event import Event
from app.models.event_group import EventGroup
from app.models.slot_batch import SlotBatch
from app.models.user import User


@pytest.mark.asyncio
class TestAddSlotsCoverage:
    """Coverage tests for add-slots endpoint."""

    async def test_add_slots_with_event_group_validation(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test that add-slots validates dates against event group range."""
        group = EventGroup(
            name="Constrained Group",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 15),
            status="published",
        )
        db_session.add(group)
        await db_session.flush()
        await db_session.refresh(group)

        event = Event(
            name="Grouped Event",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 5),
            event_group_id=group.id,
            status="draft",
        )
        db_session.add(event)
        await db_session.flush()
        await db_session.refresh(event)

        # Try to add slots outside the group's date range
        r = await async_client.post(
            f"/api/v1/events/{event.id}/add-slots",
            json={
                "start_date": "2026-07-20",
                "end_date": "2026-07-25",
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "17:00:00",
                    "slot_duration_minutes": 240,
                    "people_per_slot": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 400

    async def test_add_slots_with_location_and_category(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_event: Event,
    ):
        """Test adding slots with location and category."""
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/add-slots",
            json={
                "start_date": "2026-05-24",
                "end_date": "2026-05-24",
                "location": "Entrance A",
                "category": "Security",
                "schedule": {
                    "default_start_time": "08:00:00",
                    "default_end_time": "12:00:00",
                    "slot_duration_minutes": 120,
                    "people_per_slot": 2,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["slots_added"] >= 1

    async def test_add_slots_to_nonexistent_event(
        self,
        async_client: AsyncClient,
        as_admin: None,
    ):
        """Test adding slots to a nonexistent event returns 404."""
        import uuid

        fake_id = uuid.uuid4()
        r = await async_client.post(
            f"/api/v1/events/{fake_id}/add-slots",
            json={
                "start_date": "2026-07-01",
                "end_date": "2026-07-02",
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "17:00:00",
                    "slot_duration_minutes": 240,
                    "people_per_slot": 1,
                    "overrides": [],
                },
            },
        )
        assert r.status_code == 404


@pytest.mark.asyncio
class TestRegenerateSlotsCoverage:
    """Coverage tests for regenerate-slots endpoint."""

    async def test_regenerate_with_matching_slots_preserved(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that regeneration preserves bookings on matching slots."""
        event = Event(
            name="Regen Match Event",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            status="draft",
        )
        db_session.add(event)
        await db_session.flush()
        await db_session.refresh(event)

        # Create a slot that will match the regenerated config
        slot = DutySlot(
            event_id=event.id,
            title="Existing Slot",
            date=date(2026, 9, 1),
            start_time=time(9, 0),
            end_time=time(13, 0),
            max_bookings=2,
        )
        db_session.add(slot)
        await db_session.flush()
        await db_session.refresh(slot)

        booking = Booking(
            duty_slot_id=slot.id,
            user_id=test_user.id,
            status="confirmed",
        )
        db_session.add(booking)
        await db_session.flush()

        # Regenerate with same time window — slot should match
        r = await async_client.post(
            f"/api/v1/events/{event.id}/regenerate-slots",
            json={
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "13:00:00",
                    "slot_duration_minutes": 240,
                    "people_per_slot": 3,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["slots_kept"] >= 1
        assert data["affected_bookings"] == []

    async def test_regenerate_dry_run_no_changes(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test dry run doesn't persist changes."""
        event = Event(
            name="Dry Run Event",
            start_date=date(2026, 9, 5),
            end_date=date(2026, 9, 6),
            status="draft",
        )
        db_session.add(event)
        await db_session.flush()
        await db_session.refresh(event)

        # Create existing slot
        slot = DutySlot(
            event_id=event.id,
            title="Dry Run Slot",
            date=date(2026, 9, 5),
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        db_session.add(slot)
        await db_session.flush()

        # Dry-run with different time (should show slot as removed)
        r = await async_client.post(
            f"/api/v1/events/{event.id}/regenerate-slots",
            params={"dry_run": True},
            json={
                "schedule": {
                    "default_start_time": "10:00:00",
                    "default_end_time": "14:00:00",
                    "slot_duration_minutes": 240,
                    "people_per_slot": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["slots_removed"] >= 1
        assert data["slots_added"] >= 1

    async def test_regenerate_with_affected_bookings(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test regeneration reports affected bookings for deleted slots."""
        event = Event(
            name="Affected Bookings Event",
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 11),
            status="draft",
        )
        db_session.add(event)
        await db_session.flush()
        await db_session.refresh(event)

        # Create slot with booking
        slot = DutySlot(
            event_id=event.id,
            title="Old Slot",
            date=date(2026, 9, 10),
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        db_session.add(slot)
        await db_session.flush()

        booking = Booking(
            duty_slot_id=slot.id,
            user_id=test_user.id,
            status="confirmed",
        )
        db_session.add(booking)
        await db_session.flush()

        # Regenerate with completely different times — old slot won't match
        r = await async_client.post(
            f"/api/v1/events/{event.id}/regenerate-slots",
            params={"dry_run": True},
            json={
                "schedule": {
                    "default_start_time": "14:00:00",
                    "default_end_time": "18:00:00",
                    "slot_duration_minutes": 240,
                    "people_per_slot": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert len(data["affected_bookings"]) >= 1
        assert data["affected_bookings"][0]["slot_title"] == "Old Slot"

    async def test_regenerate_with_batch_id(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test regenerating slots scoped to a specific batch."""
        event = Event(
            name="Batch Regen Event",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 5),
            status="draft",
        )
        db_session.add(event)
        await db_session.flush()
        await db_session.refresh(event)

        batch = SlotBatch(
            event_id=event.id,
            label="Morning Batch",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 2),
            default_start_time=time(8, 0),
            default_end_time=time(12, 0),
            slot_duration_minutes=240,
            people_per_slot=2,
            location="Hall A",
            category="Security",
        )
        db_session.add(batch)
        await db_session.flush()
        await db_session.refresh(batch)

        # Create a slot linked to the batch
        slot = DutySlot(
            event_id=event.id,
            title="Batch Slot",
            date=date(2026, 10, 1),
            start_time=time(8, 0),
            end_time=time(12, 0),
            batch_id=batch.id,
        )
        db_session.add(slot)
        await db_session.flush()

        # Regenerate scoped to this batch
        r = await async_client.post(
            f"/api/v1/events/{event.id}/regenerate-slots",
            params={"batch_id": str(batch.id)},
            json={
                "schedule": {
                    "default_start_time": "08:00:00",
                    "default_end_time": "12:00:00",
                    "slot_duration_minutes": 240,
                    "people_per_slot": 3,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["slots_kept"] >= 1

    async def test_regenerate_with_wrong_batch_event(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test regenerating with a batch that doesn't belong to the event."""
        event1 = Event(
            name="Event One",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 5),
            status="draft",
        )
        event2 = Event(
            name="Event Two",
            start_date=date(2026, 11, 10),
            end_date=date(2026, 11, 15),
            status="draft",
        )
        db_session.add_all([event1, event2])
        await db_session.flush()
        await db_session.refresh(event1)
        await db_session.refresh(event2)

        batch = SlotBatch(
            event_id=event2.id,
            label="Wrong Event Batch",
            start_date=date(2026, 11, 10),
            end_date=date(2026, 11, 11),
        )
        db_session.add(batch)
        await db_session.flush()
        await db_session.refresh(batch)

        r = await async_client.post(
            f"/api/v1/events/{event1.id}/regenerate-slots",
            params={"batch_id": str(batch.id)},
            json={
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "17:00:00",
                    "slot_duration_minutes": 240,
                    "people_per_slot": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 400

    async def test_regenerate_updates_event_fields(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test that regeneration updates event name and description."""
        event = Event(
            name="Original Name",
            description="Original desc",
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 3),
            status="draft",
        )
        db_session.add(event)
        await db_session.flush()
        await db_session.refresh(event)

        r = await async_client.post(
            f"/api/v1/events/{event.id}/regenerate-slots",
            json={
                "name": "Updated Name",
                "description": "Updated desc",
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "17:00:00",
                    "slot_duration_minutes": 480,
                    "people_per_slot": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["event"]["name"] == "Updated Name"
        assert data["event"]["description"] == "Updated desc"

    async def test_create_event_with_slots_nonexistent_event(
        self,
        async_client: AsyncClient,
        as_admin: None,
    ):
        """Test creating event with slots returns 201."""
        r = await async_client.post(
            "/api/v1/events/with-slots",
            json={
                "name": "Full Coverage Event",
                "description": "Testing all paths",
                "start_date": "2027-01-10",
                "end_date": "2027-01-12",
                "location": "Main Hall",
                "category": "Catering",
                "schedule": {
                    "default_start_time": "06:00:00",
                    "default_end_time": "22:00:00",
                    "slot_duration_minutes": 240,
                    "people_per_slot": 4,
                    "remainder_mode": "extend",
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["event"]["location"] == "Main Hall"
        assert data["event"]["category"] == "Catering"
        assert data["duty_slots_created"] >= 1
