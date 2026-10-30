"""Route tests for Booking endpoints."""

from collections.abc import Callable
from datetime import date, datetime, time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.shift import Shift
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User

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
