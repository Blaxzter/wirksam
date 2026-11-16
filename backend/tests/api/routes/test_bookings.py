"""Route tests for Booking endpoints."""

import asyncio
import uuid
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

import pytest
import pytest_asyncio
from fastapi import BackgroundTasks, HTTPException
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlmodel import col

from app.api.routes.bookings import create_booking
from app.crud.booking import booking as crud_booking
from app.models.booking import Booking
from app.models.booking_reminder import BookingReminder
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shift import Shift
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from app.schemas.booking import BookingCreate

# The fixture shifts are dated in the past; booking refuses an ended shift
# (booking.shift_over), so this module runs before them.
pytestmark = pytest.mark.usefixtures("clock_before_fixture_shifts")


@pytest.mark.asyncio
class TestBookingsRoutes:
    """Test suite for /bookings/ routes."""

    async def test_create_booking(self, async_client: AsyncClient, test_shift: Shift):
        """Test creating a new booking."""
        r = await async_client.post(
            "/api/v1/bookings/",
            json={"shift_id": str(test_shift.id)},
        )

        assert r.status_code == 201
        assert r.json()["status"] == "confirmed"
        assert r.json()["shift_id"] == str(test_shift.id)

    async def test_double_booking_prevented(
        self, async_client: AsyncClient, test_booking: Booking, test_shift: Shift
    ):
        """Test that a user cannot double-book the same shift."""
        r = await async_client.post(
            "/api/v1/bookings/",
            json={"shift_id": str(test_shift.id)},
        )

        assert r.status_code == 409

    async def test_list_my_bookings(
        self, async_client: AsyncClient, test_booking: Booking
    ):
        """Test listing the current user's bookings."""
        r = await async_client.get("/api/v1/bookings/me")

        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert any(item["id"] == str(test_booking.id) for item in data["items"])

    async def test_get_booking(self, async_client: AsyncClient, test_booking: Booking):
        """Test getting a specific booking."""
        r = await async_client.get(f"/api/v1/bookings/{test_booking.id}")

        assert r.status_code == 200
        assert r.json()["id"] == str(test_booking.id)

    async def test_cancel_booking(
        self, async_client: AsyncClient, test_booking: Booking
    ):
        """Test cancelling a booking via DELETE."""
        r = await async_client.delete(f"/api/v1/bookings/{test_booking.id}")

        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    async def test_update_booking_notes(
        self, async_client: AsyncClient, test_booking: Booking
    ):
        """Test updating booking notes."""
        r = await async_client.patch(
            f"/api/v1/bookings/{test_booking.id}",
            json={"notes": "Updated notes"},
        )

        assert r.status_code == 200
        assert r.json()["notes"] == "Updated notes"

    async def test_shift_capacity_enforced(
        self, async_client: AsyncClient, db_session: AsyncSession, test_task: Task
    ):
        """Test that bookings are rejected when a shift is full."""
        shift = Shift(
            task_id=test_task.id,
            title="Limited Shift",
            date=date(2026, 5, 24),
            start_time=time(14, 0),
            end_time=time(18, 0),
            max_bookings=1,
        )
        db_session.add(shift)
        await db_session.flush()
        await db_session.refresh(shift)

        other_user = User(
            subject="local|other_user_cap_test",
            email="other@example.com",
            name="Other",
            roles=[],
        )
        db_session.add(other_user)
        await db_session.flush()

        existing = Booking(
            shift_id=shift.id,
            user_id=other_user.id,
            status="confirmed",
        )
        db_session.add(existing)
        await db_session.flush()

        r = await async_client.post(
            "/api/v1/bookings/",
            json={"shift_id": str(shift.id)},
        )

        assert r.status_code == 409

    async def test_get_nonexistent_booking(self, async_client: AsyncClient):
        """Test getting a non-existent booking returns 404."""
        import uuid

        fake_id = uuid.uuid4()
        r = await async_client.get(f"/api/v1/bookings/{fake_id}")

        assert r.status_code == 404


