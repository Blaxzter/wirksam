"""Removing a shift tells the people whose bookings end with it (finding #5).

The dispatcher itself is covered in ``tests/logic/test_notification_triggers.py``.
Here it is replaced by a recorder, so each test asserts what every route that
removes shifts *asked* it to do.

The cast, all in ``test_event``: ``test_event_admin_user`` is the organiser and
``test_user`` a member with a booking on ``shift``.
"""

import datetime as dt
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import shifts as shift_routes
from app.api.routes.tasks import batches as batch_routes
from app.api.routes.tasks import crud as task_routes
from app.api.routes.tasks import shifts as task_shift_routes
from app.models.booking import Booking
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User

pytestmark = pytest.mark.usefixtures("clock_before_fixture_shifts")

Calls = list[dict[str, Any]]

SCHEDULE: dict[str, Any] = {
    "default_start_time": "14:00:00",
    "default_end_time": "16:00:00",
    "shift_duration_minutes": 120,
    "people_per_shift": 1,
}


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> Calls:
    """Record the dispatches; the route modules import the dispatcher by name."""
    calls: Calls = []

    async def _record(**kwargs: Any) -> None:
        calls.append(kwargs)

    for module in (shift_routes, batch_routes, task_routes, task_shift_routes):
        monkeypatch.setattr(module, "dispatch_booking_cancelled_by_admin", _record)
    return calls


@pytest_asyncio.fixture
async def batch(db_session: AsyncSession, test_task: Task) -> ShiftBatch:
    row = ShiftBatch(
        task_id=test_task.id,
        label="Morgens",
        start_date=dt.date(2026, 6, 11),
        end_date=dt.date(2026, 6, 11),
        default_start_time=dt.time(8, 0),
        default_end_time=dt.time(12, 0),
        shift_duration_minutes=240,
        people_per_shift=2,
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def shift(db_session: AsyncSession, test_task: Task, batch: ShiftBatch) -> Shift:
    row = Shift(
        task_id=test_task.id,
        batch_id=batch.id,
        title="Pfingsten 2026 08:00-12:00",
        date=dt.date(2026, 6, 11),
        start_time=dt.time(8, 0),
        end_time=dt.time(12, 0),
        max_bookings=2,
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def booking(db_session: AsyncSession, shift: Shift, test_user: User) -> Booking:
    row = Booking(shift_id=shift.id, user_id=test_user.id, status="confirmed")
    db_session.add(row)
    await db_session.flush()
    return row


def _assert_told_about(call: dict[str, Any], booking: Booking, shift: Shift) -> None:
    [cancelled] = call["cancelled"]
    assert cancelled.booking_id == booking.id
    assert cancelled.user_id == booking.user_id
    assert cancelled.shift_title == shift.title
    assert cancelled.shift_date == shift.date


@pytest.mark.asyncio
class TestRemovingShiftsTellsTheBookers:
    async def test_deleting_a_shift(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        queued: Calls,
        test_event_admin_user: User,
        test_task: Task,
        shift: Shift,
        booking: Booking,
    ) -> None:
        r = await async_client.delete(
            f"/api/v1/shifts/{shift.id}",
            params={"cancellation_reason": "Zu wenig Besucher"},
        )

        assert r.status_code == 204, r.text
        [call] = queued
        _assert_told_about(call, booking, shift)
        assert call["actor_id"] == test_event_admin_user.id
        assert call["task_id"] == test_task.id
        assert call["task_name"] == test_task.name
        assert call["task_is_open"] is True
        assert call["event_id"] == test_task.event_id
        assert call["reason"] == "Zu wenig Besucher"
        assert call["is_sandbox"] is False

    async def test_deleting_a_batch(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        queued: Calls,
        test_task: Task,
        batch: ShiftBatch,
        shift: Shift,
        booking: Booking,
    ) -> None:
        r = await async_client.delete(
            f"/api/v1/tasks/{test_task.id}/batches/{batch.id}",
            params={"cancellation_reason": "Regen"},
        )

        assert r.status_code == 204, r.text
        [call] = queued
        _assert_told_about(call, booking, shift)
        assert call["task_is_open"] is True
        assert call["reason"] == "Regen"

    async def test_deleting_a_task_opens_my_bookings_instead(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        queued: Calls,
        test_task: Task,
        shift: Shift,
        booking: Booking,
    ) -> None:
        """The task's page is gone, so the notice must not lead to it."""
        task_name = test_task.name
        r = await async_client.delete(f"/api/v1/tasks/{test_task.id}")

        assert r.status_code == 204, r.text
        [call] = queued
        _assert_told_about(call, booking, shift)
        assert call["task_is_open"] is False
        assert call["task_name"] == task_name

    async def test_regenerating(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        queued: Calls,
        test_task: Task,
        shift: Shift,
        booking: Booking,
    ) -> None:
        """Different times mean the booked shift goes."""
        r = await async_client.post(
            f"/api/v1/tasks/{test_task.id}/regenerate-shifts",
            json={"schedule": SCHEDULE},
        )

        assert r.status_code == 200, r.text
        assert r.json()["shifts_removed"] >= 1
        [call] = queued
        _assert_told_about(call, booking, shift)
        assert call["task_is_open"] is True

    async def test_the_dry_run_of_regenerating_tells_nobody(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        queued: Calls,
        test_task: Task,
        shift: Shift,
        booking: Booking,
    ) -> None:
        r = await async_client.post(
            f"/api/v1/tasks/{test_task.id}/regenerate-shifts",
            params={"dry_run": True},
            json={"schedule": SCHEDULE},
        )

        assert r.status_code == 200, r.text
        assert len(r.json()["affected_bookings"]) == 1
        assert queued == []

    async def test_a_draft_task_is_not_linked(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        queued: Calls,
        db_session: AsyncSession,
        test_task: Task,
        shift: Shift,
        booking: Booking,
    ) -> None:
        """A booker can't open a draft, so the notice opens My Bookings."""
        test_task.status = "draft"
        db_session.add(test_task)
        await db_session.flush()

        r = await async_client.delete(f"/api/v1/shifts/{shift.id}")

        assert r.status_code == 204, r.text
        assert queued[0]["task_is_open"] is False

    async def test_a_demo_is_flagged_so_the_dispatcher_stops(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        queued: Calls,
        db_session: AsyncSession,
        test_task: Task,
        shift: Shift,
        booking: Booking,
    ) -> None:
        test_task.is_sandbox = True
        db_session.add(test_task)
        await db_session.flush()

        r = await async_client.delete(f"/api/v1/shifts/{shift.id}")

        assert r.status_code == 204, r.text
        assert queued[0]["is_sandbox"] is True

    async def test_a_cancelled_booking_is_not_cancelled_twice(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        queued: Calls,
        db_session: AsyncSession,
        test_task: Task,
        shift: Shift,
        booking: Booking,
    ) -> None:
        """Someone who already cancelled their booking has nothing to hear."""
        booking.status = "cancelled"
        db_session.add(booking)
        await db_session.flush()

        r = await async_client.delete(f"/api/v1/shifts/{shift.id}")

        assert r.status_code == 204, r.text
        assert queued[0]["cancelled"] == []
