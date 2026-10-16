"""Route tests for worked hours and manual work-log entries."""

import datetime as dt
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.booking import Booking
from app.models.event import Event
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.models.work_log import WorkLog


async def _book(
    db: AsyncSession,
    task: Task,
    user: User,
    *,
    date: dt.date,
    start: dt.time | None,
    end: dt.time | None,
    status: str = "confirmed",
) -> Booking:
    shift = Shift(
        task_id=task.id,
        title=f"Shift {uuid.uuid4().hex[:6]}",
        date=date,
        start_time=start,
        end_time=end,
        max_bookings=5,
    )
    db.add(shift)
    await db.flush()
    booking = Booking(shift_id=shift.id, user_id=user.id, status=status)
    db.add(booking)
    await db.flush()
    return booking


async def _log(
    db: AsyncSession,
    event: Event,
    user: User,
    minutes: int,
    *,
    created_by: User | None = None,
) -> WorkLog:
    entry = WorkLog(
        event_id=event.id,
        user_id=user.id,
        date=dt.date(2026, 6, 10),
        minutes=minutes,
        description="Aufbau",
        created_by_id=created_by.id if created_by else None,
        created_by_name=created_by.name if created_by else None,
    )
    db.add(entry)
    await db.flush()
    return entry


PAST = dt.date(2020, 6, 1)
FUTURE = dt.date(2099, 6, 1)


def _row_for(rows: list[dict[str, Any]], user: User) -> dict[str, Any]:
    return next(r for r in rows if r["user_id"] == str(user.id))