@pytest.mark.asyncio
class TestBookingGuards:
    """Who may book, and when: membership, published tasks, and never once
    the shift is over (hours and vouchers are derived from ended shifts)."""

    async def test_a_non_member_cannot_book(
        self, async_client: AsyncClient, test_shift: Shift, as_outsider: None
    ):
        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(test_shift.id)}
        )
        assert r.status_code == 403
        assert r.json()["code"] == "event.forbidden"

    async def test_a_draft_task_only_for_those_who_run_it(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_draft_task: Task,
        test_user: User,
    ):
        shift = await _shift(db_session, test_draft_task, date(2026, 6, 12))

        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(shift.id)}
        )
        assert r.status_code == 403
        assert r.json()["code"] == "task.not_published"

        db_session.add(TaskManager(task_id=test_draft_task.id, user_id=test_user.id))
        await db_session.flush()
        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(shift.id)}
        )
        assert r.status_code == 201

    @pytest.mark.parametrize("vouchers_per_shift", [0, 2])
    async def test_an_ended_shift_cannot_be_booked(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_shift: Shift,
        wall_clock: Callable[[datetime], None],
        vouchers_per_shift: int,
    ):
        """On every task: a shift booked after the fact on a task with no
        vouchers would start earning the moment an organiser set some."""
        test_task.vouchers_per_shift = vouchers_per_shift
        db_session.add(test_task)
        await db_session.flush()
        wall_clock(datetime(2026, 5, 24, 12, 0))  # the shift ends at 12:00

        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(test_shift.id)}
        )
        assert r.status_code == 409
        assert r.json()["code"] == "booking.shift_over"

    async def test_a_cancelled_booking_on_an_ended_shift_stays_cancelled(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shift: Shift,
        test_user: User,
        wall_clock: Callable[[datetime], None],
    ):
        db_session.add(
            Booking(shift_id=test_shift.id, user_id=test_user.id, status="cancelled")
        )
        await db_session.flush()
        wall_clock(datetime(2026, 5, 25, 9, 0))

        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(test_shift.id)}
        )
        assert r.status_code == 409
        assert r.json()["code"] == "booking.shift_over"

    @pytest.mark.parametrize("how", ["delete", "patch"])
    async def test_a_booking_on_an_ended_shift_cannot_be_cancelled(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_booking: Booking,
        wall_clock: Callable[[datetime], None],
        how: str,
    ):
        """It would take back hours and vouchers already earned, and perhaps
        already spent."""
        wall_clock(datetime(2026, 5, 24, 12, 30))

        if how == "delete":
            r = await async_client.delete(f"/api/v1/bookings/{test_booking.id}")
        else:
            r = await async_client.patch(
                f"/api/v1/bookings/{test_booking.id}", json={"status": "cancelled"}
            )
        assert r.status_code == 409
        assert r.json()["code"] == "booking.shift_over"
        await db_session.refresh(test_booking)
        assert test_booking.status == "confirmed"

    async def test_notes_can_still_change_after_the_shift(
        self,
        async_client: AsyncClient,
        test_booking: Booking,
        wall_clock: Callable[[datetime], None],
    ):
        wall_clock(datetime(2026, 5, 24, 12, 30))
        r = await async_client.patch(
            f"/api/v1/bookings/{test_booking.id}", json={"notes": "War gut"}
        )
        assert r.status_code == 200

    async def test_a_running_shift_can_still_be_booked(
        self,
        async_client: AsyncClient,
        test_shift: Shift,
        wall_clock: Callable[[datetime], None],
    ):
        """On a task without vouchers: someone who turns up to help joins it."""
        wall_clock(datetime(2026, 5, 24, 11, 59))
        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(test_shift.id)}
        )
        assert r.status_code == 201

    @pytest.mark.parametrize(
        "now",
        [
            datetime(2026, 5, 24, 8, 0),  # the minute it starts
            datetime(2026, 5, 24, 11, 59),  # one minute before its end
        ],
    )
    async def test_a_started_shift_that_earns_vouchers_cannot_be_booked(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_shift: Shift,
        wall_clock: Callable[[datetime], None],
        now: datetime,
    ):
        """Vouchers are a flat amount per shift: booked at 11:59, the whole
        08:00-12:00 shift would pay out a minute later."""
        test_task.vouchers_per_shift = 2
        db_session.add(test_task)
        await db_session.flush()
        wall_clock(now)

        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(test_shift.id)}
        )
        assert r.status_code == 409
        assert r.json()["code"] == "booking.shift_started"

        wall_clock(datetime(2026, 5, 24, 7, 59))
        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(test_shift.id)}
        )
        assert r.status_code == 201

    async def test_an_untimed_shift_that_earns_vouchers_only_before_its_day(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        wall_clock: Callable[[datetime], None],
    ):
        """It counts as worked at midnight, and shifts without times never
        clash, so on its day every one of them could be booked at 23:58."""
        test_task.vouchers_per_shift = 2
        db_session.add(test_task)
        untimed = Shift(
            task_id=test_task.id,
            title="Den ganzen Tag",
            date=date(2026, 6, 12),
            max_bookings=3,
        )
        db_session.add(untimed)
        await db_session.flush()

        wall_clock(datetime(2026, 6, 12, 23, 58))
        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(untimed.id)}
        )
        assert r.status_code == 409
        assert r.json()["code"] == "booking.shift_started"

        wall_clock(datetime(2026, 6, 11, 23, 59))
        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(untimed.id)}
        )
        assert r.status_code == 201

    async def test_a_cancelled_booking_on_a_started_voucher_shift_stays_cancelled(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_shift: Shift,
        test_user: User,
        wall_clock: Callable[[datetime], None],
    ):
        test_task.vouchers_per_shift = 2
        db_session.add(test_task)
        db_session.add(
            Booking(shift_id=test_shift.id, user_id=test_user.id, status="cancelled")
        )
        await db_session.flush()
        wall_clock(datetime(2026, 5, 24, 11, 59))

        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(test_shift.id)}
        )
        assert r.status_code == 409
        assert r.json()["code"] == "booking.shift_started"

    async def test_whoever_runs_a_voucher_task_may_join_a_started_shift(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_shift: Shift,
        test_user: User,
        wall_clock: Callable[[datetime], None],
    ):
        """Its people in charge (and the organisers) already shape its shifts."""
        test_task.vouchers_per_shift = 2
        db_session.add(test_task)
        db_session.add(TaskManager(task_id=test_task.id, user_id=test_user.id))
        await db_session.flush()
        wall_clock(datetime(2026, 5, 24, 11, 0))

        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(test_shift.id)}
        )
        assert r.status_code == 201

    async def test_a_row_the_check_missed_is_a_409_not_a_500(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_booking: Booking,
        test_shift: Shift,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """The insert runs in a savepoint: a row for the same person and shift
        that the check did not see breaks ``uq_booking_shift_user``, answers
        409 and leaves the transaction usable."""

        async def _not_found(*_args: Any, **_kwargs: Any) -> None:
            return None

        monkeypatch.setattr(crud_booking, "get_by_shift_and_user", _not_found)

        r = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(test_shift.id)}
        )
        assert r.status_code == 409
        assert r.json()["code"] == "booking.already_exists"
        await db_session.refresh(test_booking)
        assert test_booking.status == "confirmed"


