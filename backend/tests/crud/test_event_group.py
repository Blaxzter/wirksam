"""Unit tests for EventGroup and UserAvailability CRUD operations."""

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.event_group import event_group as crud_event_group
from app.crud.user_availability import user_availability as crud_availability
from app.models.event_group import EventGroup
from app.models.user import User
from app.models.user_availability import UserAvailability
from app.schemas.event_group import EventGroupCreate, EventGroupUpdate
from app.schemas.user_availability import (
    UserAvailabilityCreate,
    UserAvailabilityDateInput,
)


@pytest.mark.asyncio
class TestCRUDEventGroup:
    """Test suite for EventGroup CRUD operations."""

    async def test_create_event_group(self, db_session: AsyncSession, test_user: User):
        """Test creating a new event group."""
        group_in = EventGroupCreate(
            name="Summer Camp 2026",
            start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 7, 7),
            status="draft",
            created_by_id=test_user.id,
        )
        group = await crud_event_group.create(db_session, obj_in=group_in)

        assert group.name == "Summer Camp 2026"
        assert group.status == "draft"
        assert group.created_by_id == test_user.id
        assert group.id is not None

    async def test_get_event_group(
        self, db_session: AsyncSession, test_event_group: EventGroup
    ):
        """Test getting an event group by ID."""
        group = await crud_event_group.get(db_session, test_event_group.id)

        assert group is not None
        assert group.name == test_event_group.name
        assert group.id == test_event_group.id

    async def test_get_nonexistent_event_group(self, db_session: AsyncSession):
        """Test getting a non-existent event group returns None."""
        import uuid

        group = await crud_event_group.get(db_session, uuid.uuid4())
        assert group is None

    async def test_update_event_group(
        self, db_session: AsyncSession, test_event_group: EventGroup
    ):
        """Test updating an event group."""
        update = EventGroupUpdate(name="Updated Group Name")
        updated = await crud_event_group.update(
            db_session, db_obj=test_event_group, obj_in=update
        )

        assert updated.name == "Updated Group Name"
        assert updated.id == test_event_group.id

    async def test_get_multi_filtered_by_status(
        self,
        db_session: AsyncSession,
        test_event_group: EventGroup,
        test_draft_event_group: EventGroup,
    ):
        """Test filtering event groups by status."""
        published = await crud_event_group.get_multi_filtered(
            db_session, status="published"
        )
        assert any(g.id == test_event_group.id for g in published)
        assert all(g.status == "published" for g in published)

        drafts = await crud_event_group.get_multi_filtered(db_session, status="draft")
        assert any(g.id == test_draft_event_group.id for g in drafts)
        assert all(g.status == "draft" for g in drafts)

    async def test_get_multi_filtered_by_search(
        self, db_session: AsyncSession, test_event_group: EventGroup
    ):
        """Test searching event groups by name."""
        results = await crud_event_group.get_multi_filtered(
            db_session, search="Kirchentags"
        )
        assert any(g.id == test_event_group.id for g in results)

    async def test_get_count_filtered(
        self, db_session: AsyncSession, test_event_group: EventGroup
    ):
        """Test counting event groups with a filter."""
        count = await crud_event_group.get_count_filtered(
            db_session, status="published"
        )
        assert count >= 1

    async def test_get_count_filtered_search(
        self, db_session: AsyncSession, test_event_group: EventGroup
    ):
        """Test counting event groups by search term."""
        count = await crud_event_group.get_count_filtered(
            db_session, search="Kirchentags"
        )
        assert count >= 1