@pytest.mark.asyncio
class TestEventHours:
    async def test_admin_sees_hours_for_every_member(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_user: User,
        test_event_admin_user: User,
        as_event_admin: None,
    ):
        await _book(
            db_session,
            test_task,
            test_user,
            date=PAST,
            start=dt.time(8),
            end=dt.time(12),
        )
        await _book(
            db_session,
            test_task,
            test_user,
            date=PAST,
            start=dt.time(22),
            end=dt.time(1),
        )
        await _log(
            db_session, test_event, test_user, 90, created_by=test_event_admin_user
        )

        r = await async_client.get(f"/api/v1/events/{test_event.id}/hours")

        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 3  # owner, admin, member — zeros included
        mine = _row_for(rows, test_user)
        assert mine["shift_count"] == 2
        assert mine["shift_minutes"] == 4 * 60 + 3 * 60
        assert mine["manual_minutes"] == 90
        assert mine["total_minutes"] == 7 * 60 + 90
        assert mine["role"] == "member"
        # Highest total first.
        assert rows[0]["user_id"] == str(test_user.id)

    async def test_upcoming_and_cancelled_shifts_do_not_count(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_user: User,
        as_event_admin: None,
    ):
        await _book(
            db_session,
            test_task,
            test_user,
            date=FUTURE,
            start=dt.time(8),
            end=dt.time(10),
        )
        await _book(
            db_session,
            test_task,
            test_user,
            date=PAST,
            start=dt.time(8),
            end=dt.time(10),
            status="cancelled",
        )

        r = await async_client.get(f"/api/v1/events/{test_event.id}/hours")

        mine = _row_for(r.json(), test_user)
        assert mine["shift_minutes"] == 0
        assert mine["total_minutes"] == 0
        assert mine["upcoming_shift_count"] == 1
        assert mine["upcoming_shift_minutes"] == 120

    async def test_untimed_shift_is_counted_but_flagged(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_user: User,
        as_event_admin: None,
    ):
        await _book(db_session, test_task, test_user, date=PAST, start=None, end=None)

        r = await async_client.get(f"/api/v1/events/{test_event.id}/hours")

        mine = _row_for(r.json(), test_user)
        assert mine["shift_count"] == 1
        assert mine["shift_minutes"] == 0
        assert mine["untimed_shift_count"] == 1

    async def test_former_member_with_hours_stays_on_the_list(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_outsider_user: User,
        as_event_admin: None,
    ):
        """Leaving the event does not undo the work already done."""
        await _book(
            db_session,
            test_task,
            test_outsider_user,
            date=PAST,
            start=dt.time(8),
            end=dt.time(9),
        )

        r = await async_client.get(f"/api/v1/events/{test_event.id}/hours")

        row = _row_for(r.json(), test_outsider_user)
        assert row["role"] is None
        assert row["total_minutes"] == 60

    async def test_other_events_do_not_leak_in(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_private_event: Event,
        test_user: User,
        as_event_admin: None,
    ):
        other_task = Task(
            name="Elsewhere",
            start_date=PAST,
            end_date=PAST,
            status="published",
            event_id=test_private_event.id,
        )
        db_session.add(other_task)
        await db_session.flush()
        await _book(
            db_session,
            other_task,
            test_user,
            date=PAST,
            start=dt.time(8),
            end=dt.time(12),
        )
        await _log(db_session, test_private_event, test_user, 30)

        r = await async_client.get(f"/api/v1/events/{test_event.id}/hours")

        assert _row_for(r.json(), test_user)["total_minutes"] == 0

    async def test_plain_member_cannot_see_everyones_hours(
        self,
        async_client: AsyncClient,
        test_event: Event,
    ):
        r = await async_client.get(f"/api/v1/events/{test_event.id}/hours")

        assert r.status_code == 403

    async def test_outsider_gets_404_on_private_event(
        self,
        async_client: AsyncClient,
        test_private_event: Event,
        as_outsider: None,
    ):
        r = await async_client.get(f"/api/v1/events/{test_private_event.id}/hours")

        assert r.status_code == 404

    async def test_csv_export(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_user: User,
        as_event_admin: None,
    ):
        await _book(
            db_session,
            test_task,
            test_user,
            date=PAST,
            start=dt.time(8),
            end=dt.time(10),
        )
        await _log(db_session, test_event, test_user, 30)

        r = await async_client.get(f"/api/v1/events/{test_event.id}/hours/export")

        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        lines = r.text.strip().splitlines()
        assert lines[0].startswith("Volunteer Name,Volunteer Email,Role")
        assert "Test User,test@example.com,member,1,2.00,0.50,2.50,0,0.00" in lines

    async def test_csv_export_needs_admin(
        self,
        async_client: AsyncClient,
        test_event: Event,
    ):
        r = await async_client.get(f"/api/v1/events/{test_event.id}/hours/export")

        assert r.status_code == 403


@pytest.mark.asyncio
class TestVolunteerHours:
    async def test_member_reads_own_breakdown(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_user: User,
    ):
        await _book(
            db_session,
            test_task,
            test_user,
            date=PAST,
            start=dt.time(8),
            end=dt.time(12),
        )
        await _book(
            db_session,
            test_task,
            test_user,
            date=FUTURE,
            start=dt.time(8),
            end=dt.time(9),
        )
        await _log(db_session, test_event, test_user, 45)

        r = await async_client.get(
            f"/api/v1/events/{test_event.id}/hours/{test_user.id}"
        )

        assert r.status_code == 200
        body = r.json()
        assert body["summary"]["total_minutes"] == 4 * 60 + 45
        assert [s["completed"] for s in body["shifts"]] == [True, False]
        assert body["shifts"][0]["task_name"] == test_task.name
        assert [w["minutes"] for w in body["work_logs"]] == [45]

    async def test_member_cannot_read_someone_elses(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_event_admin_user: User,
    ):
        r = await async_client.get(
            f"/api/v1/events/{test_event.id}/hours/{test_event_admin_user.id}"
        )

        assert r.status_code == 403

    async def test_admin_reads_a_members(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_user: User,
        as_event_admin: None,
    ):
        r = await async_client.get(
            f"/api/v1/events/{test_event.id}/hours/{test_user.id}"
        )

        assert r.status_code == 200
        assert r.json()["summary"]["user_id"] == str(test_user.id)


