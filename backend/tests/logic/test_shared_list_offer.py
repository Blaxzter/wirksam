"""What a shared list offers, and its status, on the event's clock
(``app.logic.shared_lists.offer``).

The status rules are pure and pinned on in-memory rows; which shifts a list
offers is a query, pinned against the database with one included shift next to
one of every kind that must stay out.
"""

import datetime as dt
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.logic import clock
from app.logic.shared_lists.offer import (
    EffectiveStatus,
    closes_at,
    effective_status,
    expires_soon,
    last_start,
    list_shifts,
    starts_at,
)
from app.models.booking import Booking
from app.models.event import Event
from app.models.event_team import EventTeam
from app.models.shared_list import EndsMode, ListStatus, SharedList
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from tests.fixtures.clock import instant_clock
from tests.fixtures.shared_lists import ListGuestFactory, SharedListFactory

NOW = dt.datetime(2026, 6, 11, 9, 0)


def _list(
    *,
    status: ListStatus = "live",
    ends_mode: EndsMode = "last_shift",
    ends_on: dt.date | None = None,
) -> SharedList:
    return SharedList(
        event_id=uuid.uuid4(),
        code="abcdefghjkmn",
        title="Helfer gesucht",
        status=status,
        ends_mode=ends_mode,
        ends_on=ends_on,
    )


def _event(*, status: str = "published", timezone: str = "Europe/Berlin") -> Event:
    return Event(
        name="Sommerfest",
        start_date=dt.date(2026, 6, 10),
        end_date=dt.date(2026, 6, 14),
        status=status,
        timezone=timezone,
    )


async def _shift(
    db: AsyncSession,
    task: Task,
    date: dt.date,
    start: dt.time | None,
    *,
    max_bookings: int = 2,
) -> Shift:
    shift = Shift(
        task_id=task.id,
        title=task.name,
        date=date,
        start_time=start,
        end_time=None,
        max_bookings=max_bookings,
    )
    db.add(shift)
    await db.flush()
    return shift


async def _task(
    db: AsyncSession,
    event: Event,
    creator: User,
    name: str,
    *,
    status: str = "published",
    team_id: uuid.UUID | None = None,
) -> Task:
    task = Task(
        name=name,
        start_date=dt.date(2026, 6, 11),
        end_date=dt.date(2026, 6, 13),
        status=status,
        created_by_id=creator.id,
        event_id=event.id,
        team_id=team_id,
    )
    db.add(task)
    await db.flush()
    return task


class TestStartsAt:
    def test_an_untimed_shift_starts_at_midnight(self) -> None:
        assert starts_at(dt.date(2026, 6, 11), None) == dt.datetime(2026, 6, 11, 0, 0)

    def test_a_timed_shift_starts_at_its_start(self) -> None:
        assert starts_at(dt.date(2026, 6, 11), dt.time(18, 30)) == dt.datetime(
            2026, 6, 11, 18, 30
        )


class TestEffectiveStatus:
    def _status(
        self,
        shared_list: SharedList,
        *,
        event: Event | None = None,
        last: dt.datetime | None = dt.datetime(2026, 6, 12, 10, 0),
        now: dt.datetime = NOW,
    ) -> EffectiveStatus:
        return effective_status(
            shared_list, event=event or _event(), last_start=last, now_wall=now
        )

    def test_ended_stays_ended_even_on_an_unpublished_event(self) -> None:
        assert self._status(_list(status="ended"), event=_event(status="draft")) == (
            "ended"
        )

    def test_paused_stays_paused_even_with_nothing_left(self) -> None:
        assert self._status(_list(status="paused"), last=None) == "paused"

    @pytest.mark.parametrize("status", ["draft", "archived"])
    def test_a_live_list_of_an_unpublished_event_is_expired(self, status: str) -> None:
        assert self._status(_list(), event=_event(status=status)) == "expired"

    def test_last_shift_is_live_until_the_last_shift_starts(self) -> None:
        assert self._status(_list(), last=NOW + dt.timedelta(minutes=1)) == "live"
        assert self._status(_list(), last=NOW) == "expired"

    def test_last_shift_without_shifts_is_expired(self) -> None:
        assert self._status(_list(), last=None) == "expired"

    def test_manual_without_shifts_is_live(self) -> None:
        assert self._status(_list(ends_mode="manual"), last=None) == "live"

    def test_a_date_list_is_open_through_its_day(self) -> None:
        on_the_day = _list(ends_mode="date", ends_on=NOW.date())
        the_day_before = _list(
            ends_mode="date", ends_on=NOW.date() - dt.timedelta(days=1)
        )
        assert self._status(on_the_day, now=NOW.replace(hour=23, minute=59)) == "live"
        assert self._status(the_day_before) == "expired"

    def test_a_date_list_ignores_whether_shifts_are_left(self) -> None:
        """Started shifts vanish from it anyway; the day is what closes it."""
        assert self._status(_list(ends_mode="date", ends_on=NOW.date()), last=None) == (
            "live"
        )

    def test_the_closing_day_is_the_events_day(self) -> None:
        """03:00 UTC on the 13th is still the 12th in New York, and already the
        13th in Berlin: the same list is open in one event and closed in the
        other, because "now" is read on each event's own clock."""
        shared_list = _list(ends_mode="date", ends_on=dt.date(2026, 6, 12))
        wall_clock_now = instant_clock(dt.datetime(2026, 6, 13, 3, 0))
        for zone, expected in (
            ("America/New_York", "live"),
            ("Europe/Berlin", "expired"),
        ):
            event = _event(timezone=zone)
            now_wall = wall_clock_now(event.timezone)
            assert self._status(shared_list, event=event, now=now_wall) == expected


