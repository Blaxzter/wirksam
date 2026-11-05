# pyright: reportPrivateUsage=false
"""Unit tests for the background booking-reminder poller.

The poller is time-dependent. ``crud_reminder.fetch_due_reminders`` computes
``now`` internally, so the selection-window tests build ``remind_at`` relative to
a reference ``now`` captured immediately before the call and assert the
``remind_at <= now`` boundary explicitly: exactly at the boundary, one second
inside, one second outside, and the already-reminded (``status="sent"``) case.

Every test that touches the database patches the poller's module-level
``async_session`` so that it yields the transactional ``db_session`` fixture
instead of opening a real connection. The lifecycle tests for
``run_reminder_poller`` use a fully mocked session instead, because the only SQL
it runs there is the ``pg_try_advisory_lock`` / ``pg_advisory_unlock`` pair.
"""

import asyncio
import datetime as dt
import uuid
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.logic.notifications.messages import format_time_until
from app.logic.notifications.reminder_poller import (
    _cleanup_cycle,
    _poll_cycle,
    _process_reminder,
    run_reminder_poller,
)
from app.models.booking import Booking
from app.models.booking_reminder import BookingReminder
from app.models.event import Event
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User

MODULE = "app.logic.notifications.reminder_poller"


# ── helpers ───────────────────────────────────────────────────────


@contextmanager
def _patched_session(db: object) -> Generator[MagicMock, None, None]:
    """Point the poller's module-level ``async_session`` at ``db``.

    The poller does ``async with async_session() as db``; a real session would
    be closed on exit, so the replacement is a context manager that simply
    yields the test session and leaves it open.
    """

    @asynccontextmanager
    async def _session_cm() -> AsyncGenerator[object, None]:
        yield db

    factory = MagicMock(side_effect=_session_cm)
    with patch(f"{MODULE}.async_session", factory):
        yield factory


def _advisory_lock_session(*, acquired: bool) -> MagicMock:
    """A stand-in session that answers the ``pg_try_advisory_lock`` probe."""
    lock_result = MagicMock()
    lock_result.scalar.return_value = acquired

    db = MagicMock()
    db.execute = AsyncMock(return_value=lock_result)
    db.commit = AsyncMock()
    return db


def _fake_asyncio(sleep: object) -> MagicMock:
    """A stand-in for the ``asyncio`` module inside the poller.

    Only ``sleep`` (so the 30 s poll interval does not stall the suite) and
    ``CancelledError`` (which must stay the real class so the poller's ``except``
    clauses still match) are used by ``run_reminder_poller``.
    """
    fake = MagicMock()
    fake.CancelledError = asyncio.CancelledError
    fake.sleep = sleep
    return fake


async def _create_reminder(
    db: AsyncSession,
    *,
    booking: Booking,
    user: User,
    shift_id: uuid.UUID | None,
    remind_at: dt.datetime,
    offset_minutes: int,
    status: str = "pending",
    channels: list[str] | None = None,
) -> BookingReminder:
    """Persist a BookingReminder row with an explicit ``remind_at``."""
    reminder = BookingReminder(
        booking_id=booking.id,
        user_id=user.id,
        shift_id=shift_id,
        remind_at=remind_at,
        offset_minutes=offset_minutes,
        status=status,
        channels=channels if channels is not None else ["push"],
    )
    db.add(reminder)
    await db.flush()
    await db.refresh(reminder)
    return reminder


async def _dispatch_reminder(
    db: AsyncSession, reminder: BookingReminder
) -> tuple[MagicMock, AsyncMock]:
    """Run ``_process_reminder`` with ``NotificationService`` mocked out.

    Returns ``(service_class_mock, notify_mock)``.
    """
    notify = AsyncMock(return_value=[])
    service_cls = MagicMock()
    service_cls.return_value.notify = notify

    with _patched_session(db), patch(f"{MODULE}.NotificationService", service_cls):
        await _process_reminder(reminder)

    return service_cls, notify


# ── format_time_until ────────────────────────────────────────────