@pytest.mark.asyncio
class TestWorkLogs:
    async def test_admin_creates_an_entry(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        test_event_admin_user: User,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/work-logs",
            json={
                "user_id": str(test_user.id),
                "date": "2026-06-09",
                "minutes": 150,
                "description": "  Aufbau am Vortag  ",
            },
        )

        assert r.status_code == 201
        body = r.json()
        assert body["minutes"] == 150
        assert body["description"] == "Aufbau am Vortag"
        assert body["created_by_id"] == str(test_event_admin_user.id)
        assert body["created_by_name"] == test_event_admin_user.name

    async def test_member_cannot_credit_themselves(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_user: User,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/work-logs",
            json={
                "user_id": str(test_user.id),
                "date": "2026-06-09",
                "minutes": 60,
                "description": "Trust me",
            },
        )

        assert r.status_code == 403

    async def test_entry_must_target_a_member(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_outsider_user: User,
        as_event_admin: None,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/work-logs",
            json={
                "user_id": str(test_outsider_user.id),
                "date": "2026-06-09",
                "minutes": 60,
                "description": "Aufbau",
            },
        )

        assert r.status_code == 404
        assert r.json()["code"] == "event.member_not_found"

    @pytest.mark.parametrize("minutes", [0, -5, 24 * 60 + 1])
    async def test_minutes_out_of_range_rejected(
        self,
        async_client: AsyncClient,
        test_event: Event,
        test_user: User,
        as_event_admin: None,
        minutes: int,
    ):
        r = await async_client.post(
            f"/api/v1/events/{test_event.id}/work-logs",
            json={
                "user_id": str(test_user.id),
                "date": "2026-06-09",
                "minutes": minutes,
                "description": "Aufbau",
            },
        )

        assert r.status_code == 422

    async def test_admin_updates_and_deletes(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        as_event_admin: None,
    ):
        entry = await _log(db_session, test_event, test_user, 60)
        url = f"/api/v1/events/{test_event.id}/work-logs/{entry.id}"

        r = await async_client.patch(url, json={"minutes": 75})
        assert r.status_code == 200
        assert r.json()["minutes"] == 75
        assert r.json()["description"] == "Aufbau"

        r = await async_client.delete(url)
        assert r.status_code == 204
        assert await db_session.get(WorkLog, entry.id) is None

    async def test_entry_from_another_event_is_not_found(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_private_event: Event,
        test_event_admin_user: User,
        as_event_admin: None,
    ):
        """An admin of both events still cannot reach one's entry via the other."""
        entry = await _log(db_session, test_private_event, test_event_admin_user, 60)

        r = await async_client.delete(
            f"/api/v1/events/{test_event.id}/work-logs/{entry.id}"
        )

        assert r.status_code == 404
        assert r.json()["code"] == "work_log.not_found"


@pytest.mark.asyncio
class TestWorkLogDeletionCascades:
    async def test_deleting_the_admin_keeps_the_entry(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
        test_event_admin_user: User,
    ):
        entry = await _log(
            db_session, test_event, test_user, 60, created_by=test_event_admin_user
        )
        entry_id, admin_name = entry.id, test_event_admin_user.name

        await db_session.execute(
            delete(User).where(col(User.id) == test_event_admin_user.id)
        )
        await db_session.flush()

        db_session.expire_all()
        kept = await db_session.get(WorkLog, entry_id)
        assert kept is not None
        assert kept.created_by_name == admin_name

    async def test_deleting_the_volunteer_removes_their_entries(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ):
        entry = await _log(db_session, test_event, test_user, 60)
        entry_id = entry.id

        await db_session.execute(delete(User).where(col(User.id) == test_user.id))
        await db_session.flush()

        result = await db_session.execute(
            select(WorkLog).where(col(WorkLog.id) == entry_id)
        )
        assert result.scalar_one_or_none() is None
