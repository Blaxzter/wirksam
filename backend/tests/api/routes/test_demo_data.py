"""Tests for the superadmin demo-data generator's use of locations."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.location import Location
from app.models.shift import Shift
from app.models.task import Task
from app.schemas.demo_data import DEMO_PREFIX


async def _demo_tasks(db: AsyncSession) -> list[Task]:
    result = await db.execute(
        select(Task).where(col(Task.name).startswith(DEMO_PREFIX))
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
class TestDemoDataLocations:
    async def test_tasks_in_an_event_link_a_location_of_that_event(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_admin: None,
    ):
        r = await async_client.post(
            "/api/v1/demo-data/",
            json={"num_events": 2, "num_tasks": 6, "num_users": 0},
        )
        assert r.status_code == 200, r.text

        tasks = await _demo_tasks(db_session)
        assert len(tasks) == 6
        locations = {
            loc.id: loc
            for loc in (
                await db_session.execute(
                    select(Location).where(
                        col(Location.event_id).in_({t.event_id for t in tasks})
                    )
                )
            ).scalars()
        }
        # One row per (event, name) actually used, never a duplicate.
        pairs = [(loc.event_id, loc.name) for loc in locations.values()]
        assert len(pairs) == len(set(pairs))
        for task in tasks:
            assert task.location_id is not None
            loc = locations[task.location_id]
            assert (loc.event_id, loc.name) == (task.event_id, task.location)

            shifts = (
                await db_session.execute(
                    select(Shift).where(col(Shift.task_id) == task.id)
                )
            ).scalars()
            assert all(s.location_id == task.location_id for s in shifts)

        # And the cleanup still goes through with the links in place.
        r = await async_client.delete("/api/v1/demo-data/")
        assert r.status_code == 200, r.text
        await db_session.flush()
        await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        assert await _demo_tasks(db_session) == []

    async def test_tasks_without_an_event_keep_plain_text(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_admin: None,
    ):
        r = await async_client.post(
            "/api/v1/demo-data/",
            json={"num_events": 0, "num_tasks": 2, "num_users": 0},
        )
        assert r.status_code == 200, r.text

        tasks = await _demo_tasks(db_session)
        assert len(tasks) == 2
        assert all(t.location and t.location_id is None for t in tasks)
