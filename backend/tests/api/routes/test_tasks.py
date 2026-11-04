"""Route tests for Task endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.task import Task
from app.models.user import User


@pytest.mark.asyncio
class TestTasksRoutes:
    """Test suite for /tasks/ routes."""

    async def test_list_tasks(self, async_client: AsyncClient, test_task: Task):
        """Test listing tasks returns published tasks."""
        r = await async_client.get("/api/v1/tasks/")

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert any(item["name"] == test_task.name for item in data["items"])

    async def test_list_tasks_filters_drafts_for_normal_user(
        self, async_client: AsyncClient, test_task: Task, test_draft_task: Task
    ):
        """Test that normal users only see published tasks by default."""
        r = await async_client.get("/api/v1/tasks/")

        assert r.status_code == 200
        data = r.json()
        names = [item["name"] for item in data["items"]]
        assert test_task.name in names
        assert test_draft_task.name not in names

    async def test_get_task(self, async_client: AsyncClient, test_task: Task):
        """Test getting a single published task."""
        r = await async_client.get(f"/api/v1/tasks/{test_task.id}")

        assert r.status_code == 200
        assert r.json()["name"] == test_task.name

    async def test_draft_task_hidden_from_normal_user(
        self, async_client: AsyncClient, test_draft_task: Task
    ):
        """Test that a normal user cannot access a draft task."""
        r = await async_client.get(f"/api/v1/tasks/{test_draft_task.id}")

        assert r.status_code == 403

    async def test_create_task_as_admin(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test that an admin can create a task."""
        r = await async_client.post(
            "/api/v1/tasks/",
            json={
                "name": "Admin Task",
                "start_date": "2026-07-01",
                "end_date": "2026-07-03",
            },
        )

        assert r.status_code == 201
        assert r.json()["name"] == "Admin Task"
        assert r.json()["status"] == "draft"

    async def test_update_task_as_admin(
        self, async_client: AsyncClient, test_task: Task, as_admin: None
    ):
        """Test that an admin can update a task."""
        r = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}",
            json={"name": "Updated Task Name"},
        )

        assert r.status_code == 200
        assert r.json()["name"] == "Updated Task Name"

    async def test_delete_task_as_admin(
        self, async_client: AsyncClient, test_task: Task, as_admin: None
    ):
        """Test that an admin can delete a task."""
        r = await async_client.delete(f"/api/v1/tasks/{test_task.id}")

        assert r.status_code == 204

    async def test_list_tasks_with_search(
        self, async_client: AsyncClient, test_task: Task
    ):
        """Test searching tasks by name."""
        r = await async_client.get("/api/v1/tasks/", params={"search": "Pfingsten"})

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert any(item["name"] == test_task.name for item in data["items"])

    async def test_get_nonexistent_task(self, async_client: AsyncClient):
        """Test getting a non-existent task returns 404."""
        import uuid

        fake_id = uuid.uuid4()
        r = await async_client.get(f"/api/v1/tasks/{fake_id}")

        assert r.status_code == 404

    async def test_create_task_with_shifts(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test creating a task with auto-generated duty shifts."""
        r = await async_client.post(
            "/api/v1/tasks/with-shifts",
            json={
                "name": "Bierstand",
                "description": "Beer stand duty",
                "start_date": "2026-06-01",
                "end_date": "2026-06-02",
                "location": "Halle A",
                "category": "Bar",
                "schedule": {
                    "default_start_time": "10:00:00",
                    "default_end_time": "12:00:00",
                    "shift_duration_minutes": 60,
                    "people_per_shift": 3,
                },
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["task"]["name"] == "Bierstand"
        assert data["task"]["location"] == "Halle A"
        assert data["task"]["shift_duration_minutes"] == 60
        assert data["task"]["people_per_shift"] == 3
        assert data["shifts_created"] == 4  # 2 days * 2 shifts/day
        assert data["event"] is None

    async def test_create_task_with_shifts_and_new_group(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test creating a task with shifts and a new event."""
        r = await async_client.post(
            "/api/v1/tasks/with-shifts",
            json={
                "name": "Weinstand",
                "start_date": "2026-06-01",
                "end_date": "2026-06-01",
                "new_event": {
                    "name": "Sommerfest 2026",
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-03",
                },
                "schedule": {
                    "default_start_time": "18:00:00",
                    "default_end_time": "20:00:00",
                    "shift_duration_minutes": 30,
                    "people_per_shift": 2,
                },
            },
        )

        assert r.status_code == 201
        data = r.json()
        assert data["task"]["name"] == "Weinstand"
        assert data["event"] is not None
        assert data["event"]["name"] == "Sommerfest 2026"
        assert data["task"]["event_id"] == data["event"]["id"]
        assert data["shifts_created"] == 4  # 2 hours / 30 min

    async def test_create_task_with_shifts_and_overrides(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test per-date schedule overrides."""
        r = await async_client.post(
            "/api/v1/tasks/with-shifts",
            json={
                "name": "Kasse",
                "start_date": "2026-06-01",
                "end_date": "2026-06-02",
                "schedule": {
                    "default_start_time": "10:00:00",
                    "default_end_time": "12:00:00",
                    "shift_duration_minutes": 60,
                    "people_per_shift": 1,
                    "overrides": [
                        {
                            "date": "2026-06-02",
                            "start_time": "14:00:00",
                            "end_time": "18:00:00",
                        }
                    ],
                },
            },
        )

        assert r.status_code == 201
        data = r.json()
        # Day 1: 10-12 = 2 shifts, Day 2: 14-18 = 4 shifts
        assert data["shifts_created"] == 6


@pytest.mark.asyncio
class TestTasksEventAdminRole:
    """Managing tasks is scoped to the event they belong to."""

    async def test_create_task_in_my_event(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_event_admin: None,
    ):
        """An event admin can create tasks inside the event they run."""
        r = await async_client.post(
            "/api/v1/tasks/",
            json={
                "name": "Manager Task",
                "start_date": "2026-06-11",
                "end_date": "2026-06-12",
                "event_id": str(test_event.id),
            },
        )

        assert r.status_code == 201
        assert r.json()["name"] == "Manager Task"

    async def test_create_task_without_an_event_is_refused(
        self,
        async_client: AsyncClient,
        test_event: Event,
        as_event_admin: None,
    ):
        """Every task must belong to an event that grants the right to make it.

        An event-less task would sit outside the permission model entirely, so
        only the platform superadmin may create one.
        """
        r = await async_client.post(
            "/api/v1/tasks/",
            json={
                "name": "Orphan Task",
                "start_date": "2026-08-01",
                "end_date": "2026-08-02",
            },
        )

        assert r.status_code == 403

    async def test_create_task_as_normal_user_raises_403(
        self,
        async_client: AsyncClient,
    ):
        """Test that a plain user cannot create tasks without group assignment."""
        r = await async_client.post(
            "/api/v1/tasks/",
            json={
                "name": "Unauthorized Task",
                "start_date": "2026-08-01",
                "end_date": "2026-08-02",
            },
        )

        assert r.status_code == 403

    async def test_update_task_as_event_admin(
        self,
        async_client: AsyncClient,
        test_task: Task,
        as_event_admin: None,
    ):
        """Test that an event admin can update any task in their event."""
        r = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}",
            json={"name": "Updated by Manager"},
        )

        assert r.status_code == 200
        assert r.json()["name"] == "Updated by Manager"

    async def test_update_task_as_normal_user_raises_403(
        self,
        async_client: AsyncClient,
        test_task: Task,
    ):
        """Test that a plain user cannot update tasks."""
        r = await async_client.patch(
            f"/api/v1/tasks/{test_task.id}",
            json={"name": "Should Fail"},
        )

        assert r.status_code == 403

    async def test_delete_task_as_event_admin(
        self,
        async_client: AsyncClient,
        test_task: Task,
        as_event_admin: None,
    ):
        """Test that an event admin can delete any task in their event."""
        r = await async_client.delete(f"/api/v1/tasks/{test_task.id}")

        assert r.status_code == 204

    async def test_delete_task_as_normal_user_raises_403(
        self,
        async_client: AsyncClient,
        test_task: Task,
    ):
        """Test that a plain user cannot delete tasks."""
        r = await async_client.delete(f"/api/v1/tasks/{test_task.id}")

        assert r.status_code == 403

    async def test_event_admin_can_manage_tasks_in_their_event(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event_admin_user: User,
        test_event: Event,
        as_event_admin: None,
    ):
        """An admin membership is enough to edit that event's tasks."""
        from datetime import date

        from app.models.task import Task as TaskModel

        task = TaskModel(
            name="Group Task",
            start_date=date(2026, 6, 11),
            end_date=date(2026, 6, 11),
            status="published",
            created_by_id=test_event_admin_user.id,
            event_id=test_event.id,
        )
        db_session.add(task)
        await db_session.flush()
        await db_session.refresh(task)

        r = await async_client.patch(
            f"/api/v1/tasks/{task.id}", json={"name": "Renamed by Event Admin"}
        )

        assert r.status_code == 200
        assert r.json()["name"] == "Renamed by Event Admin"

    async def test_event_admin_cannot_manage_another_events_task(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event_admin_user: User,
        test_event: Event,
        as_event_admin: None,
    ):
        """An admin membership grants nothing outside its own event."""
        from datetime import date

        from app.models.event import Event as EventModel
        from app.models.task import Task as TaskModel

        other_event = EventModel(
            name="Someone Else's Event",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
            status="published",
            visibility="private",
        )
        db_session.add(other_event)
        await db_session.flush()

        task = TaskModel(
            name="Other Group Task",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            status="published",
            created_by_id=test_event_admin_user.id,
            event_id=other_event.id,
        )
        db_session.add(task)
        await db_session.flush()
        await db_session.refresh(task)

        r = await async_client.patch(
            f"/api/v1/tasks/{task.id}", json={"name": "Should Fail"}
        )

        assert r.status_code == 403