class TestFormatTimeUntil:
    """Table tests for the human-readable time-until helper."""

    @pytest.mark.parametrize(
        ("offset_minutes", "lang", "expected"),
        [
            # Below one hour: plain minutes in both languages.
            (0, "en", "in 0 minutes"),
            (1, "en", "in 1 minutes"),
            (15, "en", "in 15 minutes"),
            (59, "en", "in 59 minutes"),
            (0, "de", "in 0 Minuten"),
            (15, "de", "in 15 Minuten"),
            (59, "de", "in 59 Minuten"),
            # Exactly one hour: singular, no remainder.
            (60, "en", "in 1 hour"),
            (60, "de", "in 1 Stunde"),
            # Whole hours, plural.
            (120, "en", "in 2 hours"),
            (120, "de", "in 2 Stunden"),
            (1380, "en", "in 23 hours"),
            (1380, "de", "in 23 Stunden"),
            # Hours with a leftover minute remainder.
            (61, "en", "in 1h 1min"),
            (61, "de", "in 1 Std. 1 Min."),
            (90, "en", "in 1h 30min"),
            (90, "de", "in 1 Std. 30 Min."),
            (1439, "en", "in 23h 59min"),
            (1439, "de", "in 23 Std. 59 Min."),
            # Exactly one day: singular.
            (1440, "en", "in 1 day"),
            (1440, "de", "in 1 Tag"),
            # More than one day: plural.
            (2880, "en", "in 2 days"),
            (2880, "de", "in 2 Tagen"),
            (10080, "en", "in 7 days"),
            (10080, "de", "in 7 Tagen"),
            # An unsupported language uses the English wording.
            (30, "fr", "in 30 minutes"),
            (60, "fr", "in 1 hour"),
            (90, "fr", "in 1h 30min"),
            (1440, "fr", "in 1 day"),
        ],
    )
    def test_format_time_until(
        self, offset_minutes: int, lang: str, expected: str
    ) -> None:
        """Every offset bucket renders the documented wording per language."""
        assert format_time_until(offset_minutes, lang) == expected


# ── selection window (remind_at <= now AND status == "pending") ───


@pytest.mark.asyncio
class TestReminderSelectionWindow:
    """Explicit boundary tests for the poller's due-reminder selection.

    ``fetch_due_reminders`` reads the clock itself, so each test creates a
    single row relative to a reference ``now`` and queries immediately
    afterwards. The gap between the two clock reads is one INSERT, so a
    one-second margin is comfortably outside it.
    """

    async def test_reminder_exactly_at_now_is_due(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ) -> None:
        """remind_at == now is inside the window: the comparison is ``<=``."""
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        reminder = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=now,
            offset_minutes=15,
        )

        due = await crud_reminder.fetch_due_reminders(db_session, limit=50)

        assert reminder.id in {r.id for r in due}

    async def test_reminder_one_second_before_now_is_due(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ) -> None:
        """One second inside the window is selected."""
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        reminder = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=now - dt.timedelta(seconds=1),
            offset_minutes=30,
        )

        due = await crud_reminder.fetch_due_reminders(db_session, limit=50)

        assert reminder.id in {r.id for r in due}

    async def test_reminder_one_second_after_now_is_not_due(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ) -> None:
        """One second outside the window is not selected yet."""
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        reminder = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=now + dt.timedelta(seconds=1),
            offset_minutes=60,
        )

        due = await crud_reminder.fetch_due_reminders(db_session, limit=50)

        assert reminder.id not in {r.id for r in due}

    async def test_reminder_well_in_the_future_is_not_due(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ) -> None:
        """A comfortably future reminder is never selected (timing-proof case)."""
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        reminder = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=now + dt.timedelta(minutes=5),
            offset_minutes=120,
        )

        due = await crud_reminder.fetch_due_reminders(db_session, limit=50)

        assert reminder.id not in {r.id for r in due}

    async def test_already_sent_reminder_is_not_due(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ) -> None:
        """An already-reminded row stays out of the window even when overdue."""
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        reminder = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=now - dt.timedelta(minutes=5),
            offset_minutes=1440,
            status="sent",
        )

        due = await crud_reminder.fetch_due_reminders(db_session, limit=50)

        assert reminder.id not in {r.id for r in due}

    async def test_cancelled_reminder_is_not_due(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ) -> None:
        """A cancelled row is likewise excluded from the pending selection."""
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        reminder = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=now - dt.timedelta(minutes=5),
            offset_minutes=2880,
            status="cancelled",
        )

        due = await crud_reminder.fetch_due_reminders(db_session, limit=50)

        assert reminder.id not in {r.id for r in due}


