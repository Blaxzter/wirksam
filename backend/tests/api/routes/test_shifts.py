"""Route tests for Shift endpoints."""

import uuid
from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User


@pytest.mark.asyncio
class TestShiftRoutes:
    """Test suite for /shifts/ routes."""

    async def test_list_shifts(self, async_client: AsyncClient, test_shift: Shift):
        """Test listing duty shifts."""
        r = await async_client.get("/api/v1/shifts/")

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert any(item["id"] == str(test_shift.id) for item in data["items"])

    async def test_list_shifts_filter_by_task(
        self, async_client: AsyncClient, test_shift: Shift, test_task: Task
    ):
        """Test filtering duty shifts by task_id."""
        r = await async_client.get(
            "/api/v1/shifts/", params={"task_id": str(test_task.id)}
        )

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert all(item["task_id"] == str(test_task.id) for item in data["items"])

    async def test_list_shifts_search(
        self, async_client: AsyncClient, test_shift: Shift
    ):
        """Test searching duty shifts."""
        r = await async_client.get(
            "/api/v1/shifts/",
            params={"search": test_shift.title[:5]},
        )

        assert r.status_code == 200
        assert r.json()["total"] >= 1

    async def test_get_shift(self, async_client: AsyncClient, test_shift: Shift):
        """Test getting a specific duty shift."""
        r = await async_client.get(f"/api/v1/shifts/{test_shift.id}")

        assert r.status_code == 200
        assert r.json()["id"] == str(test_shift.id)
        assert "current_bookings" in r.json()
        assert "is_booked_by_me" in r.json()

    async def test_get_shift_not_found(self, async_client: AsyncClient):
        """Test getting a nonexistent duty shift."""
        fake_id = uuid.uuid4()
        r = await async_client.get(f"/api/v1/shifts/{fake_id}")
        assert r.status_code == 404

    async def test_create_shift(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_task: Task,
    ):
        """Test creating a duty shift (admin only)."""
        r = await async_client.post(
            "/api/v1/shifts/",
            json={
                "task_id": str(test_task.id),
                "title": "New Shift",
                "date": "2026-06-15",
                "start_time": "09:00:00",
                "end_time": "13:00:00",
                "max_bookings": 2,
            },
        )

        assert r.status_code == 201
        assert r.json()["title"] == "New Shift"
        assert r.json()["max_bookings"] == 2

    async def test_update_shift(
        self,
        async_client: AsyncClient,
        as_admin: None,
        test_shift: Shift,
    ):
        """Test updating a duty shift (admin only)."""
        r = await async_client.patch(
            f"/api/v1/shifts/{test_shift.id}",
            json={"title": "Updated Shift Title"},
        )

        assert r.status_code == 200
        assert r.json()["title"] == "Updated Shift Title"

    async def test_delete_shift(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_task: Task,
    ):
        """Test deleting a duty shift (admin only)."""
        shift = Shift(
            task_id=test_task.id,
            title="To Delete",
            date=date(2026, 9, 1),
            start_time=time(10, 0),
            end_time=time(14, 0),
        )
        db_session.add(shift)
        await db_session.flush()
        await db_session.refresh(shift)

        r = await async_client.delete(f"/api/v1/shifts/{shift.id}")
        assert r.status_code == 204

    async def test_list_shift_bookings(
        self, async_client: AsyncClient, test_shift: Shift
    ):
        """Test listing bookings for a specific shift."""
        r = await async_client.get(f"/api/v1/shifts/{test_shift.id}/bookings")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


