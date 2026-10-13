"""Route tests for booking.time_conflict and the matching collision marker."""

from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User

DAY = date(2026, 5, 24)


async def _shift(
    db_session: AsyncSession,
    task: Task,
    start: time | None,
    end: time | None,
    *,
    day: date = DAY,
    title: str = "Shift",
) -> Shift:
    shift = Shift(
        task_id=task.id,
        title=title,
        date=day,
        start_time=start,
        end_time=end,
        max_bookings=5,
    )
    db_session.add(shift)
    await db_session.flush()
    await db_session.refresh(shift)
    return shift


async def _book(
    db_session: AsyncSession, shift: Shift, user: User, status: str = "confirmed"
) -> Booking:
    booking = Booking(shift_id=shift.id, user_id=user.id, status=status)
    db_session.add(booking)
    await db_session.flush()
    return booking


async def _post_booking(client: AsyncClient, shift: Shift):
    return await client.post("/api/v1/bookings/", json={"shift_id": str(shift.id)})


@pytest.mark.asyncio
class TestBookingTimeConflict:
    async def test_overlapping_shift_is_rejected(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        held = await _shift(db_session, test_task, time(8), time(12), title="Gate")
        await _book(db_session, held, test_user)
        wanted = await _shift(db_session, test_task, time(10), time(14))

        r = await _post_booking(async_client, wanted)

        assert r.status_code == 409
        body = r.json()
        assert body["code"] == "booking.time_conflict"
        clash = body["conflicting_shift"]
        assert clash["id"] == str(held.id)
        assert clash["title"] == "Gate"
        assert clash["task_name"] == test_task.name
        assert clash["date"] == "2026-05-24"
        assert clash["start_time"] == "08:00:00"
        assert clash["end_time"] == "12:00:00"

    async def test_contained_shift_is_rejected(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        held = await _shift(db_session, test_task, time(8), time(16))
        await _book(db_session, held, test_user)
        wanted = await _shift(db_session, test_task, time(10), time(11))

        r = await _post_booking(async_client, wanted)

        assert r.status_code == 409
        assert r.json()["code"] == "booking.time_conflict"

    async def test_back_to_back_shifts_are_fine(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        held = await _shift(db_session, test_task, time(8), time(12))
        await _book(db_session, held, test_user)
        after = await _shift(db_session, test_task, time(12), time(16))
        before = await _shift(db_session, test_task, time(4), time(8))

        assert (await _post_booking(async_client, after)).status_code == 201
        assert (await _post_booking(async_client, before)).status_code == 201

    async def test_cancelled_booking_is_ignored(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        held = await _shift(db_session, test_task, time(8), time(12))
        await _book(db_session, held, test_user, status="cancelled")
        wanted = await _shift(db_session, test_task, time(10), time(14))

        r = await _post_booking(async_client, wanted)

        assert r.status_code == 201

    async def test_other_users_bookings_are_ignored(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_admin_user: User,
    ):
        held = await _shift(db_session, test_task, time(8), time(12))
        await _book(db_session, held, test_admin_user)
        wanted = await _shift(db_session, test_task, time(10), time(14))

        r = await _post_booking(async_client, wanted)

        assert r.status_code == 201

    async def test_overnight_shift_clashes_with_next_morning(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        night = await _shift(db_session, test_task, time(22), time(2))
        await _book(db_session, night, test_user)
        next_morning = await _shift(
            db_session, test_task, time(1), time(5), day=date(2026, 5, 25)
        )

        r = await _post_booking(async_client, next_morning)

        assert r.status_code == 409
        assert r.json()["conflicting_shift"]["id"] == str(night.id)

    async def test_booking_overnight_shift_over_next_morning(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        next_morning = await _shift(
            db_session, test_task, time(1), time(5), day=date(2026, 5, 25)
        )
        await _book(db_session, next_morning, test_user)
        night = await _shift(db_session, test_task, time(22), time(2))

        r = await _post_booking(async_client, night)

        assert r.status_code == 409

    async def test_same_times_on_other_days_are_fine(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        held = await _shift(db_session, test_task, time(8), time(12))
        await _book(db_session, held, test_user)
        tomorrow = await _shift(
            db_session, test_task, time(8), time(12), day=date(2026, 5, 25)
        )

        r = await _post_booking(async_client, tomorrow)

        assert r.status_code == 201

    async def test_untimed_shifts_never_clash(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        held = await _shift(db_session, test_task, time(8), time(12))
        await _book(db_session, held, test_user)
        all_day = await _shift(db_session, test_task, None, None)

        r = await _post_booking(async_client, all_day)

        assert r.status_code == 201

    async def test_rebooking_a_cancelled_overlapping_shift_is_rejected(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        held = await _shift(db_session, test_task, time(8), time(12))
        await _book(db_session, held, test_user)
        wanted = await _shift(db_session, test_task, time(10), time(14))
        await _book(db_session, wanted, test_user, status="cancelled")

        r = await _post_booking(async_client, wanted)

        assert r.status_code == 409
        assert r.json()["code"] == "booking.time_conflict"


@pytest.mark.asyncio
class TestCollisionMarker:
    async def test_shift_list_marks_colliding_shifts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        held = await _shift(db_session, test_task, time(8), time(12))
        await _book(db_session, held, test_user)
        clashing = await _shift(db_session, test_task, time(10), time(14))
        free = await _shift(db_session, test_task, time(12), time(16))

        r = await async_client.get(
            "/api/v1/shifts/", params={"task_id": str(test_task.id)}
        )

        assert r.status_code == 200
        flags = {
            item["id"]: item["collides_with_my_booking"] for item in r.json()["items"]
        }
        assert flags[str(held.id)] is False
        assert flags[str(clashing.id)] is True
        assert flags[str(free.id)] is False

    async def test_shift_detail_marks_collision(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        held = await _shift(db_session, test_task, time(8), time(12))
        await _book(db_session, held, test_user)
        clashing = await _shift(db_session, test_task, time(10), time(14))

        r = await async_client.get(f"/api/v1/shifts/{clashing.id}")

        assert r.status_code == 200
        assert r.json()["collides_with_my_booking"] is True

    async def test_shift_window_marks_overnight_collision(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
    ):
        # The booked shift sits the evening before the requested window.
        night = await _shift(db_session, test_task, time(22), time(2))
        await _book(db_session, night, test_user)
        next_morning = await _shift(
            db_session, test_task, time(1), time(5), day=date(2026, 5, 25)
        )
        later = await _shift(
            db_session, test_task, time(9), time(12), day=date(2026, 5, 25)
        )

        r = await async_client.get(
            f"/api/v1/tasks/{test_task.id}/shift-window",
            params={"start_date": "2026-05-25", "days": 3},
        )

        assert r.status_code == 200
        flags = {s["id"]: s["collides_with_my_booking"] for s in r.json()["shifts"]}
        assert flags == {str(next_morning.id): True, str(later.id): False}