# ── _poll_cycle ───────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPollCycle:
    """Test suite for a single poll cycle."""

    async def test_returns_zero_when_nothing_is_due(
        self, db_session: AsyncSession
    ) -> None:
        """An empty due-set short-circuits and reports zero work."""
        with _patched_session(db_session):
            processed = await _poll_cycle()

        assert processed == 0

    async def test_processes_due_reminders(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ) -> None:
        """Due reminders are snapshotted, dispatched, and counted."""
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        reminder = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=now - dt.timedelta(minutes=5),
            offset_minutes=60,
            channels=["push", "email"],
        )
        reminder_id = reminder.id
        mock_process = AsyncMock()

        with (
            _patched_session(db_session),
            patch(f"{MODULE}._process_reminder", mock_process),
        ):
            processed = await _poll_cycle()

        assert processed == 1
        call = mock_process.await_args
        assert call is not None
        dispatched = call.args[0]
        assert dispatched.id == reminder_id
        assert dispatched.offset_minutes == 60
        assert dispatched.channels == ["push", "email"]
        assert dispatched.status == "pending"

    async def test_ignores_reminders_that_are_not_yet_due(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ) -> None:
        """A future reminder is left alone by the cycle."""
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=now + dt.timedelta(minutes=5),
            offset_minutes=60,
        )
        mock_process = AsyncMock()

        with (
            _patched_session(db_session),
            patch(f"{MODULE}._process_reminder", mock_process),
        ):
            processed = await _poll_cycle()

        assert processed == 0
        mock_process.assert_not_awaited()

    async def test_swallows_fetch_errors(self, db_session: AsyncSession) -> None:
        """A failing fetch is logged and reported as zero work, not raised."""
        crud = MagicMock()
        crud.fetch_due_reminders = AsyncMock(
            side_effect=RuntimeError("connection lost")
        )
        mock_logger = MagicMock()

        with (
            _patched_session(db_session),
            patch(f"{MODULE}.crud_reminder", crud),
            patch(f"{MODULE}.logger", mock_logger),
        ):
            processed = await _poll_cycle()

        assert processed == 0
        mock_logger.exception.assert_called_once_with("Failed to fetch due reminders")