@pytest.mark.asyncio
class TestShiftsEventAdminRole:
    """Event admins manage every shift of their event's tasks."""

    async def test_create_shift_as_event_admin(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_task: Task,
    ):
        """Test that an event admin can create duty shifts."""
        r = await async_client.post(
            "/api/v1/shifts/",
            json={
                "task_id": str(test_task.id),
                "title": "Manager Shift",
                "date": "2026-07-01",
                "start_time": "09:00:00",
                "end_time": "12:00:00",
            },
        )

        assert r.status_code == 201
        assert r.json()["title"] == "Manager Shift"

    async def test_create_shift_as_normal_user_raises_403(
        self,
        async_client: AsyncClient,
        test_task: Task,
    ):
        """Test that a plain user cannot create duty shifts."""
        r = await async_client.post(
            "/api/v1/shifts/",
            json={
                "task_id": str(test_task.id),
                "title": "Unauthorized Shift",
                "date": "2026-07-01",
                "start_time": "09:00:00",
                "end_time": "12:00:00",
            },
        )

        assert r.status_code == 403

    async def test_update_shift_as_event_admin(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_shift: Shift,
    ):
        """Test that an event admin can update duty shifts."""
        r = await async_client.patch(
            f"/api/v1/shifts/{test_shift.id}",
            json={"title": "Updated by Manager"},
        )

        assert r.status_code == 200
        assert r.json()["title"] == "Updated by Manager"

    async def test_update_shift_as_normal_user_raises_403(
        self,
        async_client: AsyncClient,
        test_shift: Shift,
    ):
        """Test that a plain user cannot update duty shifts."""
        r = await async_client.patch(
            f"/api/v1/shifts/{test_shift.id}",
            json={"title": "Should Fail"},
        )

        assert r.status_code == 403

    async def test_delete_shift_as_event_admin(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_task: Task,
    ):
        """Test that an event admin can delete duty shifts."""
        shift = Shift(
            task_id=test_task.id,
            title="Manager Delete Me",
            date=date(2026, 9, 1),
            start_time=time(10, 0),
            end_time=time(14, 0),
        )
        db_session.add(shift)
        await db_session.flush()
        await db_session.refresh(shift)

        r = await async_client.delete(f"/api/v1/shifts/{shift.id}")
        assert r.status_code == 204

    async def test_delete_shift_as_normal_user_raises_403(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
    ):
        """Test that a plain user cannot delete duty shifts."""
        shift = Shift(
            task_id=test_task.id,
            title="Should Not Delete",
            date=date(2026, 9, 1),
            start_time=time(10, 0),
            end_time=time(14, 0),
        )
        db_session.add(shift)
        await db_session.flush()
        await db_session.refresh(shift)

        r = await async_client.delete(f"/api/v1/shifts/{shift.id}")
        assert r.status_code == 403
        assert r.json()["code"] == "task.forbidden"


@pytest.mark.asyncio
class TestShiftBatchesAndRegeneration:
    async def test_another_tasks_batch_is_refused(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_task: Task,
        test_draft_task: Task,
    ):
        """Otherwise deleting that batch would take this shift with it."""
        foreign = ShiftBatch(
            task_id=test_draft_task.id,
            start_date=test_draft_task.start_date,
            end_date=test_draft_task.end_date,
        )
        db_session.add(foreign)
        await db_session.flush()

        r = await async_client.post(
            "/api/v1/shifts/",
            json={
                "task_id": str(test_task.id),
                "batch_id": str(foreign.id),
                "title": "Wrong batch",
                "date": "2026-06-12",
            },
        )

        assert r.status_code == 400
        assert r.json()["code"] == "batch.wrong_task"

    async def test_regenerating_a_booked_shift_away_cancels_with_a_snapshot(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        """Not left confirmed with no shift, dropping out of everyone's hours."""
        shift = Shift(
            task_id=test_task.id,
            title="Old slot",
            date=date(2026, 6, 12),
            start_time=time(7, 0),
            end_time=time(8, 0),
        )
        db_session.add(shift)
        await db_session.flush()
        booking = Booking(shift_id=shift.id, user_id=test_user.id, status="confirmed")
        db_session.add(booking)
        await db_session.flush()

        r = await async_client.post(
            f"/api/v1/tasks/{test_task.id}/regenerate-shifts",
            json={
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "11:00:00",
                    "shift_duration_minutes": 60,
                }
            },
        )

        assert r.status_code == 200, r.text
        assert r.json()["shifts_removed"] == 1
        await db_session.refresh(booking)
        assert booking.status == "cancelled"
        assert booking.cancelled_task_name == test_task.name
        assert booking.cancelled_shift_title == "Old slot"