class TestClosesAt:
    def test_with_the_last_shift(self) -> None:
        last = dt.datetime(2026, 6, 12, 10, 0)
        assert closes_at(_list(), last_start=last) == last
        assert closes_at(_list(), last_start=None) is None

    def test_on_a_day_at_its_end(self) -> None:
        shared_list = _list(ends_mode="date", ends_on=dt.date(2026, 6, 12))
        closes = closes_at(shared_list, last_start=None)
        assert closes is not None
        assert closes.date() == dt.date(2026, 6, 12)
        assert closes > dt.datetime(2026, 6, 12, 23, 59, 59)

    def test_by_hand_never(self) -> None:
        assert closes_at(_list(ends_mode="manual"), last_start=NOW) is None


class TestExpiresSoon:
    @pytest.mark.parametrize(("days", "expected"), [(0, True), (3, True), (4, False)])
    def test_a_live_date_list_within_three_days(
        self, days: int, expected: bool
    ) -> None:
        shared_list = _list(
            ends_mode="date", ends_on=NOW.date() + dt.timedelta(days=days)
        )
        assert expires_soon(shared_list, effective="live", now_wall=NOW) is expected

    def test_not_when_paused(self) -> None:
        shared_list = _list(status="paused", ends_mode="date", ends_on=NOW.date())
        assert not expires_soon(shared_list, effective="paused", now_wall=NOW)

    def test_not_when_closing_with_the_last_shift(self) -> None:
        assert not expires_soon(_list(), effective="live", now_wall=NOW)