# ── _process_reminder ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestProcessReminder:
    """Test suite for dispatching a single reminder."""

    @pytest.mark.parametrize(
        ("zone", "expected"),
        [("Asia/Tokyo", " (Asia/Tokyo)"), ("Europe/Berlin", "")],
    )
    async def test_the_time_says_whose_clock_it_is_when_that_is_not_the_usual_one(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
        test_event: Event,
        monkeypatch: pytest.MonkeyPatch,
        zone: str,
        expected: str,
    ) -> None:
        monkeypatch.setattr(settings, "EVENT_TIMEZONE", "Europe/Berlin")
        test_event.timezone = zone
        db_session.add(test_event)
        await db_session.flush()
        reminder = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=dt.datetime(2026, 5, 24, 7, 0),
            offset_minutes=60,
        )

        _, notify = await _dispatch_reminder(db_session, reminder)

        call = notify.await_args
        assert call is not None
        _, body = call.kwargs["message_factory"]("en")
        end = test_shift.end_time
        assert end is not None
        assert f"–{end.strftime('%H:%M')}{expected}\n" in body

    async def test_dispatches_and_marks_sent(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
        test_task: Task,
        test_event: Event,
    ) -> None:
        """The happy path notifies the booker and retires the reminder."""
        test_task.event_id = test_event.id
        await db_session.flush()

        reminder = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=dt.datetime(2026, 5, 24, 7, 0),
            offset_minutes=60,
            channels=["push", "email"],
        )

        service_cls, notify = await _dispatch_reminder(db_session, reminder)

        service_cls.assert_called_once_with(db_session)
        call = notify.await_args
        assert call is not None
        kwargs = call.kwargs
        assert kwargs["recipient_ids"] == [test_user.id]
        assert kwargs["type_code"] == "booking.reminder"
        assert kwargs["only_channels"] == ["push", "email"]
        assert kwargs["data"] == {
            "booking_id": str(test_booking.id),
            "slot_id": str(test_shift.id),
            "task_id": str(test_task.id),
        }
        assert kwargs["scope_chain"] == [
            ("shift", test_shift.id),
            ("task", test_task.id),
            ("event", test_event.id),
        ]

        await db_session.refresh(reminder)
        assert reminder.status == "sent"

    async def test_scope_chain_omits_event_when_task_has_none(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
        test_task: Task,
    ) -> None:
        """A standalone task contributes no event scope.

        Fixture tasks now live inside an event, so detach this one first —
        the branch under test is the legacy ``event_id IS NULL`` case.
        """
        test_task.event_id = None
        db_session.add(test_task)
        await db_session.flush()

        reminder = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=dt.datetime(2026, 5, 24, 7, 0),
            offset_minutes=15,
        )

        _, notify = await _dispatch_reminder(db_session, reminder)

        call = notify.await_args
        assert call is not None
        assert call.kwargs["scope_chain"] == [
            ("shift", test_shift.id),
            ("task", test_task.id),
        ]

    async def test_message_factory_renders_shift_context(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ) -> None:
        """The deferred message factory localizes title, body, and time-until."""
        reminder = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=dt.datetime(2026, 5, 24, 7, 0),
            offset_minutes=60,
        )

        _, notify = await _dispatch_reminder(db_session, reminder)

        call = notify.await_args
        assert call is not None
        factory = call.kwargs["message_factory"]

        title_en, body_en = factory("en")
        assert title_en == "Upcoming Booking"
        assert "Einlasskontrolle" in body_en
        assert "in 1 hour" in body_en
        assert "24.05.2026" in body_en
        assert "08:00" in body_en
        assert "12:00" in body_en
        assert "Haupteingang" in body_en

        title_de, body_de = factory("de")
        assert title_de == "Bevorstehende Buchung"
        assert "in 1 Stunde" in body_de
        assert "Einlasskontrolle" in body_de

    async def test_message_factory_tolerates_missing_shift_details(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_task: Task,
    ) -> None:
        """A shift without times or location renders empty placeholders."""
        bare_shift = Shift(
            task_id=test_task.id,
            title="Aufbau",
            date=dt.date(2026, 5, 25),
            max_bookings=1,
        )
        db_session.add(bare_shift)
        await db_session.flush()
        await db_session.refresh(bare_shift)

        reminder = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=bare_shift.id,
            remind_at=dt.datetime(2026, 5, 24, 7, 0),
            offset_minutes=1440,
        )

        _, notify = await _dispatch_reminder(db_session, reminder)

        call = notify.await_args
        assert call is not None
        _, body = call.kwargs["message_factory"]("en")

        assert "Aufbau" in body
        assert "25.05.2026" in body
        assert "in 1 day" in body
        # start_time / end_time / location all fall back to empty strings.
        assert ":" not in body  # no HH:MM was rendered
        assert body.endswith(" ")  # trailing empty location

    async def test_deleted_shift_marks_sent_without_notifying(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
    ) -> None:
        """A reminder whose shift was deleted (FK set to NULL) is retired quietly."""
        reminder = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=None,
            remind_at=dt.datetime(2026, 5, 24, 7, 0),
            offset_minutes=15,
        )

        service_cls, notify = await _dispatch_reminder(db_session, reminder)

        service_cls.assert_not_called()
        notify.assert_not_awaited()
        await db_session.refresh(reminder)
        assert reminder.status == "sent"

    async def test_unknown_shift_id_does_not_notify(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
    ) -> None:
        """A snapshot pointing at a shift that no longer exists dispatches nothing."""
        reminder = BookingReminder(
            id=uuid.uuid4(),
            booking_id=test_booking.id,
            user_id=test_user.id,
            shift_id=uuid.uuid4(),
            remind_at=dt.datetime(2026, 5, 24, 7, 0),
            offset_minutes=15,
            status="pending",
            channels=["push"],
        )

        service_cls, notify = await _dispatch_reminder(db_session, reminder)

        service_cls.assert_not_called()
        notify.assert_not_awaited()

    async def test_swallows_and_logs_dispatch_errors(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ) -> None:
        """A failing notification is logged; the poller keeps running.

        The failure path rolls the session back, so this test deliberately
        asserts on logging rather than on database state afterwards.
        """
        reminder = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=dt.datetime(2026, 5, 24, 7, 0),
            offset_minutes=60,
        )
        notify = AsyncMock(side_effect=RuntimeError("push gateway down"))
        service_cls = MagicMock()
        service_cls.return_value.notify = notify
        mock_logger = MagicMock()

        with (
            _patched_session(db_session),
            patch(f"{MODULE}.NotificationService", service_cls),
            patch(f"{MODULE}.logger", mock_logger),
        ):
            await _process_reminder(reminder)

        notify.assert_awaited_once()
        mock_logger.exception.assert_called_once()
        call = mock_logger.exception.call_args
        assert call is not None
        assert "Failed to process reminder" in call.args[0]


