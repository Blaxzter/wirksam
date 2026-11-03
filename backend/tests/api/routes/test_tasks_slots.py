"""Route tests for Task Shifts (generation/regeneration) endpoints."""

from typing import Any

import pytest
from httpx import AsyncClient

from app.models.task import Task


@pytest.mark.asyncio
class TestTaskShiftsRoutes:
    """Test suite for task shift generation routes (admin only)."""

    async def test_create_task_with_shifts(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test creating a task with auto-generated shifts."""
        r = await async_client.post(
            "/api/v1/tasks/with-shifts",
            json={
                "name": "Generated Task",
                "description": "Auto-generated shifts",
                "start_date": "2026-07-01",
                "end_date": "2026-07-03",
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "17:00:00",
                    "shift_duration_minutes": 240,
                    "people_per_shift": 2,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["task"]["name"] == "Generated Task"
        assert data["shifts_created"] >= 1

    async def test_create_task_with_shifts_and_group(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test creating a task with a new event."""
        r = await async_client.post(
            "/api/v1/tasks/with-shifts",
            json={
                "name": "Grouped Task",
                "start_date": "2026-08-01",
                "end_date": "2026-08-02",
                "new_event": {
                    "name": "New Group",
                    "start_date": "2026-08-01",
                    "end_date": "2026-08-31",
                },
                "schedule": {
                    "default_start_time": "10:00:00",
                    "default_end_time": "14:00:00",
                    "shift_duration_minutes": 120,
                    "people_per_shift": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["event"] is not None
        assert data["event"]["name"] == "New Group"

    async def test_regenerate_shifts_dry_run(
        self, async_client: AsyncClient, as_admin: None, test_task: Task
    ):
        """Test regenerating shifts in dry run mode."""
        r = await async_client.post(
            f"/api/v1/tasks/{test_task.id}/regenerate-shifts",
            params={"dry_run": True},
            json={
                "schedule": {
                    "default_start_time": "08:00:00",
                    "default_end_time": "16:00:00",
                    "shift_duration_minutes": 240,
                    "people_per_shift": 1,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert "shifts_added" in data
        assert "shifts_removed" in data
        assert "shifts_kept" in data
        assert "affected_bookings" in data

    async def test_regenerate_shifts(
        self, async_client: AsyncClient, as_admin: None, test_task: Task
    ):
        """Test actually regenerating shifts."""
        r = await async_client.post(
            f"/api/v1/tasks/{test_task.id}/regenerate-shifts",
            json={
                "schedule": {
                    "default_start_time": "09:00:00",
                    "default_end_time": "17:00:00",
                    "shift_duration_minutes": 480,
                    "people_per_shift": 3,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["task"]["id"] == str(test_task.id)

    async def test_add_shifts_to_task(
        self, async_client: AsyncClient, as_admin: None, test_task: Task
    ):
        """Test adding a new batch of shifts to an existing task."""
        r = await async_client.post(
            f"/api/v1/tasks/{test_task.id}/add-shifts",
            json={
                "start_date": "2026-06-11",
                "end_date": "2026-06-13",
                "schedule": {
                    "default_start_time": "10:00:00",
                    "default_end_time": "14:00:00",
                    "shift_duration_minutes": 120,
                    "people_per_shift": 2,
                    "overrides": [],
                },
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["shifts_added"] >= 1

    async def test_add_shifts_honours_specific_dates(
        self, async_client: AsyncClient, as_admin: None, test_task: Task
    ):
        """Gap days inside the submitted span get no shifts (#144).

        The wizard's "specific dates" mode sends start=min / end=max, so without
        the date list the two skipped days here would be created silently.
        """
        r = await async_client.post(
            f"/api/v1/tasks/{test_task.id}/add-shifts",
            json={
                "start_date": "2026-06-11",
                "end_date": "2026-06-14",
                "schedule": {
                    "default_start_time": "10:00:00",
                    "default_end_time": "12:00:00",
                    "shift_duration_minutes": 120,
                    "people_per_shift": 1,
                    "overrides": [],
                    "specific_dates": ["2026-06-11", "2026-06-14"],
                },
            },
        )

        assert r.status_code == 201
        assert r.json()["shifts_added"] == 2

        shifts = await async_client.get(
            "/api/v1/shifts/", params={"task_id": str(test_task.id), "limit": 200}
        )
        assert shifts.status_code == 200
        dates = {s["date"] for s in shifts.json()["items"]}
        assert "2026-06-11" in dates
        assert "2026-06-14" in dates
        assert "2026-06-12" not in dates
        assert "2026-06-13" not in dates

    async def test_list_batches(self, async_client: AsyncClient, test_task: Task):
        """Test listing shift batches for a task."""
        r = await async_client.get(f"/api/v1/tasks/{test_task.id}/batches")

        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_renaming_the_task_renames_its_generated_shifts(
        self, async_client: AsyncClient, as_admin: None
    ):
        """A plain save of the details takes the new name to every batch.

        With several batches the task's edit page only ever patches the task,
        so the shift titles ("<name> 10:00-12:00") have to follow from there.
        A title somebody typed is theirs and stays.
        """
        schedule: dict[str, Any] = {
            "default_start_time": "10:00:00",
            "default_end_time": "12:00:00",
            "shift_duration_minutes": 60,
            "people_per_shift": 1,
            "overrides": [],
        }
        r = await async_client.post(
            "/api/v1/tasks/with-shifts",
            json={
                "name": "Bar",
                "start_date": "2026-07-01",
                "end_date": "2026-07-01",
                "new_event": {
                    "name": "Sommerfest",
                    "start_date": "2026-07-01",
                    "end_date": "2026-07-05",
                },
                "schedule": schedule,
            },
        )
        assert r.status_code == 201, r.text
        task_id = r.json()["task"]["id"]
        r = await async_client.post(
            f"/api/v1/tasks/{task_id}/add-shifts",
            json={
                "start_date": "2026-07-03",
                "end_date": "2026-07-03",
                "schedule": schedule,
            },
        )
        assert r.status_code == 201, r.text
        r = await async_client.post(
            "/api/v1/shifts/",
            json={
                "task_id": task_id,
                "title": "Bar aufräumen",
                "date": "2026-07-04",
                "start_time": "18:00:00",
                "end_time": "19:00:00",
                "max_bookings": 2,
            },
        )
        assert r.status_code == 201, r.text

        r = await async_client.patch(f"/api/v1/tasks/{task_id}", json={"name": "Café"})
        assert r.status_code == 200, r.text

        shifts = await async_client.get(
            "/api/v1/shifts/", params={"task_id": task_id, "limit": 200}
        )
        titles = sorted(s["title"] for s in shifts.json()["items"])
        assert titles == [
            "Bar aufräumen",
            "Café 10:00-11:00",
            "Café 10:00-11:00",
            "Café 11:00-12:00",
            "Café 11:00-12:00",
        ]