@pytest.mark.asyncio
class TestListShifts:
    async def test_offers_only_included_shifts_that_have_not_started(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_draft_event: Event,
        test_task: Task,
        test_user: User,
        make_shared_list: SharedListFactory,
    ) -> None:
        offered = await _shift(db_session, test_task, dt.date(2026, 6, 11), dt.time(10))
        started = await _shift(db_session, test_task, dt.date(2026, 6, 11), dt.time(8))
        untimed_today = await _shift(db_session, test_task, dt.date(2026, 6, 11), None)
        excluded = await _shift(db_session, test_task, dt.date(2026, 6, 12), None)

        team = EventTeam(event_id=test_event.id, name="Kasse")
        db_session.add(team)
        await db_session.flush()
        team_task = await _task(
            db_session, test_event, test_user, "Kasse", team_id=team.id
        )
        draft_task = await _task(
            db_session, test_event, test_user, "Aufbau", status="draft"
        )
        moved_task = await _task(db_session, test_draft_event, test_user, "Umgezogen")
        for task in (team_task, draft_task, moved_task):
            await _shift(db_session, task, dt.date(2026, 6, 12), dt.time(10))

        shared_list = await make_shared_list(
            tasks=[test_task, team_task, draft_task, moved_task], excluded=[excluded]
        )

        shifts = await list_shifts(db_session, shared_list, now_wall=NOW)
        assert [o.shift.id for o in shifts] == [offered.id]

        with_started = await list_shifts(
            db_session, shared_list, now_wall=NOW, include_started=True
        )
        assert {o.shift.id for o in with_started} == {
            offered.id,
            started.id,
            untimed_today.id,
        }

    async def test_ordered_by_day_start_untimed_first_then_task(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_user: User,
        make_shared_list: SharedListFactory,
    ) -> None:
        bar = await _task(db_session, test_event, test_user, "Bar")
        day2 = dt.date(2026, 6, 12)
        late = await _shift(db_session, test_task, day2, dt.time(18))
        untimed = await _shift(db_session, test_task, day2, None)
        early_task_b = await _shift(db_session, test_task, day2, dt.time(10))
        early_task_a = await _shift(db_session, bar, day2, dt.time(10))
        first_day = await _shift(db_session, bar, dt.date(2026, 6, 11), dt.time(20))
        shared_list = await make_shared_list(tasks=[test_task, bar])

        shifts = await list_shifts(db_session, shared_list, now_wall=NOW)

        assert [o.shift.id for o in shifts] == [
            first_day.id,
            untimed.id,
            early_task_a.id,
            early_task_b.id,
            late.id,
        ]
        assert shifts[0].task.id == bar.id
        assert shifts[0].starts_at == dt.datetime(2026, 6, 11, 20, 0)

    async def test_counts_confirmed_bookings_and_clamps_free(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
        test_event_admin_user: User,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """``max_bookings`` lowered below the bookings a shift has: no place is
        free, never a negative number. Cancelled bookings hold no place."""
        shift = await _shift(
            db_session, test_task, dt.date(2026, 6, 12), dt.time(10), max_bookings=3
        )
        await make_list_guest(test_shared_list, shifts=[shift])
        db_session.add_all(
            [
                Booking(shift_id=shift.id, user_id=test_user.id, status="confirmed"),
                Booking(
                    shift_id=shift.id,
                    user_id=test_event_admin_user.id,
                    status="cancelled",
                ),
            ]
        )
        await db_session.flush()

        [offered] = await list_shifts(db_session, test_shared_list, now_wall=NOW)
        assert (offered.confirmed, offered.free) == (2, 1)

        shift.max_bookings = 1
        await db_session.flush()
        [offered] = await list_shifts(db_session, test_shared_list, now_wall=NOW)
        assert (offered.confirmed, offered.free) == (2, 0)


@pytest.mark.asyncio
class TestLastStart:
    async def test_the_latest_included_start_started_or_not(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
        test_event: Event,
        make_shared_list: SharedListFactory,
    ) -> None:
        await _shift(db_session, test_task, dt.date(2026, 6, 10), dt.time(10))
        latest = await _shift(db_session, test_task, dt.date(2026, 6, 12), None)
        excluded = await _shift(db_session, test_task, dt.date(2026, 6, 13), None)
        draft = await _task(db_session, test_event, test_user, "Abbau", status="draft")
        await _shift(db_session, draft, dt.date(2026, 6, 14), dt.time(9))
        shared_list = await make_shared_list(
            tasks=[test_task, draft], excluded=[excluded]
        )

        assert await last_start(db_session, shared_list) == starts_at(
            latest.date, latest.start_time
        )

    async def test_none_without_shifts(
        self, db_session: AsyncSession, test_shared_list: SharedList
    ) -> None:
        assert await last_start(db_session, test_shared_list) is None

    async def test_feeds_the_status_on_the_events_clock(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        test_event: Event,
        test_task: Task,
        test_shared_list: SharedList,
    ) -> None:
        """The way callers combine the two: the last shift starts at 10:00
        Berlin, 08:00 UTC, so at 08:30 UTC the list has expired."""
        await _shift(db_session, test_task, dt.date(2026, 6, 12), dt.time(10))
        last = await last_start(db_session, test_shared_list)

        statuses: list[EffectiveStatus] = []
        for utc in (dt.datetime(2026, 6, 12, 7, 30), dt.datetime(2026, 6, 12, 8, 30)):
            monkeypatch.setattr("app.logic.clock.wall_clock_now", instant_clock(utc))
            statuses.append(
                effective_status(
                    test_shared_list,
                    event=test_event,
                    last_start=last,
                    now_wall=clock.wall_clock_now(test_event.timezone),
                )
            )
        assert statuses == ["live", "expired"]