# ── _cleanup_cycle ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCleanupCycle:
    """Test suite for the periodic cleanup cycle."""

    async def test_calls_expire_then_cleanup(self, db_session: AsyncSession) -> None:
        """Both maintenance queries run against the same session."""
        crud = MagicMock()
        crud.expire_past_pending = AsyncMock(return_value=0)
        crud.cleanup_old = AsyncMock(return_value=0)

        with _patched_session(db_session), patch(f"{MODULE}.crud_reminder", crud):
            await _cleanup_cycle()

        crud.expire_past_pending.assert_awaited_once_with(db_session)
        crud.cleanup_old.assert_awaited_once_with(db_session, days=30)

    async def test_expires_stale_pending_reminders(
        self,
        db_session: AsyncSession,
        test_booking: Booking,
        test_user: User,
        test_shift: Shift,
    ) -> None:
        """Pending reminders more than an hour overdue are marked expired."""
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        stale = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=now - dt.timedelta(hours=2),
            offset_minutes=15,
        )
        fresh = await _create_reminder(
            db_session,
            booking=test_booking,
            user=test_user,
            shift_id=test_shift.id,
            remind_at=now + dt.timedelta(hours=2),
            offset_minutes=60,
        )
        mock_logger = MagicMock()

        with _patched_session(db_session), patch(f"{MODULE}.logger", mock_logger):
            await _cleanup_cycle()

        await db_session.refresh(stale)
        await db_session.refresh(fresh)
        assert stale.status == "expired"
        assert fresh.status == "pending"

        mock_logger.info.assert_called_once()
        call = mock_logger.info.call_args
        assert call is not None
        assert "expired=1" in call.args[0]

    async def test_stays_quiet_when_there_is_nothing_to_clean(
        self, db_session: AsyncSession
    ) -> None:
        """No expired and no deleted rows means no log line."""
        mock_logger = MagicMock()

        with _patched_session(db_session), patch(f"{MODULE}.logger", mock_logger):
            await _cleanup_cycle()

        mock_logger.info.assert_not_called()

    async def test_swallows_cleanup_errors(self, db_session: AsyncSession) -> None:
        """A failing maintenance query is logged instead of propagating."""
        crud = MagicMock()
        crud.expire_past_pending = AsyncMock(side_effect=RuntimeError("deadlock"))
        crud.cleanup_old = AsyncMock(return_value=0)
        mock_logger = MagicMock()

        with (
            _patched_session(db_session),
            patch(f"{MODULE}.crud_reminder", crud),
            patch(f"{MODULE}.logger", mock_logger),
        ):
            await _cleanup_cycle()

        crud.cleanup_old.assert_not_awaited()
        mock_logger.exception.assert_called_once_with("Failed during reminder cleanup")


# ── run_reminder_poller ───────────────────────────────────────────