@pytest.mark.asyncio
class TestBookingReminders:
    """The reminders a booking starts with, and what cancelling does to them."""

    @pytest.fixture(autouse=True)
    def _utc_before_the_shifts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A reminder is pending only while its moment is ahead in UTC."""
        monkeypatch.setattr(
            "app.logic.clock.utc_now", lambda: datetime(2026, 5, 1, 6, 0)
        )

    async def test_booking_again_after_a_cancel_starts_the_defaults_afresh(
        self, async_client: AsyncClient, db_session: AsyncSession, test_shift: Shift
    ):
        """Cancelling keeps the reminder rows, as cancelled. Booking the shift
        again reactivates the same booking, whose defaults used to be added
        next to those rows and break ``uq_reminder_booking_offset`` (a 500)."""
        booked = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(test_shift.id)}
        )
        assert booked.status_code == 201
        booking_id = uuid.UUID(booked.json()["id"])
        r = await async_client.delete(f"/api/v1/bookings/{booking_id}")
        assert r.status_code == 200
        assert await _reminders(db_session, booking_id) == [
            (15, "cancelled"),
            (1440, "cancelled"),
        ]

        again = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(test_shift.id)}
        )

        assert again.status_code == 201
        assert again.json()["id"] == str(booking_id)
        # test_user's defaults: 15 minutes by push, a day by email.
        assert await _reminders(db_session, booking_id) == [
            (15, "pending"),
            (1440, "pending"),
        ]

    async def test_cancelling_through_patch_cancels_the_reminders(
        self, async_client: AsyncClient, db_session: AsyncSession, test_shift: Shift
    ):
        booked = await async_client.post(
            "/api/v1/bookings/", json={"shift_id": str(test_shift.id)}
        )
        booking_id = uuid.UUID(booked.json()["id"])

        r = await async_client.patch(
            f"/api/v1/bookings/{booking_id}", json={"status": "cancelled"}
        )

        assert r.status_code == 200
        assert await _reminders(db_session, booking_id) == [
            (15, "cancelled"),
            (1440, "cancelled"),
        ]


async def _reminders(db: AsyncSession, booking_id: uuid.UUID) -> list[tuple[int, str]]:
    result = await db.execute(
        select(col(BookingReminder.offset_minutes), col(BookingReminder.status))
        .where(col(BookingReminder.booking_id) == booking_id)
        .order_by(col(BookingReminder.offset_minutes))
    )
    return [(offset, status) for offset, status in result.all()]


# ── Two requests at once ──────────────────────────────────────────

#: Long enough for the other transaction to reach the lock and wait on it.
SETTLE = 0.5


@dataclass
class LastPlace:
    """Committed for real: two members and a shift with one place."""

    sessions: async_sessionmaker[AsyncSession]
    shift_id: uuid.UUID
    first_id: uuid.UUID
    second_id: uuid.UUID


@pytest_asyncio.fixture
async def last_place(test_engine: AsyncEngine) -> AsyncGenerator[LastPlace]:
    """Like ``test_booking_leave_race.py``: two transactions on two
    connections, so the setup is committed and deleted again afterwards
    (the test database is shared), and the route is called directly."""
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    key = uuid.uuid4().hex[:8]
    async with sessions() as setup:
        owner, first, second = (
            User(
                subject=f"local|last-place-{role}-{key}",
                email=f"last-place-{role}-{key}@example.com",
                name=role.title(),
                roles=[],
                is_active=True,
            )
            for role in ("owner", "first", "second")
        )
        setup.add_all([owner, first, second])
        await setup.flush()
        event = Event(
            name=f"Last place {key}",
            start_date=date(2026, 6, 10),
            end_date=date(2026, 6, 14),
            created_by_id=owner.id,
        )
        setup.add(event)
        await setup.flush()
        setup.add_all(
            [
                EventMembership(user_id=owner.id, event_id=event.id, role="owner"),
                EventMembership(user_id=first.id, event_id=event.id, role="member"),
                EventMembership(user_id=second.id, event_id=event.id, role="member"),
            ]
        )
        task = Task(
            name="Theke",
            start_date=date(2026, 6, 12),
            end_date=date(2026, 6, 12),
            status="published",
            created_by_id=owner.id,
            event_id=event.id,
        )
        setup.add(task)
        await setup.flush()
        shift = Shift(
            task_id=task.id,
            title="Theke",
            date=date(2026, 6, 12),
            start_time=time(18),
            end_time=time(22),
            max_bookings=1,
        )
        setup.add(shift)
        await setup.commit()

    try:
        yield LastPlace(
            sessions=sessions,
            shift_id=shift.id,
            first_id=first.id,
            second_id=second.id,
        )
    finally:
        async with test_engine.begin() as conn:
            await conn.execute(delete(Booking).where(col(Booking.shift_id) == shift.id))
            await conn.execute(delete(Shift).where(col(Shift.id) == shift.id))
            await conn.execute(delete(Task).where(col(Task.id) == task.id))
            await conn.execute(
                delete(EventMembership).where(col(EventMembership.event_id) == event.id)
            )
            await conn.execute(delete(Event).where(col(Event.id) == event.id))
            await conn.execute(
                delete(User).where(col(User.id).in_([owner.id, first.id, second.id]))
            )


async def _book_as(session: AsyncSession, place: LastPlace, user_id: uuid.UUID) -> None:
    user = await session.get(User, user_id)
    assert user is not None
    await create_booking(
        BookingCreate(shift_id=place.shift_id), session, user, BackgroundTasks()
    )


async def _book_in_own_transaction(place: LastPlace, user_id: uuid.UUID) -> None:
    async with place.sessions() as session, session.begin():
        await _book_as(session, place, user_id)


async def _race(place: LastPlace, first_id: uuid.UUID, then_id: uuid.UUID) -> str:
    """Book as ``first_id`` and, before that commits, as ``then_id``.

    Asserts that the second request waits for the first, and returns the code
    it is refused with once the first has committed.
    """
    async with place.sessions() as booking:
        await booking.begin()
        await _book_as(booking, place, first_id)

        second = asyncio.create_task(_book_in_own_transaction(place, then_id))
        await asyncio.sleep(SETTLE)
        assert not second.done(), "the second booking did not wait for the first"
        await booking.commit()

    with pytest.raises(HTTPException) as refused:
        await asyncio.wait_for(second, timeout=10)
    assert refused.value.status_code == 409
    detail: Any = refused.value.detail
    return str(detail["code"])


async def _confirmed_user_ids(place: LastPlace) -> list[uuid.UUID]:
    async with place.sessions() as session:
        result = await session.execute(
            select(col(Booking.user_id)).where(
                col(Booking.shift_id) == place.shift_id,
                col(Booking.status) == "confirmed",
            )
        )
        return list(result.scalars().all())


@pytest.mark.asyncio
class TestBookingRaces:
    """Bookings of one shift take turns (``booking_capacity.lock_shifts``):
    counting the free places and inserting used to be two steps that two
    requests could interleave."""

    async def test_the_last_place_goes_to_exactly_one_of_two(
        self, last_place: LastPlace
    ) -> None:
        code = await _race(last_place, last_place.first_id, last_place.second_id)

        assert code == "booking.slot_full"
        assert await _confirmed_user_ids(last_place) == [last_place.first_id]

    async def test_a_booking_sent_twice_is_a_409_not_a_500(
        self, last_place: LastPlace
    ) -> None:
        """A double click: without the lock both requests insert, and the
        second hits ``uq_booking_shift_user``."""
        code = await _race(last_place, last_place.first_id, last_place.first_id)

        assert code == "booking.already_exists"
        assert await _confirmed_user_ids(last_place) == [last_place.first_id]

    async def test_a_shift_deleted_meanwhile_is_not_found(
        self, last_place: LastPlace
    ) -> None:
        """The insert's foreign key check waits for the organiser's delete and
        fails once it commits: the shift is gone, not already booked."""
        async with last_place.sessions() as organiser:
            await organiser.begin()
            await organiser.execute(
                delete(Shift).where(col(Shift.id) == last_place.shift_id)
            )
            booking = asyncio.create_task(
                _book_in_own_transaction(last_place, last_place.first_id)
            )
            await asyncio.sleep(SETTLE)
            assert not booking.done(), "the booking did not wait for the delete"
            await organiser.commit()

        with pytest.raises(HTTPException) as refused:
            await asyncio.wait_for(booking, timeout=10)
        assert refused.value.status_code == 404
        detail: Any = refused.value.detail
        assert detail["code"] == "shift.not_found"


async def _shift(db: AsyncSession, task: Task, day: date) -> Shift:
    shift = Shift(
        task_id=task.id,
        title="Kasse",
        date=day,
        start_time=time(10, 0),
        end_time=time(12, 0),
        max_bookings=3,
    )
    db.add(shift)
    await db.flush()
    return shift
