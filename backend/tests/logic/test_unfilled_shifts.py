"""Alerting organisers about shifts about to start with places open."""

import datetime as dt
from types import TracebackType
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic.notifications import reminder_poller
from app.logic.notifications.unfilled_shifts import (
    LOOKAHEAD_MINUTES,
    check_upcoming_shifts,
)
from app.models.booking import Booking
from app.models.event import Event
from app.models.notification import Notification, NotificationType
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User

TYPE_CODE = "shift.starting_soon_unfilled"

# The check reads the wall clock of each shift's event, so the instant is frozen
# and every zone reads it. ``NOW`` is that instant in the default zone, the one
# the fixture event is in, and every row below is built relative to it.
INSTANT = dt.datetime(2026, 5, 24, 10, 0, tzinfo=dt.timezone.utc)
NOW = INSTANT.astimezone(ZoneInfo("Europe/Berlin")).replace(tzinfo=None)
TODAY = NOW.date()


def _frozen_wall_clock(zone: str | None = None) -> dt.datetime:
    return INSTANT.astimezone(ZoneInfo(zone or "Europe/Berlin")).replace(tzinfo=None)


class _SessionContext:
    """Async context manager standing in for `async_session()`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


async def _run_check(db: AsyncSession) -> int:
    """Run the check against the test session with a frozen clock."""
    with (
        patch(
            "app.logic.notifications.unfilled_shifts.async_session",
            MagicMock(return_value=_SessionContext(db)),
        ),
        patch("app.logic.clock.wall_clock_now", _frozen_wall_clock),
        patch(
            "app.logic.clock.utc_now",
            lambda: INSTANT.replace(tzinfo=None),
        ),
        patch(
            "app.logic.notifications.service.EmailChannel.is_configured",
            return_value=False,
        ),
        patch(
            "app.logic.notifications.service.PushChannel.is_configured",
            return_value=False,
        ),
        patch(
            "app.logic.notifications.service.TelegramChannel.is_configured",
            return_value=False,
        ),
    ):
        return await check_upcoming_shifts()


@pytest.mark.asyncio
class TestCheckUpcomingShifts:
    """Test suite for the upcoming-unfilled-shift check."""

    async def _seed_type(self, db: AsyncSession) -> NotificationType:
        """Register the notification type the check dispatches."""
        nt = NotificationType(
            code=TYPE_CODE,
            name="Shift Starting Soon (Unfilled)",
            description="Alert when a shift starts soon but still has open spots",
            category="shift",
            default_channels=["email"],
            is_active=True,
        )
        db.add(nt)
        await db.flush()
        await db.refresh(nt)
        return nt

    async def _make_shift(
        self,
        db: AsyncSession,
        task: Task,
        *,
        starts_in: dt.timedelta,
        on_date: dt.date | None = None,
        max_bookings: int = 2,
    ) -> Shift:
        """Create a shift starting `starts_in` from the frozen now."""
        start = NOW + starts_in
        shift = Shift(
            task_id=task.id,
            title="Einlasskontrolle",
            description="Einlass am Haupteingang",
            date=on_date or TODAY,
            start_time=start.time(),
            end_time=(start + dt.timedelta(hours=2)).time(),
            location="Haupteingang",
            max_bookings=max_bookings,
        )
        db.add(shift)
        await db.flush()
        await db.refresh(shift)
        return shift

    async def _make_booking(
        self, db: AsyncSession, shift: Shift, user: User, status: str
    ) -> Booking:
        """Create a booking for a shift with an explicit status."""
        booking = Booking(shift_id=shift.id, user_id=user.id, status=status)
        db.add(booking)
        await db.flush()
        await db.refresh(booking)
        return booking

    async def _make_previous_alert(
        self,
        db: AsyncSession,
        shift: Shift,
        recipient: User,
        *,
        age: dt.timedelta,
    ) -> Notification:
        """Insert an already-dispatched alert for `shift`, created `age` ago."""
        data: dict[str, str | int | None] = {"slot_id": str(shift.id)}
        notif = Notification(
            recipient_id=recipient.id,
            notification_type_code=TYPE_CODE,
            title="Unfilled Shift Starting Soon",
            body="Previously dispatched alert",
            data=data,
            created_at=INSTANT.replace(tzinfo=None) - age,
        )
        db.add(notif)
        await db.flush()
        await db.refresh(notif)
        return notif

    async def _alerts(self, db: AsyncSession) -> list[Notification]:
        """All dispatched unfilled-shift alerts currently in the database."""
        result = await db.execute(
            select(Notification).where(
                col(Notification.notification_type_code) == TYPE_CODE
            )
        )
        return list(result.scalars().all())

    async def test_notifies_the_events_organisers_about_unfilled_shift(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_admin_user: User,
        test_event_admin_user: User,
        test_user: User,
    ) -> None:
        """A shift starting inside the window with open spots alerts the event's
        owner and admins, not its members."""
        await self._seed_type(db_session)
        shift = await self._make_shift(
            db_session, test_task, starts_in=dt.timedelta(minutes=10)
        )

        sent = await _run_check(db_session)

        assert sent == 1
        alerts = await self._alerts(db_session)
        assert {a.recipient_id for a in alerts} == {
            test_admin_user.id,
            test_event_admin_user.id,
        }
        assert test_user.id not in {a.recipient_id for a in alerts}
        alert = alerts[0]
        assert alert.notification_type_code == TYPE_CODE
        assert alert.data is not None
        assert alert.data["slot_id"] == str(shift.id)
        assert alert.data["task_id"] == str(test_task.id)
        assert alert.data["open_spots"] == 2
        assert alert.data["confirmed"] == 0
        assert alert.data["max_bookings"] == 2
        assert shift.title in alert.body
        assert f"{LOOKAHEAD_MINUTES} minutes" in alert.body
        assert "0 of 2 places" in alert.body

    async def test_a_platform_admin_outside_the_event_hears_nothing(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_admin_user: User,
    ) -> None:
        """Only the event's roster counts, whatever a global role says."""
        event = await db_session.get(Event, test_task.event_id)
        assert event is not None
        await self._seed_type(db_session)
        await self._make_shift(
            db_session, test_task, starts_in=dt.timedelta(minutes=10)
        )
        other_admin = User(
            subject="local|platform-admin",
            email="platform@example.com",
            is_active=True,
            roles=["admin"],
        )
        db_session.add(other_admin)
        await db_session.flush()

        await _run_check(db_session)

        recipients = {a.recipient_id for a in await self._alerts(db_session)}
        assert other_admin.id not in recipients
        assert test_admin_user.id in recipients

    async def test_each_shift_is_judged_on_its_own_events_clock(
        self,
        db_session: AsyncSession,
        test_task: Task,
    ) -> None:
        """At the same instant, 19:10 is coming up in Tokyo and hours off in
        the default zone: only the event in Tokyo is alerted about."""
        await self._seed_type(db_session)
        event = await db_session.get(Event, test_task.event_id)
        assert event is not None
        event.timezone = "Asia/Tokyo"
        db_session.add(event)
        await db_session.flush()
        tokyo_now = _frozen_wall_clock("Asia/Tokyo")
        coming_up = Shift(
            task_id=test_task.id,
            title="Tokyo",
            date=tokyo_now.date(),
            start_time=(tokyo_now + dt.timedelta(minutes=10)).time(),
            max_bookings=1,
        )
        default_zone_only = await self._make_shift(
            db_session, test_task, starts_in=dt.timedelta(minutes=10)
        )
        db_session.add(coming_up)
        await db_session.flush()

        sent = await _run_check(db_session)

        assert sent == 1
        alerts = await self._alerts(db_session)
        assert {a.data["slot_id"] for a in alerts if a.data} == {str(coming_up.id)}
        assert str(default_zone_only.id) not in {
            a.data["slot_id"] for a in alerts if a.data
        }

    async def test_the_window_crosses_midnight(
        self,
        db_session: AsyncSession,
        test_task: Task,
    ) -> None:
        """At 23:50, a shift at 00:10 is twenty minutes away, on the next date.
        The check used to compare times of day on today's date only."""
        await self._seed_type(db_session)
        event = await db_session.get(Event, test_task.event_id)
        assert event is not None
        # 10:00 UTC is 23:50 at this fixed offset, and the frozen instant stays.
        event.timezone = "Etc/GMT-13"  # UTC+13: 23:00 at 10:00 UTC
        db_session.add(event)
        await db_session.flush()
        with patch("app.logic.notifications.unfilled_shifts.LOOKAHEAD_MINUTES", 90):
            tomorrow = _frozen_wall_clock("Etc/GMT-13").date() + dt.timedelta(days=1)
            shift = Shift(
                task_id=test_task.id,
                title="After midnight",
                date=tomorrow,
                start_time=dt.time(0, 10),
                max_bookings=1,
            )
            db_session.add(shift)
            await db_session.flush()

            assert await _run_check(db_session) == 1

    @pytest.mark.parametrize(
        ("task_status", "event_status"),
        [("draft", "published"), ("published", "draft")],
    )
    async def test_ignores_what_is_not_published(
        self,
        db_session: AsyncSession,
        test_task: Task,
        task_status: str,
        event_status: str,
    ) -> None:
        await self._seed_type(db_session)
        event = await db_session.get(Event, test_task.event_id)
        assert event is not None
        event.status = event_status
        test_task.status = task_status
        db_session.add_all([event, test_task])
        await self._make_shift(
            db_session, test_task, starts_in=dt.timedelta(minutes=10)
        )

        assert await _run_check(db_session) == 0

    async def test_ignores_a_demo_event(
        self,
        db_session: AsyncSession,
        test_task: Task,
    ) -> None:
        await self._seed_type(db_session)
        event = await db_session.get(Event, test_task.event_id)
        assert event is not None
        event.is_sandbox = True
        db_session.add(event)
        await self._make_shift(
            db_session, test_task, starts_in=dt.timedelta(minutes=10)
        )

        assert await _run_check(db_session) == 0

    async def test_skips_full_shift(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
        test_admin_user: User,
    ) -> None:
        """A shift whose confirmed bookings fill every spot is skipped."""
        _ = test_admin_user  # an organiser exists, or nothing could be sent
        await self._seed_type(db_session)
        shift = await self._make_shift(
            db_session,
            test_task,
            starts_in=dt.timedelta(minutes=10),
            max_bookings=1,
        )
        await self._make_booking(db_session, shift, test_user, "confirmed")

        sent = await _run_check(db_session)

        assert sent == 0
        assert await self._alerts(db_session) == []

    async def test_cancelled_bookings_do_not_fill_the_shift(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
        test_admin_user: User,
    ) -> None:
        """Only confirmed bookings count toward a shift being full."""
        _ = test_admin_user
        await self._seed_type(db_session)
        shift = await self._make_shift(
            db_session,
            test_task,
            starts_in=dt.timedelta(minutes=10),
            max_bookings=1,
        )
        await self._make_booking(db_session, shift, test_user, "cancelled")

        sent = await _run_check(db_session)

        assert sent == 1
        alerts = await self._alerts(db_session)
        assert alerts
        assert alerts[0].data is not None
        assert alerts[0].data["confirmed"] == 0
        assert alerts[0].data["open_spots"] == 1

    async def test_ignores_shift_outside_lookahead_window(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_admin_user: User,
    ) -> None:
        """A shift starting well after the lookahead window is ignored."""
        _ = test_admin_user
        await self._seed_type(db_session)
        await self._make_shift(
            db_session,
            test_task,
            starts_in=dt.timedelta(minutes=LOOKAHEAD_MINUTES + 90),
        )

        sent = await _run_check(db_session)

        assert sent == 0
        assert await self._alerts(db_session) == []

    async def test_ignores_shift_that_already_started(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_admin_user: User,
    ) -> None:
        """A shift that started before now is no longer 'upcoming'."""
        _ = test_admin_user
        await self._seed_type(db_session)
        await self._make_shift(
            db_session, test_task, starts_in=dt.timedelta(minutes=-10)
        )

        sent = await _run_check(db_session)

        assert sent == 0
        assert await self._alerts(db_session) == []

    async def test_ignores_shift_on_another_date(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_admin_user: User,
    ) -> None:
        """A shift at the right time of day but on another date is ignored."""
        _ = test_admin_user
        await self._seed_type(db_session)
        await self._make_shift(
            db_session,
            test_task,
            starts_in=dt.timedelta(minutes=10),
            on_date=TODAY + dt.timedelta(days=1),
        )

        sent = await _run_check(db_session)

        assert sent == 0
        assert await self._alerts(db_session) == []

    async def test_skips_shift_alerted_within_the_last_hour(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_admin_user: User,
    ) -> None:
        """A shift alerted about 10 minutes ago is not alerted about again."""
        await self._seed_type(db_session)
        shift = await self._make_shift(
            db_session, test_task, starts_in=dt.timedelta(minutes=10)
        )
        await self._make_previous_alert(
            db_session, shift, test_admin_user, age=dt.timedelta(minutes=10)
        )

        sent = await _run_check(db_session)

        assert sent == 0
        # Only the pre-existing alert remains — nothing new was dispatched.
        alerts = await self._alerts(db_session)
        assert len(alerts) == 1
        assert alerts[0].body == "Previously dispatched alert"

    async def test_alerts_again_when_previous_alert_is_stale(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_admin_user: User,
    ) -> None:
        """An alert older than an hour no longer suppresses a new one."""
        await self._seed_type(db_session)
        shift = await self._make_shift(
            db_session, test_task, starts_in=dt.timedelta(minutes=10)
        )
        await self._make_previous_alert(
            db_session, shift, test_admin_user, age=dt.timedelta(hours=3)
        )

        sent = await _run_check(db_session)

        assert sent == 1
        alerts = await self._alerts(db_session)
        bodies = [a.body for a in alerts]
        assert "Previously dispatched alert" in bodies
        assert any(shift.title in body for body in bodies)

    async def test_returns_zero_when_no_shifts_exist(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
    ) -> None:
        """An empty schedule sends nothing and reports zero."""
        _ = test_admin_user
        await self._seed_type(db_session)

        sent = await _run_check(db_session)

        assert sent == 0
        assert await self._alerts(db_session) == []


@pytest.mark.asyncio
class TestPollerRunsTheCheck:
    async def test_a_failure_is_logged_and_does_not_stop_the_poller(self) -> None:
        with patch.object(
            reminder_poller,
            "check_upcoming_shifts",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await reminder_poller._unfilled_cycle()  # pyright: ignore[reportPrivateUsage]