@pytest.mark.asyncio
class TestRunReminderPoller:
    """Test suite for the poller's advisory lock and main loop."""

    async def test_skips_when_another_worker_holds_the_lock(self) -> None:
        """A lost advisory-lock race exits before any polling happens."""
        db = _advisory_lock_session(acquired=False)
        mock_logger = MagicMock()
        mock_poll = AsyncMock()

        with (
            _patched_session(db),
            patch(f"{MODULE}.logger", mock_logger),
            patch(f"{MODULE}._poll_cycle", mock_poll),
        ):
            await run_reminder_poller()

        mock_poll.assert_not_awaited()
        # Only the lock probe ran — no unlock, because nothing was acquired.
        assert db.execute.await_count == 1
        mock_logger.info.assert_called_once_with(
            "Another worker holds the reminder poller lock; skipping"
        )

    async def test_polls_and_runs_cleanup_until_cancelled(self) -> None:
        """With the lock held the loop polls, cleans up, and releases on cancel."""
        db = _advisory_lock_session(acquired=True)
        mock_logger = MagicMock()
        mock_poll = AsyncMock(return_value=3)
        mock_cleanup = AsyncMock()
        sleep = AsyncMock(side_effect=asyncio.CancelledError)

        with (
            _patched_session(db),
            patch(f"{MODULE}.logger", mock_logger),
            patch(f"{MODULE}.asyncio", _fake_asyncio(sleep)),
            patch(f"{MODULE}._poll_cycle", mock_poll),
            patch(f"{MODULE}._cleanup_cycle", mock_cleanup),
            patch(f"{MODULE}._CLEANUP_EVERY_N_CYCLES", 1),
        ):
            await run_reminder_poller()

        mock_poll.assert_awaited_once()
        mock_cleanup.assert_awaited_once()
        mock_logger.debug.assert_called_once_with("Processed 3 reminders")
        mock_logger.info.assert_any_call("Reminder poller shutting down")
        mock_logger.info.assert_any_call("Reminder poller advisory lock released")

        assert db.execute.await_count == 2
        unlock_sql = str(db.execute.await_args_list[1].args[0])
        assert "pg_advisory_unlock" in unlock_sql

    async def test_looks_for_unfilled_shifts_on_its_own_turn(self) -> None:
        """Every few cycles the same worker checks for shifts about to start
        with places open, so nothing else has to schedule that."""
        db = _advisory_lock_session(acquired=True)
        mock_check = AsyncMock(return_value=0)
        # Three cycles, and the check's turn comes on the second.
        sleep = AsyncMock(side_effect=[None, None, asyncio.CancelledError])

        with (
            _patched_session(db),
            patch(f"{MODULE}.asyncio", _fake_asyncio(sleep)),
            patch(f"{MODULE}._poll_cycle", AsyncMock(return_value=0)),
            patch(f"{MODULE}.check_upcoming_shifts", mock_check),
            patch(f"{MODULE}._UNFILLED_EVERY_N_CYCLES", 2),
        ):
            await run_reminder_poller()

        mock_check.assert_awaited_once()

    async def test_swallows_unexpected_cycle_errors(self) -> None:
        """A crashing cycle is logged and the loop carries on to the next sleep."""
        db = _advisory_lock_session(acquired=True)
        mock_logger = MagicMock()
        mock_poll = AsyncMock(side_effect=RuntimeError("boom"))
        mock_cleanup = AsyncMock()
        sleep = AsyncMock(side_effect=asyncio.CancelledError)

        with (
            _patched_session(db),
            patch(f"{MODULE}.logger", mock_logger),
            patch(f"{MODULE}.asyncio", _fake_asyncio(sleep)),
            patch(f"{MODULE}._poll_cycle", mock_poll),
            patch(f"{MODULE}._cleanup_cycle", mock_cleanup),
        ):
            await run_reminder_poller()

        mock_logger.exception.assert_called_once_with(
            "Unexpected error in reminder poller cycle"
        )
        mock_cleanup.assert_not_awaited()
        sleep.assert_awaited_once()
        assert db.execute.await_count == 2

    async def test_cancellation_inside_a_cycle_stops_the_loop(self) -> None:
        """CancelledError raised by the cycle is re-raised, not treated as an error."""
        db = _advisory_lock_session(acquired=True)
        mock_logger = MagicMock()
        mock_poll = AsyncMock(side_effect=asyncio.CancelledError)
        sleep = AsyncMock()

        with (
            _patched_session(db),
            patch(f"{MODULE}.logger", mock_logger),
            patch(f"{MODULE}.asyncio", _fake_asyncio(sleep)),
            patch(f"{MODULE}._poll_cycle", mock_poll),
        ):
            await run_reminder_poller()

        sleep.assert_not_awaited()
        mock_logger.exception.assert_not_called()
        mock_logger.info.assert_any_call("Reminder poller shutting down")
        assert db.execute.await_count == 2

    async def test_task_cancellation_releases_the_lock(self) -> None:
        """Cancelling the running task unwinds cleanly and unlocks."""
        db = _advisory_lock_session(acquired=True)
        mock_logger = MagicMock()
        mock_poll = AsyncMock(return_value=0)
        reached_sleep = asyncio.Event()

        async def _sleep(seconds: float) -> None:
            _ = seconds
            reached_sleep.set()
            await asyncio.sleep(3600)

        with (
            _patched_session(db),
            patch(f"{MODULE}.logger", mock_logger),
            patch(f"{MODULE}.asyncio", _fake_asyncio(_sleep)),
            patch(f"{MODULE}._poll_cycle", mock_poll),
        ):
            task = asyncio.create_task(run_reminder_poller())
            await asyncio.wait_for(reached_sleep.wait(), timeout=5)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        mock_poll.assert_awaited_once()
        # processed == 0, so no "Processed N reminders" line.
        mock_logger.debug.assert_not_called()
        mock_logger.info.assert_any_call("Reminder poller shutting down")
        mock_logger.info.assert_any_call("Reminder poller advisory lock released")

        assert db.execute.await_count == 2
        unlock_sql = str(db.execute.await_args_list[1].args[0])
        assert "pg_advisory_unlock" in unlock_sql
