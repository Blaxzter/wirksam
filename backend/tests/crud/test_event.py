"""Unit tests for Event CRUD operations."""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.event import event as crud_event
from app.models.event import Event
from app.models.user import User
from app.schemas.event import EventCreate, EventUpdate


@pytest.mark.asyncio
class TestCRUDEvent:
    """Test suite for Event CRUD operations."""

    async def test_create_event(self, db_session: AsyncSession, test_user: User):
        """Test creating a new event."""
        event_in = EventCreate(
            name="Test Event",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 3),
            status="draft",
            created_by_id=test_user.id,
        )
        event = await crud_event.create(db_session, obj_in=event_in)

        assert event.name == "Test Event"
        assert event.status == "draft"
        assert event.created_by_id == test_user.id
        assert event.id is not None

    async def test_get_event(self, db_session: AsyncSession, test_event: Event):
        """Test getting an event by ID."""
        event = await crud_event.get(db_session, test_event.id)

        assert event is not None
        assert event.name == test_event.name
        assert event.id == test_event.id

    async def test_update_event(self, db_session: AsyncSession, test_event: Event):
        """Test updating an event."""
        update = EventUpdate(name="Updated Event")
        updated = await crud_event.update(db_session, db_obj=test_event, obj_in=update)

        assert updated.name == "Updated Event"
        assert updated.id == test_event.id

    async def test_get_multi_filtered_by_status(
        self, db_session: AsyncSession, test_event: Event, test_draft_event: Event
    ):
        """Test filtering events by status."""
        published = await crud_event.get_multi_filtered(db_session, status="published")

        assert len(published) >= 1
        assert all(e.status == "published" for e in published)

        drafts = await crud_event.get_multi_filtered(db_session, status="draft")
        assert len(drafts) >= 1
        assert all(e.status == "draft" for e in drafts)

    async def test_get_count_filtered(
        self, db_session: AsyncSession, test_event: Event
    ):
        """Test counting events with filter."""
        count = await crud_event.get_count_filtered(db_session, status="published")

        assert count >= 1

    async def test_get_multi_filtered_by_search(
        self, db_session: AsyncSession, test_event: Event
    ):
        """Test searching events by name."""
        results = await crud_event.get_multi_filtered(db_session, search="Pfingsten")

        assert len(results) >= 1
        assert any(e.id == test_event.id for e in results)

    async def test_remove_event(self, db_session: AsyncSession, test_event: Event):
        """Test removing an event."""
        event_id = test_event.id
        removed = await crud_event.remove(db_session, id=event_id)

        assert removed is not None
        assert removed.id == event_id

        found = await crud_event.get(db_session, event_id)
        assert found is None
