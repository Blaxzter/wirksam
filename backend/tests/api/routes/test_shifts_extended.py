"""Coverage gap tests for tasks/shifts.py (add-shifts validation, regenerate with batch, matching)."""

from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.event import Event
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User


@pytest.mark.asyncio
class TestAddShiftsCoverage:
    """Coverage tests for add-shifts endpoint."""

    async def test_add_shifts_with_event_validation(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test that add-shifts validates dates against event range."""
        group = Event(
            name="Constrained Group",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 15),
            status="published",
        )
        db_session.add(group)
        await db_session.flush()
        await db_session.refresh(group)

        task = Task(
            name="Grouped Task",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 5),
            event_id=group.id,
            status="draft",
        )
        db_session.add(task)
        await db_session.flush()
        await db_session.refresh(task)

        # Try to add shifts outside the group's date range
        r = await async_client.post(
            f"/api/v1/tasks/{task.id}/add-shifts",
            json={
                "start_date": "2026-07-20",
                "end_date": "2026-07-25",
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "17:00:00",
                    "shift_duration_minutes": 240,
                    "people_per_shift": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 400

    async def test_add_shifts_with_location_and_category(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_task: Task,
    ):
        """Test adding shifts with location and category."""
        r = await async_client.post(
            f"/api/v1/tasks/{test_task.id}/add-shifts",
            json={
                "start_date": "2026-06-11",
                "end_date": "2026-06-11",
                "location": "Entrance A",
                "category": "Security",
                "schedule": {
                    "default_start_time": "08:00:00",
                    "default_end_time": "12:00:00",
                    "shift_duration_minutes": 120,
                    "people_per_shift": 2,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["shifts_added"] >= 1

    async def test_add_shifts_to_nonexistent_task(
        self,
        async_client: AsyncClient,
        as_admin: None,
    ):
        """Test adding shifts to a nonexistent task returns 404."""
        import uuid

        fake_id = uuid.uuid4()
        r = await async_client.post(
            f"/api/v1/tasks/{fake_id}/add-shifts",
            json={
                "start_date": "2026-07-01",
                "end_date": "2026-07-02",
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "17:00:00",
                    "shift_duration_minutes": 240,
                    "people_per_shift": 1,
                    "overrides": [],
                },
            },
        )
        assert r.status_code == 404


@pytest.mark.asyncio
class TestRegenerateShiftsCoverage:
    """Coverage tests for regenerate-shifts endpoint."""

    async def test_regenerate_with_matching_shifts_preserved(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that regeneration preserves bookings on matching shifts."""
        task = Task(
            name="Regen Match Task",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            status="draft",
        )
        db_session.add(task)
        await db_session.flush()
        await db_session.refresh(task)

        # Create a shift that will match the regenerated config
        shift = Shift(
            task_id=task.id,
            title="Existing Shift",
            date=date(2026, 9, 1),
            start_time=time(9, 0),
            end_time=time(13, 0),
            max_bookings=2,
        )
        db_session.add(shift)
        await db_session.flush()
        await db_session.refresh(shift)

        booking = Booking(
            shift_id=shift.id,
            user_id=test_user.id,
            status="confirmed",
        )
        db_session.add(booking)
        await db_session.flush()

        # Regenerate with same time window — shift should match
        r = await async_client.post(
            f"/api/v1/tasks/{task.id}/regenerate-shifts",
            json={
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "13:00:00",
                    "shift_duration_minutes": 240,
                    "people_per_shift": 3,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["shifts_kept"] >= 1
        assert data["affected_bookings"] == []

    async def test_regenerate_dry_run_no_changes(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test dry run doesn't persist changes."""
        task = Task(
            name="Dry Run Task",
            start_date=date(2026, 9, 5),
            end_date=date(2026, 9, 6),
            status="draft",
        )
        db_session.add(task)
        await db_session.flush()
        await db_session.refresh(task)

        # Create existing shift
        shift = Shift(
            task_id=task.id,
            title="Dry Run Shift",
            date=date(2026, 9, 5),
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        db_session.add(shift)
        await db_session.flush()

        # Dry-run with different time (should show shift as removed)
        r = await async_client.post(
            f"/api/v1/tasks/{task.id}/regenerate-shifts",
            params={"dry_run": True},
            json={
                "schedule": {
                    "default_start_time": "10:00:00",
                    "default_end_time": "14:00:00",
                    "shift_duration_minutes": 240,
                    "people_per_shift": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["shifts_removed"] >= 1
        assert data["shifts_added"] >= 1

    async def test_regenerate_dry_run_leaves_kept_shifts_alone(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """A kept shift's title, places, location and category stay as they were.

        The real run copies those onto every matched shift. The preview used to
        do the same before checking ``dry_run``, and the request's commit kept
        it, so looking at the preview and cancelling changed the rota.
        """
        task = Task(
            name="Preview Task",
            start_date=date(2026, 9, 5),
            end_date=date(2026, 9, 5),
            status="draft",
        )
        db_session.add(task)
        await db_session.flush()
        kept = Shift(
            task_id=task.id,
            title="Old title",
            date=date(2026, 9, 5),
            start_time=time(10, 0),
            end_time=time(14, 0),
            max_bookings=3,
            location="Old place",
            category="Old category",
        )
        db_session.add(kept)
        await db_session.flush()

        r = await async_client.post(
            f"/api/v1/tasks/{task.id}/regenerate-shifts",
            params={"dry_run": True},
            json={
                "name": "New name",
                "location": "New place",
                "category": "New category",
                "schedule": {
                    "default_start_time": "10:00:00",
                    "default_end_time": "14:00:00",
                    "shift_duration_minutes": 240,
                    "people_per_shift": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200, r.text
        assert r.json()["shifts_kept"] == 1
        await db_session.refresh(kept)
        assert (kept.title, kept.max_bookings, kept.location, kept.category) == (
            "Old title",
            3,
            "Old place",
            "Old category",
        )
        await db_session.refresh(task)
        assert task.name == "Preview Task"

    async def test_regenerate_with_affected_bookings(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test regeneration reports affected bookings for deleted shifts."""
        task = Task(
            name="Affected Bookings Task",
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 11),
            status="draft",
        )
        db_session.add(task)
        await db_session.flush()
        await db_session.refresh(task)

        # Create shift with booking
        shift = Shift(
            task_id=task.id,
            title="Old Shift",
            date=date(2026, 9, 10),
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        db_session.add(shift)
        await db_session.flush()

        booking = Booking(
            shift_id=shift.id,
            user_id=test_user.id,
            status="confirmed",
        )
        db_session.add(booking)
        await db_session.flush()

        # Regenerate with completely different times — old shift won't match
        r = await async_client.post(
            f"/api/v1/tasks/{task.id}/regenerate-shifts",
            params={"dry_run": True},
            json={
                "schedule": {
                    "default_start_time": "14:00:00",
                    "default_end_time": "18:00:00",
                    "shift_duration_minutes": 240,
                    "people_per_shift": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert len(data["affected_bookings"]) >= 1
        assert data["affected_bookings"][0]["slot_title"] == "Old Shift"

    async def test_regenerate_with_batch_id(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test regenerating shifts scoped to a specific batch."""
        task = Task(
            name="Batch Regen Task",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 5),
            status="draft",
        )
        db_session.add(task)
        await db_session.flush()
        await db_session.refresh(task)

        batch = ShiftBatch(
            task_id=task.id,
            label="Morning Batch",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 2),
            default_start_time=time(8, 0),
            default_end_time=time(12, 0),
            shift_duration_minutes=240,
            people_per_shift=2,
            location="Hall A",
            category="Security",
        )
        db_session.add(batch)
        await db_session.flush()
        await db_session.refresh(batch)

        # Create a shift linked to the batch
        shift = Shift(
            task_id=task.id,
            title="Batch Shift",
            date=date(2026, 10, 1),
            start_time=time(8, 0),
            end_time=time(12, 0),
            batch_id=batch.id,
        )
        db_session.add(shift)
        await db_session.flush()

        # Regenerate scoped to this batch
        r = await async_client.post(
            f"/api/v1/tasks/{task.id}/regenerate-shifts",
            params={"batch_id": str(batch.id)},
            json={
                "schedule": {
                    "default_start_time": "08:00:00",
                    "default_end_time": "12:00:00",
                    "shift_duration_minutes": 240,
                    "people_per_shift": 3,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["shifts_kept"] >= 1

    async def test_regenerate_with_wrong_batch_task(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test regenerating with a batch that doesn't belong to the task."""
        event1 = Task(
            name="Task One",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 5),
            status="draft",
        )
        event2 = Task(
            name="Task Two",
            start_date=date(2026, 11, 10),
            end_date=date(2026, 11, 15),
            status="draft",
        )
        db_session.add_all([event1, event2])
        await db_session.flush()
        await db_session.refresh(event1)
        await db_session.refresh(event2)

        batch = ShiftBatch(
            task_id=event2.id,
            label="Wrong Task Batch",
            start_date=date(2026, 11, 10),
            end_date=date(2026, 11, 11),
        )
        db_session.add(batch)
        await db_session.flush()
        await db_session.refresh(batch)

        r = await async_client.post(
            f"/api/v1/tasks/{event1.id}/regenerate-shifts",
            params={"batch_id": str(batch.id)},
            json={
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "17:00:00",
                    "shift_duration_minutes": 240,
                    "people_per_shift": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 400

    async def test_regenerate_updates_task_fields(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test that regeneration updates task name and description."""
        task = Task(
            name="Original Name",
            description="Original desc",
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 3),
            status="draft",
        )
        db_session.add(task)
        await db_session.flush()
        await db_session.refresh(task)

        r = await async_client.post(
            f"/api/v1/tasks/{task.id}/regenerate-shifts",
            json={
                "name": "Updated Name",
                "description": "Updated desc",
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "17:00:00",
                    "shift_duration_minutes": 480,
                    "people_per_shift": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["task"]["name"] == "Updated Name"
        assert data["task"]["description"] == "Updated desc"

    async def test_create_task_with_shifts_nonexistent_task(
        self,
        async_client: AsyncClient,
        as_admin: None,
    ):
        """Test creating task with shifts returns 201."""
        r = await async_client.post(
            "/api/v1/tasks/with-shifts",
            json={
                "name": "Full Coverage Task",
                "description": "Testing all paths",
                "start_date": "2027-01-10",
                "end_date": "2027-01-12",
                "location": "Main Hall",
                "category": "Catering",
                "schedule": {
                    "default_start_time": "06:00:00",
                    "default_end_time": "22:00:00",
                    "shift_duration_minutes": 240,
                    "people_per_shift": 4,
                    "remainder_mode": "extend",
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["task"]["location"] == "Main Hall"
        assert data["task"]["category"] == "Catering"
        assert data["shifts_created"] >= 1