@pytest.mark.asyncio
class TestCRUDUserAvailability:
    """Test suite for UserAvailability CRUD operations."""

    async def test_upsert_creates_fully_available(
        self, db_session: AsyncSession, test_user: User, test_event_group: EventGroup
    ):
        """Test creating a new 'fully_available' availability via upsert."""
        avail_in = UserAvailabilityCreate(
            availability_type="fully_available",
            notes="Always here",
            dates=[],
        )
        avail = await crud_availability.upsert_for_user(
            db_session,
            user_id=test_user.id,
            event_group_id=test_event_group.id,
            obj_in=avail_in,
        )

        assert avail.availability_type == "fully_available"
        assert avail.notes == "Always here"
        assert avail.user_id == test_user.id
        assert avail.event_group_id == test_event_group.id
        assert avail.available_dates == []

    async def test_upsert_creates_with_specific_dates(
        self, db_session: AsyncSession, test_user: User, test_event_group: EventGroup
    ):
        """Test creating a 'specific_dates' availability with date entries."""
        dates: list[datetime.date | UserAvailabilityDateInput] = [
            datetime.date(2026, 6, 10),
            datetime.date(2026, 6, 12),
        ]
        avail_in = UserAvailabilityCreate(
            availability_type="specific_dates",
            notes=None,
            dates=dates,
        )
        avail = await crud_availability.upsert_for_user(
            db_session,
            user_id=test_user.id,
            event_group_id=test_event_group.id,
            obj_in=avail_in,
        )

        assert avail.availability_type == "specific_dates"
        assert len(avail.available_dates) == 2
        stored_dates = {d.slot_date for d in avail.available_dates}
        assert stored_dates == set(dates)

    async def test_upsert_updates_existing(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_user_availability: UserAvailability,
        test_event_group: EventGroup,
    ):
        """Test that upsert updates an existing availability record."""
        avail_in = UserAvailabilityCreate(
            availability_type="specific_dates",
            notes="Changed my mind",
            dates=[datetime.date(2026, 6, 11)],
        )
        updated = await crud_availability.upsert_for_user(
            db_session,
            user_id=test_user.id,
            event_group_id=test_event_group.id,
            obj_in=avail_in,
        )

        assert updated.id == test_user_availability.id
        assert updated.availability_type == "specific_dates"
        assert updated.notes == "Changed my mind"
        assert len(updated.available_dates) == 1
        assert updated.available_dates[0].slot_date == datetime.date(2026, 6, 11)

    async def test_get_by_user_and_group(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_user_availability: UserAvailability,
        test_event_group: EventGroup,
    ):
        """Test finding an availability by user and group."""
        found = await crud_availability.get_by_user_and_group(
            db_session,
            user_id=test_user.id,
            event_group_id=test_event_group.id,
        )

        assert found is not None
        assert found.id == test_user_availability.id

    async def test_get_by_user_and_group_not_found(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
        test_event_group: EventGroup,
    ):
        """Test that None is returned when no availability exists."""
        found = await crud_availability.get_by_user_and_group(
            db_session,
            user_id=test_admin_user.id,
            event_group_id=test_event_group.id,
        )
        assert found is None

    async def test_get_multi_by_group(
        self,
        db_session: AsyncSession,
        test_user_availability: UserAvailability,
        test_event_group: EventGroup,
    ):
        """Test retrieving all availabilities for a group."""
        results = await crud_availability.get_multi_by_group(
            db_session, event_group_id=test_event_group.id
        )

        assert len(results) >= 1
        assert any(a.id == test_user_availability.id for a in results)

    async def test_delete_for_user(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_user_availability: UserAvailability,
        test_event_group: EventGroup,
    ):
        """Test removing a user's availability."""
        deleted = await crud_availability.delete_for_user(
            db_session,
            user_id=test_user.id,
            event_group_id=test_event_group.id,
        )

        assert deleted is True
        found = await crud_availability.get_by_user_and_group(
            db_session,
            user_id=test_user.id,
            event_group_id=test_event_group.id,
        )
        assert found is None

    async def test_delete_for_user_not_found(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
        test_event_group: EventGroup,
    ):
        """Test that deleting a non-existent availability returns False."""
        deleted = await crud_availability.delete_for_user(
            db_session,
            user_id=test_admin_user.id,
            event_group_id=test_event_group.id,
        )
        assert deleted is False
