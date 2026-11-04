"""A time zone per event: the zone has to change the outcome.

Both clocks are frozen at one instant, 2026-07-01 03:00 UTC, and each zone reads
it on its own clock:

* ``Asia/Tokyo``: 12:00 on 1 July
* ``Europe/Berlin`` (the default ``test_event`` is in): 05:00 on 1 July
* ``Europe/Lisbon``: 04:00 on 1 July
* ``Pacific/Honolulu``: 17:00 on 30 June
"""

import datetime as dt
from collections.abc import Callable, Generator, Iterator
from contextlib import AbstractContextManager, contextmanager
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.logic import work_hours
from app.logic.booking_conflicts import find_conflicting_booking, mark_collisions
from app.models.booking import Booking
from app.models.booking_reminder import BookingReminder
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.event_team import (
    EventTeam,
    EventTeamCheck,
    EventTeamMember,
    EventTeamRequirement,
)
from app.models.location import Location
from app.models.shift import Shift
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from app.models.voucher import VoucherEarning, VoucherEntry
from app.schemas.booking_reminder import ReminderOffsetEntry
from tests.fixtures.client import act_as
from tests.fixtures.clock import set_instant

INSTANT = dt.datetime(2026, 7, 1, 3, 0)
JULY_1 = dt.date(2026, 7, 1)
JUNE_30 = dt.date(2026, 6, 30)
LATER = dt.date(2026, 7, 10)

CountQueries = Callable[[], AbstractContextManager[list[str]]]

TOKYO = "Asia/Tokyo"
LISBON = "Europe/Lisbon"
HONOLULU = "Pacific/Honolulu"
BERLIN = "Europe/Berlin"


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    assert settings.EVENT_TIMEZONE == BERLIN
    set_instant(monkeypatch, INSTANT)


async def _event(
    db: AsyncSession, owner: User, member: User, *, zone: str, name: str | None = None
) -> Event:
    event = Event(
        name=name or f"Event in {zone}",
        start_date=dt.date(2026, 6, 1),
        end_date=dt.date(2026, 7, 31),
        status="published",
        visibility="public",
        created_by_id=owner.id,
        timezone=zone,
    )
    db.add(event)
    await db.flush()
    db.add(EventMembership(user_id=owner.id, event_id=event.id, role="owner"))
    db.add(EventMembership(user_id=member.id, event_id=event.id, role="member"))
    await db.flush()
    return event


async def _task(
    db: AsyncSession,
    event: Event | None,
    owner: User,
    *,
    vouchers: int = 0,
    point: bool = False,
    end_date: dt.date = dt.date(2026, 7, 31),
) -> Task:
    task = Task(
        name=f"Task in {event.timezone if event else 'no event'}",
        start_date=dt.date(2026, 6, 1),
        end_date=end_date,
        status="published",
        created_by_id=owner.id,
        event_id=event.id if event else None,
        vouchers_per_shift=vouchers,
        is_voucher_point=point,
    )
    db.add(task)
    await db.flush()
    return task


async def _shift(
    db: AsyncSession,
    task: Task,
    date: dt.date,
    start: dt.time | None,
    end: dt.time | None,
) -> Shift:
    shift = Shift(
        task_id=task.id,
        title=f"Shift of {task.name}",
        date=date,
        start_time=start,
        end_time=end,
        max_bookings=2,
    )
    db.add(shift)
    await db.flush()
    return shift


async def _book(
    db: AsyncSession, shift: Shift, user: User, *, status: str = "confirmed"
) -> Booking:
    booking = Booking(shift_id=shift.id, user_id=user.id, status=status)
    db.add(booking)
    await db.flush()
    return booking


@pytest_asyncio.fixture
async def tokyo(
    db_session: AsyncSession, test_admin_user: User, test_user: User
) -> Event:
    return await _event(db_session, test_admin_user, test_user, zone=TOKYO)


@pytest_asyncio.fixture
async def lisbon(
    db_session: AsyncSession, test_admin_user: User, test_user: User
) -> Event:
    return await _event(db_session, test_admin_user, test_user, zone=LISBON)


@pytest_asyncio.fixture
async def honolulu(
    db_session: AsyncSession, test_admin_user: User, test_user: User
) -> Event:
    return await _event(db_session, test_admin_user, test_user, zone=HONOLULU)


@pytest.fixture
def as_organiser(app: FastAPI, test_admin_user: User) -> Iterator[None]:
    """The owner of ``test_event`` and of every event ``_event`` makes here."""
    with act_as(app, test_admin_user):
        yield


# ── The field ─────────────────────────────────────────────────────


BASE_EVENT = {"name": "Festival", "start_date": "2026-08-01", "end_date": "2026-08-02"}


@pytest.mark.asyncio
@pytest.mark.usefixtures("as_organiser")
class TestTheField:
    async def test_a_new_event_starts_with_the_setting(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.post("/api/v1/events/", json=BASE_EVENT)
        assert r.status_code == 201, r.text
        assert r.json()["timezone"] == settings.EVENT_TIMEZONE

    async def test_a_new_event_can_say_its_zone(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.post(
            "/api/v1/events/", json={**BASE_EVENT, "timezone": TOKYO}
        )
        assert r.status_code == 201, r.text
        assert r.json()["timezone"] == TOKYO

    @pytest.mark.parametrize(
        "zone",
        ["Mars/Olympus_Mons", "", "Europe", "../etc/passwd", "A" * 65, "Asia/Tokyo/x"],
    )
    async def test_an_unknown_zone_is_refused(
        self, async_client: AsyncClient, test_event: Event, zone: str
    ) -> None:
        created = await async_client.post(
            "/api/v1/events/", json={**BASE_EVENT, "timezone": zone}
        )
        assert created.status_code == 422, created.text
        updated = await async_client.patch(
            f"/api/v1/events/{test_event.id}", json={"timezone": zone}
        )
        assert updated.status_code == 422, updated.text

    async def test_a_zone_can_be_changed(
        self, async_client: AsyncClient, test_event: Event
    ) -> None:
        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}", json={"timezone": TOKYO}
        )
        assert r.status_code == 200, r.text
        assert r.json()["timezone"] == TOKYO
        read = await async_client.get(f"/api/v1/events/{test_event.id}")
        assert read.json()["timezone"] == TOKYO

    async def test_an_explicit_null_leaves_it(
        self, async_client: AsyncClient, tokyo: Event
    ) -> None:
        r = await async_client.patch(
            f"/api/v1/events/{tokyo.id}", json={"timezone": None}
        )
        assert r.status_code == 200, r.text
        assert r.json()["timezone"] == TOKYO

    async def test_a_single_task_read_names_its_events_zone(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        test_admin_user: User,
    ) -> None:
        task = await _task(db_session, tokyo, test_admin_user)
        r = await async_client.get(f"/api/v1/tasks/{task.id}")
        assert r.status_code == 200, r.text
        assert r.json()["event_timezone"] == TOKYO


