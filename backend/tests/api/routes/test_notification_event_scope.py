"""The routes name the event, so muting a whole event quiets these notices too.

The dispatchers are covered in ``tests/logic/test_notification_triggers.py``,
including that a mute on the event they are given applies. Here they are replaced
by recorders, so each test asserts that the route gave them the event at all.
"""

import datetime as dt
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.api.routes import bookings as bookings_routes
from app.logic.notifications import triggers
from app.models.booking import Booking
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from tests.fixtures.client import act_as

pytestmark = pytest.mark.usefixtures("clock_before_fixture_shifts")

Calls = dict[str, list[dict[str, Any]]]


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> Calls:
    calls: Calls = {"cobooked": [], "cancelled": [], "time_changed": []}

    def _recorder(name: str) -> Any:
        async def _record(**kwargs: Any) -> None:
            calls[name].append(kwargs)

        return _record

    async def _confirmed(**_: Any) -> None:
        return None

    monkeypatch.setattr(bookings_routes, "dispatch_booking_confirmed", _confirmed)
    monkeypatch.setattr(
        bookings_routes, "dispatch_booking_cobooked", _recorder("cobooked")
    )
    monkeypatch.setattr(
        bookings_routes, "dispatch_booking_cancelled_by_user", _recorder("cancelled")
    )
    # The shift route imports this one where it needs it.
    monkeypatch.setattr(
        triggers, "dispatch_shift_time_changed", _recorder("time_changed")
    )
    return calls


@pytest_asyncio.fixture
async def shift(db_session: AsyncSession, test_task: Task) -> Shift:
    row = Shift(
        task_id=test_task.id,
        title="Bar 10:00-12:00",
        date=dt.date(2026, 6, 11),
        start_time=dt.time(10, 0),
        end_time=dt.time(12, 0),
        max_bookings=5,
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def second_booker(
    db_session: AsyncSession, test_event: Event, shift: Shift
) -> User:
    user = User(
        subject="local|second-booker",
        email="second.booker@example.com",
        name="Second",
        roles=[],
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(EventMembership(user_id=user.id, event_id=test_event.id))
    db_session.add(Booking(shift_id=shift.id, user_id=user.id, status="confirmed"))
    await db_session.flush()
    return user


@pytest.mark.asyncio
class TestTheRoutesNameTheEvent:
    async def test_someone_booking_your_shift(
        self,
        async_client: AsyncClient,
        queued: Calls,
        test_event: Event,
        shift: Shift,
        second_booker: User,
    ) -> None:
        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(shift.id)}
        )

        assert r.status_code == 201, r.text
        [call] = queued["cobooked"]
        assert call["existing_user_ids"] == [second_booker.id]
        assert call["event_id"] == test_event.id

    async def test_cancelling_your_booking(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        queued: Calls,
        db_session: AsyncSession,
        test_event: Event,
        shift: Shift,
        second_booker: User,
    ) -> None:
        rows = await db_session.execute(
            select(col(Booking.id)).where(col(Booking.user_id) == second_booker.id)
        )
        booking_id = rows.scalar_one()

        with act_as(app, second_booker):
            r = await async_client.delete(f"/api/v1/bookings/{booking_id}")

        assert r.status_code == 200, r.text
        [call] = queued["cancelled"]
        assert call["event_id"] == test_event.id

    async def test_a_shifts_time_changing(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        queued: Calls,
        test_event: Event,
        shift: Shift,
        second_booker: User,
    ) -> None:
        r = await async_client.patch(
            f"/api/v1/shifts/{shift.id}", json={"start_time": "09:00:00"}
        )

        assert r.status_code == 200, r.text
        [call] = queued["time_changed"]
        assert call["booked_user_ids"] == [second_booker.id]
        assert call["event_id"] == test_event.id