# ── Reminders ─────────────────────────────────────────────────────


async def _reminder(
    db: AsyncSession,
    shift: Shift,
    booking: Booking,
    user: User,
    *,
    zone: str | None,
    offset: int = 60,
    status: str | None = None,
) -> BookingReminder:
    reminder = await crud_reminder.create_reminder(
        db,
        booking_id=booking.id,
        user_id=user.id,
        shift_id=shift.id,
        offset_minutes=offset,
        slot_start=dt.datetime.combine(shift.date, shift.start_time or dt.time()),
        zone=zone,
    )
    if status is not None:
        reminder.status = status
        db.add(reminder)
        await db.flush()
    return reminder


@pytest.mark.asyncio
@pytest.mark.usefixtures("as_organiser")
class TestReminders:
    """A 10:00 shift on 10 July, one hour's notice: 00:00 UTC in Tokyo, 07:00 UTC
    in Berlin, 19:00 UTC in Honolulu."""

    async def test_on_create_through_the_api(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        task = await _task(db_session, tokyo, test_admin_user)
        shift = await _shift(db_session, task, LATER, dt.time(10), dt.time(12))
        booking = await _book(db_session, shift, test_user)

        r = await async_client.post(
            f"/api/v1/bookings/{booking.id}/reminders", json={"offset_minutes": 60}
        )

        assert r.status_code == 201, r.text
        assert r.json()["remind_at"].startswith("2026-07-10T00:00:00")

    async def test_on_booking_with_default_reminders(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        app: FastAPI,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        test_user.default_reminder_offsets = [
            ReminderOffsetEntry(offset_minutes=60, channels=["push"])
        ]
        db_session.add(test_user)
        task = await _task(db_session, tokyo, test_admin_user)
        shift = await _shift(db_session, task, LATER, dt.time(10), dt.time(12))
        await db_session.flush()

        with act_as(app, test_user):
            r = await async_client.post(
                "/api/v1/bookings/", json={"shift_id": str(shift.id)}
            )

        assert r.status_code == 201, r.text
        reminders = await crud_reminder.get_by_booking(
            db_session, booking_id=r.json()["id"]
        )
        assert [x.remind_at for x in reminders] == [dt.datetime(2026, 7, 10, 0, 0)]

    async def test_a_zone_change_moves_what_is_pending(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_user: User,
    ) -> None:
        shift = await _shift(db_session, test_task, LATER, dt.time(10), dt.time(12))
        booking = await _book(db_session, shift, test_user)
        reminder = await _reminder(db_session, shift, booking, test_user, zone=None)
        assert reminder.remind_at == dt.datetime(2026, 7, 10, 7, 0)

        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}", json={"timezone": TOKYO}
        )
        assert r.status_code == 200, r.text

        await db_session.refresh(reminder)
        assert reminder.remind_at == dt.datetime(2026, 7, 10, 0, 0)
        assert reminder.status == "pending"

    async def test_saving_the_same_zone_moves_nothing(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_user: User,
    ) -> None:
        shift = await _shift(db_session, test_task, LATER, dt.time(10), dt.time(12))
        booking = await _book(db_session, shift, test_user)
        reminder = await _reminder(db_session, shift, booking, test_user, zone=None)
        # Someone's stored moment that isn't what the shift works out to.
        reminder.remind_at = dt.datetime(2026, 7, 9, 0, 0)
        db_session.add(reminder)
        await db_session.flush()

        r = await async_client.patch(
            f"/api/v1/events/{test_event.id}", json={"timezone": BERLIN}
        )
        assert r.status_code == 200, r.text

        await db_session.refresh(reminder)
        assert reminder.remind_at == dt.datetime(2026, 7, 9, 0, 0)

    async def test_sent_and_cancelled_stay_as_they_are(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_user: User,
    ) -> None:
        shift = await _shift(db_session, test_task, LATER, dt.time(10), dt.time(12))
        booking = await _book(db_session, shift, test_user)
        sent = await _reminder(
            db_session, shift, booking, test_user, zone=None, offset=60, status="sent"
        )
        cancelled = await _reminder(
            db_session,
            shift,
            booking,
            test_user,
            zone=None,
            offset=30,
            status="cancelled",
        )
        before = (sent.remind_at, cancelled.remind_at)

        await async_client.patch(
            f"/api/v1/events/{test_event.id}", json={"timezone": TOKYO}
        )

        await db_session.refresh(sent)
        await db_session.refresh(cancelled)
        assert (sent.remind_at, cancelled.remind_at) == before
        assert (sent.status, cancelled.status) == ("sent", "cancelled")

    async def test_moving_a_shift_moves_its_reminders(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        task = await _task(db_session, tokyo, test_admin_user)
        shift = await _shift(db_session, task, LATER, dt.time(10), dt.time(12))
        booking = await _book(db_session, shift, test_user)
        reminder = await _reminder(db_session, shift, booking, test_user, zone=TOKYO)

        r = await async_client.patch(
            f"/api/v1/shifts/{shift.id}",
            json={"date": "2026-07-12", "start_time": "09:00:00"},
        )
        assert r.status_code == 200, r.text

        await db_session.refresh(reminder)
        # 09:00 in Tokyo on the 12th is midnight UTC, less an hour.
        assert reminder.remind_at == dt.datetime(2026, 7, 11, 23, 0)

    async def test_a_new_end_time_moves_nothing(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        task = await _task(db_session, tokyo, test_admin_user)
        shift = await _shift(db_session, task, LATER, dt.time(10), dt.time(12))
        booking = await _book(db_session, shift, test_user)
        reminder = await _reminder(db_session, shift, booking, test_user, zone=TOKYO)
        before = reminder.remind_at

        r = await async_client.patch(
            f"/api/v1/shifts/{shift.id}", json={"end_time": "13:00:00"}
        )
        assert r.status_code == 200, r.text

        await db_session.refresh(reminder)
        assert reminder.remind_at == before

    async def test_moved_past_it_expires_and_moved_back_it_returns(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        """A shift moved to the wrong day by mistake and moved back keeps its
        reminder, which never reached anybody."""
        task = await _task(db_session, tokyo, test_admin_user)
        shift = await _shift(db_session, task, LATER, dt.time(10), dt.time(12))
        booking = await _book(db_session, shift, test_user)
        reminder = await _reminder(db_session, shift, booking, test_user, zone=TOKYO)

        # 12:30 in Tokyo is half an hour from now, so an hour's notice has gone.
        r = await async_client.patch(
            f"/api/v1/shifts/{shift.id}",
            json={
                "date": "2026-07-01",
                "start_time": "12:30:00",
                "end_time": "14:00:00",
            },
        )
        assert r.status_code == 200, r.text
        await db_session.refresh(reminder)
        assert reminder.status == "expired"

        r = await async_client.patch(
            f"/api/v1/shifts/{shift.id}",
            json={
                "date": "2026-07-10",
                "start_time": "10:00:00",
                "end_time": "12:00:00",
            },
        )
        assert r.status_code == 200, r.text
        await db_session.refresh(reminder)
        assert reminder.status == "pending"
        assert reminder.remind_at == dt.datetime(2026, 7, 10, 0, 0)

    async def test_an_expired_reminder_of_a_cancelled_booking_stays_expired(
        self,
        db_session: AsyncSession,
        tokyo: Event,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        task = await _task(db_session, tokyo, test_admin_user)
        shift = await _shift(db_session, task, LATER, dt.time(10), dt.time(12))
        booking = await _book(db_session, shift, test_user, status="cancelled")
        reminder = await _reminder(
            db_session, shift, booking, test_user, zone=TOKYO, status="expired"
        )

        await crud_reminder.reschedule(db_session, shift_ids=[shift.id])

        await db_session.refresh(reminder)
        assert reminder.status == "expired"

    async def test_moving_the_events_dates_moves_them(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        task = await _task(db_session, tokyo, test_admin_user)
        shift = await _shift(db_session, task, LATER, dt.time(10), dt.time(12))
        booking = await _book(db_session, shift, test_user)
        reminder = await _reminder(db_session, shift, booking, test_user, zone=TOKYO)

        r = await async_client.post(
            f"/api/v1/events/{tokyo.id}/shift-dates",
            json={"new_start_date": "2026-06-03"},
        )
        assert r.status_code == 200, r.text

        await db_session.refresh(reminder)
        assert reminder.remind_at == dt.datetime(2026, 7, 12, 0, 0)

    async def test_moving_a_task_to_another_zone_moves_them(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        honolulu: Event,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        task = await _task(db_session, tokyo, test_admin_user)
        shift = await _shift(db_session, task, LATER, dt.time(10), dt.time(12))
        booking = await _book(db_session, shift, test_user)
        reminder = await _reminder(db_session, shift, booking, test_user, zone=TOKYO)

        r = await async_client.patch(
            f"/api/v1/tasks/{task.id}", json={"event_id": str(honolulu.id)}
        )
        assert r.status_code == 200, r.text

        await db_session.refresh(reminder)
        assert reminder.remind_at == dt.datetime(2026, 7, 10, 19, 0)

    async def test_a_task_without_an_event_uses_the_setting(
        self, db_session: AsyncSession, test_admin_user: User, test_user: User
    ) -> None:
        task = await _task(db_session, None, test_admin_user)
        shift = await _shift(db_session, task, LATER, dt.time(10), dt.time(12))
        booking = await _book(db_session, shift, test_user)
        reminder = await _reminder(db_session, shift, booking, test_user, zone=TOKYO)

        await crud_reminder.reschedule(db_session, shift_ids=[shift.id])

        await db_session.refresh(reminder)
        assert reminder.remind_at == dt.datetime(2026, 7, 10, 7, 0)


# ── Booking cut-offs ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestBookingCutOffs:
    async def test_an_ended_shift_is_judged_on_its_own_clock(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        test_admin_user: User,
    ) -> None:
        """Over by 11:00 in Tokyo. Berlin's clock says it hasn't begun."""
        task = await _task(db_session, tokyo, test_admin_user)
        shift = await _shift(db_session, task, JULY_1, dt.time(10), dt.time(11))

        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(shift.id)}
        )

        assert r.status_code == 409, r.text
        assert r.json()["code"] == "booking.shift_over"

    async def test_a_shift_behind_the_default_clock_can_still_be_booked(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        honolulu: Event,
        test_admin_user: User,
    ) -> None:
        """20:00 on 30 June hasn't come in Honolulu. In Berlin it's long gone."""
        task = await _task(db_session, honolulu, test_admin_user)
        shift = await _shift(db_session, task, JUNE_30, dt.time(20), dt.time(22))

        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(shift.id)}
        )

        assert r.status_code == 201, r.text

    async def test_a_voucher_shift_that_started_is_refused_on_its_own_clock(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        test_admin_user: User,
    ) -> None:
        task = await _task(db_session, tokyo, test_admin_user, vouchers=2)
        shift = await _shift(db_session, task, JULY_1, dt.time(11), dt.time(14))

        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(shift.id)}
        )

        assert r.status_code == 409, r.text
        assert r.json()["code"] == "booking.shift_started"

    async def test_cancelling_an_ended_shift_is_refused_on_its_own_clock(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        task = await _task(db_session, tokyo, test_admin_user)
        shift = await _shift(db_session, task, JULY_1, dt.time(10), dt.time(11))
        booking = await _book(db_session, shift, test_user)

        r = await async_client.delete(f"/api/v1/bookings/{booking.id}")

        assert r.status_code == 409, r.text
        assert r.json()["code"] == "booking.shift_over"

    @pytest.mark.parametrize(("zone", "status"), [(TOKYO, 403), (BERLIN, 200)])
    async def test_a_person_in_charge_and_a_started_shift(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
        zone: str,
        status: int,
    ) -> None:
        """``check_shift_history``: 11:00 has been in Tokyo, not in Berlin."""
        event = await _event(db_session, test_admin_user, test_user, zone=zone)
        task = await _task(db_session, event, test_admin_user)
        db_session.add(TaskManager(task_id=task.id, user_id=test_user.id))
        shift = await _shift(db_session, task, JULY_1, dt.time(11), dt.time(14))
        other = await _book_other(db_session, shift)
        assert other is not None

        r = await async_client.patch(
            f"/api/v1/shifts/{shift.id}", json={"date": "2026-07-02"}
        )

        assert r.status_code == status, r.text

    async def test_leaving_keeps_a_shift_over_on_the_events_clock(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        app: FastAPI,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        """Over in Tokyo, so the work happened. Berlin's clock would cancel it."""
        task = await _task(db_session, tokyo, test_admin_user)
        shift = await _shift(db_session, task, JULY_1, dt.time(10), dt.time(11))
        booking = await _book(db_session, shift, test_user)

        with act_as(app, test_admin_user):
            r = await async_client.delete(
                f"/api/v1/events/{tokyo.id}/members/{test_user.id}"
            )
        assert r.status_code == 204, r.text

        await db_session.refresh(booking)
        assert booking.status == "confirmed"


async def _book_other(db: AsyncSession, shift: Shift) -> Booking:
    """Someone else's booking, so that the shift counts as booked."""
    other = User(
        subject=f"local|tz-other-{shift.id}",
        email=f"tz-other-{shift.id}@example.com",
        name="Other",
        roles=[],
        is_active=True,
    )
    db.add(other)
    await db.flush()
    return await _book(db, shift, other)


# ── Vouchers and hours ────────────────────────────────────────────


@pytest.mark.asyncio
class TestVouchersAndHours:
    @pytest.mark.parametrize(
        ("zone", "earned", "upcoming"), [(TOKYO, 3, 0), (BERLIN, 0, 3)]
    )
    async def test_vouchers_are_earned_when_the_shift_ends_there(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
        zone: str,
        earned: int,
        upcoming: int,
    ) -> None:
        event = await _event(db_session, test_admin_user, test_user, zone=zone)
        task = await _task(db_session, event, test_admin_user, vouchers=3)
        shift = await _shift(db_session, task, JULY_1, dt.time(10), dt.time(11))
        await _book(db_session, shift, test_user)

        r = await async_client.get(f"/api/v1/events/{event.id}/vouchers/me")

        assert r.status_code == 200, r.text
        assert r.json()["summary"]["earned"] == earned
        assert r.json()["summary"]["upcoming"] == upcoming

    async def test_ends_at_is_converted_through_the_events_zone(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        task = await _task(db_session, tokyo, test_admin_user, vouchers=3)
        shift = await _shift(db_session, task, JULY_1, dt.time(10), dt.time(11))
        await _book(db_session, shift, test_user)

        r = await async_client.get(f"/api/v1/events/{tokyo.id}/vouchers/me")

        assert r.json()["shifts"][0]["ends_at"].startswith("2026-07-01T02:00:00")

    async def test_changing_the_zone_keeps_what_was_earned(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        app: FastAPI,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        """Over in Tokyo at 11:00; 11:00 hasn't come in Honolulu. Earned is earned."""
        task = await _task(db_session, tokyo, test_admin_user, vouchers=3)
        shift = await _shift(db_session, task, JULY_1, dt.time(10), dt.time(11))
        booking = await _book(db_session, shift, test_user)

        with act_as(app, test_admin_user):
            r = await async_client.patch(
                f"/api/v1/events/{tokyo.id}", json={"timezone": HONOLULU}
            )
        assert r.status_code == 200, r.text

        settled = await db_session.execute(
            select(VoucherEarning).where(col(VoucherEarning.booking_id) == booking.id)
        )
        assert settled.scalar_one().amount == 3
        with act_as(app, test_user):
            account = await async_client.get(f"/api/v1/events/{tokyo.id}/vouchers/me")
        assert account.json()["summary"]["earned"] == 3

    @pytest.mark.parametrize(("zone", "can_redeem"), [(TOKYO, True), (BERLIN, False)])
    async def test_on_shift_at_a_point_is_judged_on_its_own_clock(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
        zone: str,
        can_redeem: bool,
    ) -> None:
        """11:00-14:00 is running at noon in Tokyo. It's 05:00 in Berlin."""
        event = await _event(db_session, test_admin_user, test_user, zone=zone)
        point = await _task(db_session, event, test_admin_user, point=True)
        shift = await _shift(db_session, point, JULY_1, dt.time(11), dt.time(14))
        await _book(db_session, shift, test_user)

        points = await async_client.get(f"/api/v1/events/{event.id}/vouchers/points")
        assert points.status_code == 200, points.text
        assert points.json()[0]["can_redeem"] is can_redeem

        # The task reads answer the same.
        read = await async_client.get(f"/api/v1/tasks/{point.id}")
        assert read.json()["can_redeem"] is can_redeem

    async def test_the_task_feed_answers_can_redeem_per_zone(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        lisbon: Event,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        """One page, two zones: running in Tokyo, not yet in Lisbon."""
        running = await _task(db_session, tokyo, test_admin_user, point=True)
        waiting = await _task(db_session, lisbon, test_admin_user, point=True)
        for task in (running, waiting):
            shift = await _shift(db_session, task, JULY_1, dt.time(11), dt.time(14))
            await _book(db_session, shift, test_user)
            await _shift(db_session, task, LATER, dt.time(11), dt.time(14))

        r = await async_client.get(
            "/api/v1/tasks/feed", params={"view": "list", "all_events": True}
        )

        assert r.status_code == 200, r.text
        redeem = {i["id"]: i["can_redeem"] for i in r.json()["items"]}
        assert redeem[str(running.id)] is True
        assert redeem[str(waiting.id)] is False

    async def test_todays_redemptions_start_at_the_events_midnight(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        app: FastAPI,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        """16:00 UTC on 30 June is 01:00 on 1 July in Tokyo: today, over there."""
        point = await _task(db_session, tokyo, test_admin_user, point=True)
        moment = dt.datetime(2026, 6, 30, 16, 0)
        db_session.add(
            VoucherEntry(
                event_id=tokyo.id,
                user_id=test_user.id,
                kind="redemption",
                amount=-2,
                method="manual",
                task_id=point.id,
                task_name=point.name,
                actor_id=test_admin_user.id,
                actor_name="Admin",
                created_at=moment,
                updated_at=moment,
            )
        )
        await db_session.flush()

        with act_as(app, test_admin_user):
            r = await async_client.get(
                f"/api/v1/events/{tokyo.id}/vouchers/points/{point.id}/entries"
            )

        assert r.status_code == 200, r.text
        assert r.json()["today_amount"] == 2

    @pytest.mark.parametrize(("zone", "completed"), [(TOKYO, True), (BERLIN, False)])
    async def test_hours_count_once_the_shift_ends_there(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
        zone: str,
        completed: bool,
    ) -> None:
        event = await _event(db_session, test_admin_user, test_user, zone=zone)
        task = await _task(db_session, event, test_admin_user)
        shift = await _shift(db_session, task, JULY_1, dt.time(10), dt.time(11))
        await _book(db_session, shift, test_user)

        detail = await work_hours.volunteer_hours(db_session, event.id, test_user)

        assert [s.completed for s in detail.shifts] == [completed]


# ── Views across events ───────────────────────────────────────────


@pytest_asyncio.fixture
async def two_zones(
    db_session: AsyncSession,
    tokyo: Event,
    lisbon: Event,
    test_admin_user: User,
) -> SimpleNamespace:
    """The same 10:00-11:00 on 1 July in both: over in Tokyo (12:00), still to
    come in Lisbon (04:00). Comparing either clock with both shifts gets one
    of them wrong."""
    tokyo_task = await _task(db_session, tokyo, test_admin_user)
    lisbon_task = await _task(db_session, lisbon, test_admin_user)
    return SimpleNamespace(
        tokyo_task=tokyo_task,
        lisbon_task=lisbon_task,
        tokyo_shift=await _shift(
            db_session, tokyo_task, JULY_1, dt.time(10), dt.time(11)
        ),
        lisbon_shift=await _shift(
            db_session, lisbon_task, JULY_1, dt.time(10), dt.time(11)
        ),
    )


@pytest.mark.asyncio
class TestViewsAcrossEvents:
    async def test_the_feed_judges_each_shift_on_its_own_clock(
        self, async_client: AsyncClient, two_zones: SimpleNamespace
    ) -> None:
        r = await async_client.get(
            "/api/v1/tasks/feed", params={"view": "list", "all_events": True}
        )

        assert r.status_code == 200, r.text
        items = {i["id"]: i for i in r.json()["items"]}
        assert str(two_zones.lisbon_task.id) in items
        assert str(two_zones.tokyo_task.id) not in items
        assert items[str(two_zones.lisbon_task.id)]["open_shifts"] == 1

    async def test_a_tasks_window_starts_on_its_own_today(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        honolulu: Event,
        tokyo: Event,
        test_admin_user: User,
    ) -> None:
        """It's still 30 June in Honolulu and already 1 July in Tokyo."""
        behind = await _task(db_session, honolulu, test_admin_user)
        await _shift(db_session, behind, JUNE_30, dt.time(20), dt.time(22))
        ahead = await _task(db_session, tokyo, test_admin_user)
        await _shift(db_session, ahead, JULY_1, dt.time(20), dt.time(22))

        r = await async_client.get(
            "/api/v1/tasks/feed", params={"view": "list", "all_events": True}
        )

        items = {i["id"]: i for i in r.json()["items"]}
        assert items[str(behind.id)]["slot_window_start"] == "2026-06-30"
        assert items[str(ahead.id)]["slot_window_start"] == "2026-07-01"
        assert [s["date"] for s in items[str(behind.id)]["shifts"]] == ["2026-06-30"]
        assert [s["date"] for s in items[str(ahead.id)]["shifts"]] == ["2026-07-01"]

    async def test_first_available_starts_on_its_own_today(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        honolulu: Event,
        test_admin_user: User,
    ) -> None:
        behind = await _task(db_session, honolulu, test_admin_user)
        await _shift(db_session, behind, JUNE_30, dt.time(20), dt.time(22))

        r = await async_client.get(
            "/api/v1/tasks/feed",
            params={
                "view": "list",
                "all_events": True,
                "focus_mode": "first_available",
            },
        )

        items = {i["id"]: i for i in r.json()["items"]}
        assert items[str(behind.id)]["slot_window_start"] == "2026-06-30"

    @pytest.mark.usefixtures("as_organiser")
    async def test_a_task_ends_on_its_own_day(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        honolulu: Event,
        tokyo: Event,
        test_admin_user: User,
    ) -> None:
        """An organiser's tasks show until their end date, full or not: 30 June
        is today in Honolulu and was yesterday in Tokyo."""
        behind = await _task(db_session, honolulu, test_admin_user, end_date=JUNE_30)
        ahead = await _task(db_session, tokyo, test_admin_user, end_date=JUNE_30)

        r = await async_client.get(
            "/api/v1/tasks/feed", params={"view": "cards", "all_events": True}
        )

        ids = {i["id"] for i in r.json()["items"]}
        assert str(behind.id) in ids
        assert str(ahead.id) not in ids

    async def test_the_dashboard_lists_my_shifts_by_their_own_clocks(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        two_zones: SimpleNamespace,
        test_user: User,
    ) -> None:
        await _book(db_session, two_zones.tokyo_shift, test_user)
        await _book(db_session, two_zones.lisbon_shift, test_user)

        r = await async_client.get("/api/v1/dashboard/feed")

        assert r.status_code == 200, r.text
        assert [s["shift_id"] for s in r.json()["my_shifts"]] == [
            str(two_zones.lisbon_shift.id)
        ]

    async def test_the_dashboard_offers_open_shifts_by_their_own_clocks(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        two_zones: SimpleNamespace,
        test_user: User,
    ) -> None:
        test_user.selected_event_id = None
        db_session.add(test_user)
        await db_session.flush()

        r = await async_client.get("/api/v1/dashboard/feed")

        assert r.status_code == 200, r.text
        offered = {s["shift_id"] for s in r.json()["open_shifts"]}
        assert str(two_zones.lisbon_shift.id) in offered
        assert str(two_zones.tokyo_shift.id) not in offered

    async def test_an_overnight_shift_is_running_on_its_own_clock(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        honolulu: Event,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        """22:00-13:00 from 30 June: still on at noon in Tokyo, and in Honolulu
        (17:00 on the 30th) it hasn't started."""
        running = await _shift(
            db_session,
            await _task(db_session, tokyo, test_admin_user),
            JUNE_30,
            dt.time(22),
            dt.time(13),
        )
        ahead = await _shift(
            db_session,
            await _task(db_session, honolulu, test_admin_user),
            JUNE_30,
            dt.time(22),
            dt.time(13),
        )
        await _book(db_session, running, test_user)
        await _book(db_session, ahead, test_user)

        r = await async_client.get("/api/v1/dashboard/feed")

        assert {s["shift_id"] for s in r.json()["my_shifts"]} == {
            str(running.id),
            str(ahead.id),
        }

    async def test_the_sidebar_goes_by_each_shifts_own_clock(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        two_zones: SimpleNamespace,
        test_user: User,
    ) -> None:
        await _book(db_session, two_zones.tokyo_shift, test_user)
        await _book(db_session, two_zones.lisbon_shift, test_user)
        await _shift(db_session, two_zones.tokyo_task, JULY_1, dt.time(10), dt.time(11))
        await _shift(
            db_session, two_zones.lisbon_task, JULY_1, dt.time(10), dt.time(11)
        )

        r = await async_client.get("/api/v1/dashboard/sidebar")

        assert r.status_code == 200, r.text
        data = r.json()
        assert [b["slot_id"] for b in data["bookings"]] == [
            str(two_zones.lisbon_shift.id)
        ]
        task_ids = {t["id"] for t in data["tasks"]}
        assert str(two_zones.lisbon_task.id) in task_ids
        assert str(two_zones.tokyo_task.id) not in task_ids

    async def test_the_sidebar_lists_an_event_until_its_own_last_day(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        behind = await _event(
            db_session, test_admin_user, test_user, zone=HONOLULU, name="Behind"
        )
        ahead = await _event(
            db_session, test_admin_user, test_user, zone=TOKYO, name="Ahead"
        )
        for event in (behind, ahead):
            event.end_date = JUNE_30
            db_session.add(event)
        await db_session.flush()

        r = await async_client.get("/api/v1/dashboard/sidebar")

        ids = {e["id"] for e in r.json()["events"]}
        assert str(behind.id) in ids
        assert str(ahead.id) not in ids

    async def test_attention_counts_shifts_by_their_own_clocks(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        app: FastAPI,
        test_admin_user: User,
        test_event_admin_user: User,
    ) -> None:
        """Yesterday in Tokyo (30 June) isn't soon; today in Honolulu is. The
        count is across every event this organiser runs."""
        for zone in (TOKYO, HONOLULU):
            event = await _event(
                db_session, test_event_admin_user, test_admin_user, zone=zone
            )
            task = await _task(db_session, event, test_event_admin_user)
            await _shift(db_session, task, JUNE_30, dt.time(20), dt.time(22))

        with act_as(app, test_event_admin_user):
            r = await async_client.get("/api/v1/dashboard/feed")

        assert r.status_code == 200, r.text
        assert r.json()["attention"]["empty_shifts_soon"] == 1

    async def test_a_task_without_an_event_is_read_in_the_setting(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        """It still has to be on a clock with several zones in use: no branch
        for it would drop the shift from the list."""
        task = await _task(db_session, None, test_admin_user)
        coming_up = await _shift(db_session, task, JULY_1, dt.time(10), dt.time(11))
        await _book(db_session, coming_up, test_user)
        assert tokyo.timezone == TOKYO

        r = await async_client.get("/api/v1/dashboard/feed")

        assert str(coming_up.id) in {s["shift_id"] for s in r.json()["my_shifts"]}

    @pytest.mark.parametrize(
        "url",
        [
            "/api/v1/dashboard/feed",
            "/api/v1/dashboard/sidebar",
        ],
    )
    async def test_more_events_add_no_queries(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
        count_queries: CountQueries,
        url: str,
    ) -> None:
        """Two zones either way: judging shifts on their clocks costs one query
        for the zones, however many events are in them."""

        async def add(zone: str) -> None:
            event = await _event(db_session, test_admin_user, test_user, zone=zone)
            task = await _task(db_session, event, test_admin_user)
            shift = await _shift(db_session, task, LATER, dt.time(10), dt.time(11))
            await _book(db_session, shift, test_user)

        await add(TOKYO)
        await add(LISBON)
        with count_queries() as few:
            assert (await async_client.get(url)).status_code == 200

        for zone in (TOKYO, LISBON, TOKYO, LISBON):
            await add(zone)
        with count_queries() as many:
            assert (await async_client.get(url)).status_code == 200

        assert len(many) == len(few)


# ── Clashes across zones ──────────────────────────────────────────

JULY_11 = dt.date(2026, 7, 11)


@pytest.mark.asyncio
class TestClashesAcrossZones:
    """On 10 July: Tokyo is UTC+9, Berlin UTC+2, Lisbon UTC+1, Honolulu UTC-10."""

    async def _shift_in(
        self,
        db: AsyncSession,
        zone: str,
        owner: User,
        member: User,
        date: dt.date,
        start: int,
        end: int,
    ) -> Shift:
        event = await _event(db, owner, member, zone=zone, name=f"{zone} {start}")
        task = await _task(db, event, owner)
        return await _shift(db, task, date, dt.time(start), dt.time(end))

    async def _try_to_book(self, client: AsyncClient, shift: Shift) -> int:
        r = await client.post("/api/v1/bookings/", json={"shift_id": str(shift.id)})
        if r.status_code == 409:
            assert r.json()["code"] == "booking.time_conflict"
        return r.status_code

    @pytest.mark.parametrize(
        ("booked", "wanted", "status"),
        [
            # The same hours on the rota, seven hours apart in fact.
            ((TOKYO, LATER, 10, 12), (BERLIN, LATER, 10, 12), 201),
            # Different hours on the rota, the same moment in fact.
            ((LISBON, LATER, 9, 11), (BERLIN, LATER, 10, 12), 409),
            ((BERLIN, LATER, 10, 12), (LISBON, LATER, 9, 11), 409),
            # Back to back in fact, which is no clash on any clock.
            ((LISBON, LATER, 9, 10), (BERLIN, LATER, 11, 12), 201),
            # The same moment, dated a day apart: the booked shift is outside the
            # window one zone would have looked at.
            ((TOKYO, JULY_11, 6, 8), (HONOLULU, LATER, 11, 13), 409),
            ((HONOLULU, LATER, 22, 23), (TOKYO, JULY_11, 17, 18), 409),
            # Two events in one zone compare as written, with others around.
            ((TOKYO, LATER, 10, 12), (TOKYO, LATER, 11, 13), 409),
            ((TOKYO, LATER, 10, 12), (TOKYO, LATER, 12, 13), 201),
        ],
    )
    async def test_booking(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
        booked: tuple[str, dt.date, int, int],
        wanted: tuple[str, dt.date, int, int],
        status: int,
    ) -> None:
        held = await self._shift_in(
            db_session, booked[0], test_admin_user, test_user, *booked[1:]
        )
        await _book(db_session, held, test_user)
        other = await self._shift_in(
            db_session, wanted[0], test_admin_user, test_user, *wanted[1:]
        )

        assert await self._try_to_book(async_client, other) == status

    @pytest.mark.parametrize(
        ("booked", "wanted", "collides"),
        [
            ((TOKYO, LATER, 10, 12), (BERLIN, LATER, 10, 12), False),
            ((LISBON, LATER, 9, 11), (BERLIN, LATER, 10, 12), True),
            ((TOKYO, JULY_11, 6, 8), (HONOLULU, LATER, 11, 13), True),
        ],
    )
    async def test_the_flag_on_a_list_of_shifts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
        booked: tuple[str, dt.date, int, int],
        wanted: tuple[str, dt.date, int, int],
        collides: bool,
    ) -> None:
        held = await self._shift_in(
            db_session, booked[0], test_admin_user, test_user, *booked[1:]
        )
        await _book(db_session, held, test_user)
        other = await self._shift_in(
            db_session, wanted[0], test_admin_user, test_user, *wanted[1:]
        )

        r = await async_client.get(
            "/api/v1/shifts/", params={"task_id": str(other.task_id)}
        )

        assert r.status_code == 200, r.text
        assert [s["collides_with_my_booking"] for s in r.json()["items"]] == [collides]

    async def test_the_flag_in_the_feed(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        held = await self._shift_in(
            db_session, LISBON, test_admin_user, test_user, LATER, 9, 11
        )
        await _book(db_session, held, test_user)
        other = await self._shift_in(
            db_session, BERLIN, test_admin_user, test_user, LATER, 10, 12
        )

        r = await async_client.get(
            "/api/v1/tasks/feed",
            params={
                "view": "list",
                "focus_mode": "first_available",
                "all_events": True,
            },
        )

        assert r.status_code == 200, r.text
        [item] = [i for i in r.json()["items"] if i["id"] == str(other.task_id)]
        assert [s["collides_with_my_booking"] for s in item["shifts"]] == [True]


@pytest.mark.asyncio
class TestClashesWithOneZoneInUse:
    """The usual installation: nothing about zones reaches the queries."""

    async def test_booking_reads_no_zones(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_event: Event,
        test_task: Task,
        count_queries: CountQueries,
    ) -> None:
        assert test_event.timezone == BERLIN
        held = await _shift(db_session, test_task, LATER, dt.time(10), dt.time(12))
        await _book(db_session, held, test_user)
        other = await _shift(db_session, test_task, LATER, dt.time(11), dt.time(13))

        with count_queries() as statements:
            found = await find_conflicting_booking(
                db_session, user_id=test_user.id, shift=other, zone=BERLIN
            )

        assert found is not None
        assert found.shift.id == held.id
        assert not any("zone_event" in statement for statement in statements)

    async def test_marking_a_page_reads_no_zones(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_event: Event,
        test_task: Task,
        count_queries: CountQueries,
    ) -> None:
        assert test_event.timezone == BERLIN
        held = await _shift(db_session, test_task, LATER, dt.time(10), dt.time(12))
        await _book(db_session, held, test_user)
        other = await _shift(db_session, test_task, LATER, dt.time(11), dt.time(13))
        entry = SimpleNamespace(
            id=other.id,
            date=other.date,
            start_time=other.start_time,
            end_time=other.end_time,
            is_booked_by_me=False,
            collides_with_my_booking=False,
        )

        with count_queries() as statements:
            await mark_collisions(
                db_session,
                user_id=test_user.id,
                entries=[entry],  # pyright: ignore[reportArgumentType]
            )

        assert entry.collides_with_my_booking is True
        assert not any("zone_event" in statement for statement in statements)


# ── The reads name the zone ───────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.usefixtures("as_organiser")
class TestTheReadsNameTheZone:
    """So a client can work out what the server would refuse, in the event's time
    rather than the browser's. Every read here spans events, so each row has to
    carry its own."""

    @pytest_asyncio.fixture
    async def shifts(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
        tokyo: Event,
        honolulu: Event,
    ) -> dict[str, Shift]:
        out: dict[str, Shift] = {}
        for event in (tokyo, honolulu):
            task = await _task(db_session, event, test_admin_user)
            # Both booked and open shifts: the dashboard lists them apart.
            booked = await _shift(db_session, task, LATER, dt.time(10), dt.time(11))
            await _book(db_session, booked, test_user)
            await _shift(db_session, task, LATER, dt.time(12), dt.time(13))
            out[event.timezone] = booked
        return out

    async def test_a_shift(
        self, async_client: AsyncClient, shifts: dict[str, Shift]
    ) -> None:
        for zone, shift in shifts.items():
            r = await async_client.get(f"/api/v1/shifts/{shift.id}")
            assert r.json()["event_timezone"] == zone

    async def test_a_tasks_shifts(
        self, async_client: AsyncClient, shifts: dict[str, Shift]
    ) -> None:
        for zone, shift in shifts.items():
            r = await async_client.get(
                "/api/v1/shifts/", params={"task_id": str(shift.task_id)}
            )
            assert {s["event_timezone"] for s in r.json()["items"]} == {zone}

    async def test_the_task_list(
        self, async_client: AsyncClient, shifts: dict[str, Shift]
    ) -> None:
        r = await async_client.get("/api/v1/tasks/", params={"all_events": True})

        zones = {t["id"]: t["event_timezone"] for t in r.json()["items"]}
        for zone, shift in shifts.items():
            assert zones[str(shift.task_id)] == zone

    @pytest.mark.parametrize("view", ["list", "cards"])
    async def test_the_task_feed(
        self, async_client: AsyncClient, shifts: dict[str, Shift], view: str
    ) -> None:
        r = await async_client.get(
            "/api/v1/tasks/feed", params={"view": view, "all_events": True}
        )

        zones = {t["id"]: t["event_timezone"] for t in r.json()["items"]}
        for zone, shift in shifts.items():
            assert zones[str(shift.task_id)] == zone

    async def test_my_bookings(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        test_user: User,
        shifts: dict[str, Shift],
    ) -> None:
        with act_as(app, test_user):
            r = await async_client.get(
                "/api/v1/bookings/me", params={"all_events": True}
            )

        zones = {
            b["shift"]["id"]: b["shift"]["event_timezone"] for b in r.json()["items"]
        }
        for zone, shift in shifts.items():
            assert zones[str(shift.id)] == zone

    async def test_the_dashboard(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        test_user: User,
        tokyo: Event,
        shifts: dict[str, Shift],
    ) -> None:
        test_user.selected_event_id = tokyo.id
        db_session.add(test_user)
        await db_session.flush()

        with act_as(app, test_user):
            r = await async_client.get("/api/v1/dashboard/feed")

        mine = {s["shift_id"]: s["event_timezone"] for s in r.json()["my_shifts"]}
        for zone, shift in shifts.items():
            assert mine[str(shift.id)] == zone
        assert {s["event_timezone"] for s in r.json()["open_shifts"]} == {TOKYO}

    async def test_a_locations_shifts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        tokyo: Event,
        shifts: dict[str, Shift],
    ) -> None:
        location = Location(event_id=tokyo.id, name="Bar")
        db_session.add(location)
        await db_session.flush()
        shift = shifts[TOKYO]
        shift.location_id = location.id
        db_session.add(shift)
        await db_session.flush()

        r = await async_client.get(
            f"/api/v1/locations/{location.id}/shifts", params={"on": LATER.isoformat()}
        )

        assert [s["event_timezone"] for s in r.json()] == [TOKYO]

    async def test_a_task_without_an_event_says_none(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_admin_user: User,
    ) -> None:
        task = await _task(db_session, None, test_admin_user)

        r = await async_client.get(f"/api/v1/tasks/{task.id}")

        assert r.status_code == 200, r.text
        assert r.json()["event_timezone"] is None


# ── Today, where the event is ─────────────────────────────────────


async def _ending(db: AsyncSession, event: Event, end: dt.date) -> Event:
    event.end_date = end
    db.add(event)
    await db.flush()
    return event


@pytest.mark.asyncio
@pytest.mark.usefixtures("as_organiser")
class TestAnEventsLastDay:
    """30 June is today in Honolulu and was yesterday in Tokyo."""

    async def test_the_read_says_expired_on_its_own_clock(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        honolulu: Event,
        tokyo: Event,
    ) -> None:
        await _ending(db_session, honolulu, JUNE_30)
        await _ending(db_session, tokyo, JUNE_30)

        behind = await async_client.get(f"/api/v1/events/{honolulu.id}")
        ahead = await async_client.get(f"/api/v1/events/{tokyo.id}")

        assert behind.json()["is_expired"] is False
        assert ahead.json()["is_expired"] is True

    async def test_the_model_says_the_same(
        self, db_session: AsyncSession, honolulu: Event, tokyo: Event
    ) -> None:
        assert (await _ending(db_session, honolulu, JUNE_30)).is_expired is False
        assert (await _ending(db_session, tokyo, JUNE_30)).is_expired is True

    @pytest.mark.parametrize("expired", [True, False])
    async def test_the_list_filter_says_the_same(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        honolulu: Event,
        tokyo: Event,
        expired: bool,
    ) -> None:
        await _ending(db_session, honolulu, JUNE_30)
        await _ending(db_session, tokyo, JUNE_30)

        r = await async_client.get(
            "/api/v1/events/", params={"scope": "mine", "is_expired": expired}
        )

        assert r.status_code == 200, r.text
        ids = {e["id"] for e in r.json()["items"]}
        assert (str(tokyo.id) in ids) is expired
        assert (str(honolulu.id) in ids) is not expired
        assert r.json()["total"] == len(ids)


@pytest.mark.asyncio
@pytest.mark.usefixtures("as_organiser")
class TestTheMapsDefaultDay:
    """Without ``on``, the map shows today where the event is."""

    async def _at_location(
        self, db: AsyncSession, event: Event, owner: User, day: dt.date
    ) -> Location:
        location = Location(event_id=event.id, name="Bar")
        db.add(location)
        await db.flush()
        task = await _task(db, event, owner)
        shift = await _shift(db, task, day, dt.time(10), dt.time(11))
        shift.location_id = location.id
        db.add(shift)
        await db.flush()
        return location

    @pytest.mark.parametrize(("zone", "listed"), [(HONOLULU, JUNE_30), (TOKYO, JULY_1)])
    async def test_a_locations_shifts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
        zone: str,
        listed: dt.date,
    ) -> None:
        event = await _event(db_session, test_admin_user, test_user, zone=zone)
        location = await self._at_location(db_session, event, test_admin_user, listed)

        r = await async_client.get(f"/api/v1/locations/{location.id}/shifts")

        assert r.status_code == 200, r.text
        assert [s["date"] for s in r.json()] == [listed.isoformat()]

    @pytest.mark.parametrize(("zone", "listed"), [(HONOLULU, JUNE_30), (TOKYO, JULY_1)])
    async def test_the_maps_counts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
        zone: str,
        listed: dt.date,
    ) -> None:
        event = await _event(db_session, test_admin_user, test_user, zone=zone)
        location = await self._at_location(db_session, event, test_admin_user, listed)

        r = await async_client.get(f"/api/v1/events/{event.id}/venue-map")

        assert r.status_code == 200, r.text
        assert r.json()["on"] == listed.isoformat()
        stats = {s["location_id"]: s for s in r.json()["location_stats"]}
        assert stats[str(location.id)]["shift_count"] == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("as_organiser")
class TestATeamChecksDates:
    """A check runs out on a date where the event is, and a document can be
    issued as late as today there."""

    async def _team(self, db: AsyncSession, event: Event) -> EventTeam:
        team = EventTeam(event_id=event.id, name="Kasse", requires_approval=True)
        db.add(team)
        await db.flush()
        return team

    async def _requirement(
        self, db: AsyncSession, team: EventTeam
    ) -> EventTeamRequirement:
        requirement = EventTeamRequirement(
            team_id=team.id,
            label="Führungszeugnis",
            ask_issue_date=True,
            valid_for_years=1,
        )
        db.add(requirement)
        await db.flush()
        return requirement

    @pytest.mark.parametrize(("zone", "expired"), [(HONOLULU, False), (TOKYO, True)])
    async def test_a_check_expires_on_its_events_day(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
        zone: str,
        expired: bool,
    ) -> None:
        event = await _event(db_session, test_admin_user, test_user, zone=zone)
        team = await self._team(db_session, event)
        requirement = await self._requirement(db_session, team)
        member = EventTeamMember(
            team_id=team.id, user_id=test_user.id, status="approved"
        )
        db_session.add(member)
        await db_session.flush()
        db_session.add(
            EventTeamCheck(
                member_id=member.id,
                requirement_id=requirement.id,
                checked_by_name="Someone",
                checked_at=INSTANT,
                expires_on=JUNE_30,
            )
        )
        await db_session.flush()

        r = await async_client.get(f"/api/v1/events/{event.id}/teams/{team.id}/members")

        assert r.status_code == 200, r.text
        [read] = r.json()
        assert read["checks"][0]["expired"] is expired
        assert read["needs_recheck"] is expired

    @pytest.mark.parametrize(("zone", "allowed"), [(TOKYO, True), (HONOLULU, False)])
    async def test_a_document_issued_today_there_is_not_in_the_future(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
        zone: str,
        allowed: bool,
    ) -> None:
        """1 July has begun in Tokyo and is still to come in Honolulu."""
        event = await _event(db_session, test_admin_user, test_user, zone=zone)
        team = await self._team(db_session, event)
        requirement = await self._requirement(db_session, team)

        r = await async_client.post(
            f"/api/v1/events/{event.id}/teams/{team.id}/members",
            json={
                "user_id": str(test_user.id),
                "checks": [
                    {
                        "requirement_id": str(requirement.id),
                        "issued_on": JULY_1.isoformat(),
                    }
                ],
            },
        )

        assert r.status_code == (201 if allowed else 422), r.text
        assert allowed or r.json()["code"] == "team.check_issued_in_future"


@pytest.fixture
def count_queries(db_session: AsyncSession) -> CountQueries:
    """``with count_queries() as statements:`` collects what the session runs."""
    engine = db_session.get_bind()

    @contextmanager
    def _count() -> Generator[list[str]]:
        statements: list[str] = []

        def record(_c: Any, _cur: Any, statement: str, *_rest: Any) -> None:
            statements.append(statement)

        sa_event.listen(engine, "before_cursor_execute", record)
        try:
            yield statements
        finally:
            sa_event.remove(engine, "before_cursor_execute", record)

    return _count
