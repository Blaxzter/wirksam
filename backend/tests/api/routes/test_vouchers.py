"""Volunteer vouchers over HTTP: codes, redeeming, accounts and corrections.

The cast, all in ``test_event`` (2026-06-10 to 14):

- ``admin``: ``test_event_admin_user``, an event admin;
- ``volunteer``: ``test_user``, a member who earned 3 vouchers on a shift
  that ended at noon on 11 June;
- ``manager``: a member in charge of the point ``Theke``;
- ``staff``: a member on a 14:00-18:00 shift at ``Theke`` that day;
- ``second_staff``: a member on the same hours at ``Ausgabe``, a second point
  with nobody in charge and no team;
- ``bystander``: a member with no shift and no role.

The event keeps the default voucher rule (``voucher_manual_redeem`` is
``on_shift``) unless a test switches it to ``in_charge``.

The event wall clock is pinned to 11 June, 15:00 unless a test moves it, so
the volunteer's shift is over and the staff shifts are running. Stored
timestamps (code expiry) run on the real UTC clock.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.booking import booking as crud_booking
from app.crud.voucher import voucher as crud_voucher
from app.logic import vouchers
from app.logic.clock import utc_now
from app.models.booking import Booking
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shift import Shift
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from app.models.voucher import VoucherEntry, VoucherPass
from tests.fixtures.client import act_as
from tests.fixtures.clock import fixed_clock
from tests.fixtures.sandbox import SandboxSetup

DAY = dt.date(2026, 6, 11)
NOW = dt.datetime(2026, 6, 11, 15, 0)


@dataclass
class Cast:
    event: Event
    other_event: Event
    admin: User
    volunteer: User
    manager: User
    staff: User
    second_staff: User
    bystander: User
    outsider: User
    work: Task
    point: Task
    second_point: Task
    plain: Task
    other_point: Task
    staff_shift: Shift


async def _user(db: AsyncSession, key: str) -> User:
    user = User(
        subject=f"local|voucher-{key}",
        email=f"{key}.vouchers@example.com",
        name=key.replace("_", " ").title(),
        roles=[],
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _member(db: AsyncSession, user: User, event: Event) -> None:
    db.add(EventMembership(user_id=user.id, event_id=event.id, role="member"))
    await db.flush()


async def _task(db: AsyncSession, event: Event, creator: User, **cols: Any) -> Task:
    task = Task(
        name=cols.pop("name"),
        start_date=DAY,
        end_date=DAY + dt.timedelta(days=2),
        status=cols.pop("status", "published"),
        created_by_id=creator.id,
        event_id=event.id,
        **cols,
    )
    db.add(task)
    await db.flush()
    return task


async def _shift_for(
    db: AsyncSession,
    task: Task,
    user: User | None,
    *,
    date: dt.date = DAY,
    start: dt.time | None,
    end: dt.time | None,
) -> Shift:
    shift = Shift(
        task_id=task.id,
        title=f"{task.name} {uuid.uuid4().hex[:4]}",
        date=date,
        start_time=start,
        end_time=end,
        max_bookings=4,
    )
    db.add(shift)
    await db.flush()
    if user is not None:
        db.add(Booking(shift_id=shift.id, user_id=user.id, status="confirmed"))
        await db.flush()
    return shift


@pytest_asyncio.fixture
async def cast(
    db_session: AsyncSession,
    test_event: Event,
    test_draft_event: Event,
    test_event_admin_user: User,
    test_user: User,
    test_outsider_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> Cast:
    monkeypatch.setattr("app.logic.clock.wall_clock_now", fixed_clock(NOW))
    manager = await _user(db_session, "manager")
    staff = await _user(db_session, "staff")
    second_staff = await _user(db_session, "second_staff")
    bystander = await _user(db_session, "bystander")
    for user in (manager, staff, second_staff, bystander):
        await _member(db_session, user, test_event)

    work = await _task(
        db_session, test_event, test_user, name="Aufbau", vouchers_per_shift=3
    )
    point = await _task(
        db_session, test_event, test_user, name="Theke", is_voucher_point=True
    )
    second_point = await _task(
        db_session, test_event, test_user, name="Ausgabe", is_voucher_point=True
    )
    plain = await _task(db_session, test_event, test_user, name="Garderobe")
    other_point = await _task(
        db_session, test_draft_event, test_user, name="Kasse", is_voucher_point=True
    )
    db_session.add(TaskManager(task_id=point.id, user_id=manager.id))
    await db_session.flush()

    await _shift_for(db_session, work, test_user, start=dt.time(8), end=dt.time(12))
    staff_shift = await _shift_for(
        db_session, point, staff, start=dt.time(14), end=dt.time(18)
    )
    await _shift_for(
        db_session, second_point, second_staff, start=dt.time(14), end=dt.time(18)
    )
    return Cast(
        event=test_event,
        other_event=test_draft_event,
        admin=test_event_admin_user,
        volunteer=test_user,
        manager=manager,
        staff=staff,
        second_staff=second_staff,
        bystander=bystander,
        outsider=test_outsider_user,
        work=work,
        point=point,
        second_point=second_point,
        plain=plain,
        other_point=other_point,
        staff_shift=staff_shift,
    )


async def _manual_rule(db: AsyncSession, cast: Cast, rule: str) -> None:
    """Set the event's ``voucher_manual_redeem``."""
    cast.event.voucher_manual_redeem = rule
    db.add(cast.event)
    await db.flush()


def _base(event: Event) -> str:
    return f"/api/v1/events/{event.id}/vouchers"


async def _issue(
    client: AsyncClient, app: FastAPI, cast: Cast, user: User | None = None
) -> dict[str, Any]:
    with act_as(app, user or cast.volunteer):
        r = await client.post(f"{_base(cast.event)}/me/pass")
    assert r.status_code == 201, r.text
    return r.json()


async def _check(
    client: AsyncClient,
    app: FastAPI,
    cast: Cast,
    as_user: User,
    *,
    task: Task | None = None,
    event: Event | None = None,
    **body: Any,
) -> Response:
    with act_as(app, as_user):
        return await client.post(
            f"{_base(event or cast.event)}/check",
            json={"task_id": str((task or cast.point).id), **body},
        )


async def _redeem(
    client: AsyncClient,
    app: FastAPI,
    cast: Cast,
    as_user: User,
    *,
    amount: int = 1,
    task: Task | None = None,
    event: Event | None = None,
    request_id: uuid.UUID | None = None,
    **body: Any,
) -> Response:
    with act_as(app, as_user):
        return await client.post(
            f"{_base(event or cast.event)}/redeem",
            json={
                "task_id": str((task or cast.point).id),
                "amount": amount,
                "request_id": str(request_id or uuid.uuid4()),
                **body,
            },
        )


async def _pass_row(db: AsyncSession, pass_id: str) -> VoucherPass:
    p = await crud_voucher.reload_pass(db, pass_id=uuid.UUID(pass_id))
    assert p is not None
    return p


async def _entries(db: AsyncSession, cast: Cast) -> list[VoucherEntry]:
    rows = await db.execute(
        select(VoucherEntry)
        .where(col(VoucherEntry.event_id) == cast.event.id)
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars())


def _code(r: Response) -> str:
    return r.json().get("code")


# ── Showing a code ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPass:
    async def test_a_member_gets_a_short_code(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        body = await _issue(async_client, app, cast)

        assert len(body["code"]) == 6
        assert all(c in vouchers.CODE_ALPHABET for c in body["code"])
        assert body["qr_payload"] == f"WV1:{body['code']}"
        assert body["ttl_seconds"] == 120
        assert body["event_name"] == cast.event.name

    async def test_not_for_someone_outside_the_event(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        with act_as(app, cast.outsider):
            r = await async_client.post(f"{_base(cast.event)}/me/pass")
        assert r.status_code == 403
        assert _code(r) == "event.forbidden"

    async def test_a_new_code_replaces_the_unused_one(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        old = await _issue(async_client, app, cast)
        await _issue(async_client, app, cast)

        r = await _check(async_client, app, cast, cast.admin, code=old["code"])
        assert r.status_code == 404
        assert _code(r) == "voucher.code_invalid"
        with act_as(app, cast.volunteer):
            r = await async_client.get(f"{_base(cast.event)}/me/pass/{old['id']}")
        assert r.status_code == 404
        assert _code(r) == "voucher.pass_not_found"

    async def test_a_new_code_keeps_a_used_one_and_a_held_one(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        used = await _issue(async_client, app, cast)
        assert (
            await _redeem(async_client, app, cast, cast.admin, code=used["code"])
        ).status_code == 201
        held = await _issue(async_client, app, cast)
        assert (
            await _check(async_client, app, cast, cast.admin, code=held["code"])
        ).status_code == 200

        await _issue(async_client, app, cast)

        with act_as(app, cast.volunteer):
            used_status = await async_client.get(
                f"{_base(cast.event)}/me/pass/{used['id']}"
            )
            held_status = await async_client.get(
                f"{_base(cast.event)}/me/pass/{held['id']}"
            )
        assert used_status.json()["status"] == "used"
        assert held_status.json()["status"] == "checking"
        # And the held one still redeems.
        r = await _redeem(async_client, app, cast, cast.admin, code=held["code"])
        assert r.status_code == 201

    async def test_status_follows_the_code(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        issued = await _issue(async_client, app, cast)
        url = f"{_base(cast.event)}/me/pass/{issued['id']}"

        async def status() -> dict[str, Any]:
            with act_as(app, cast.volunteer):
                r = await async_client.get(url)
            assert r.status_code == 200
            return r.json()

        assert (await status())["status"] == "active"
        assert (await status())["available"] == 3

        await _check(async_client, app, cast, cast.staff, code=issued["code"])
        assert (await status())["status"] == "checking"

        await _redeem(
            async_client, app, cast, cast.staff, code=issued["code"], amount=2
        )
        done = await status()
        assert done == {
            "status": "used",
            "redeemed_amount": 2,
            "task_name": "Theke",
            "available": 1,
        }

        fresh = await _issue(async_client, app, cast)
        p = await _pass_row(db_session, fresh["id"])
        p.expires_at = utc_now() - dt.timedelta(seconds=1)
        db_session.add(p)
        await db_session.flush()
        with act_as(app, cast.volunteer):
            r = await async_client.get(f"{_base(cast.event)}/me/pass/{fresh['id']}")
        assert r.json()["status"] == "expired"

    async def test_nobody_reads_someone_elses_code(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        issued = await _issue(async_client, app, cast)
        with act_as(app, cast.bystander):
            r = await async_client.get(f"{_base(cast.event)}/me/pass/{issued['id']}")
        assert r.status_code == 404
        assert _code(r) == "voucher.pass_not_found"


@pytest.mark.asyncio
class TestHold:
    """A checked code survives its own expiry for a minute, so a slow network
    between check and redeem never loses it."""

    async def _checked_then_expired(
        self,
        client: AsyncClient,
        app: FastAPI,
        db: AsyncSession,
        cast: Cast,
        *,
        checked_ago: int,
    ) -> str:
        issued = await _issue(client, app, cast)
        assert (
            await _check(client, app, cast, cast.admin, code=issued["code"])
        ).status_code == 200
        p = await _pass_row(db, issued["id"])
        p.expires_at = utc_now() - dt.timedelta(seconds=5)
        p.checked_at = utc_now() - dt.timedelta(seconds=checked_ago)
        db.add(p)
        await db.flush()
        return issued["code"]

    async def test_within_the_hold_it_still_redeems(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        code = await self._checked_then_expired(
            async_client, app, db_session, cast, checked_ago=50
        )
        r = await _redeem(async_client, app, cast, cast.admin, code=code)
        assert r.status_code == 201

    async def test_after_the_hold_it_has_expired(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        code = await self._checked_then_expired(
            async_client, app, db_session, cast, checked_ago=61
        )
        r = await _redeem(async_client, app, cast, cast.admin, code=code)
        assert r.status_code == 409
        assert _code(r) == "voucher.code_expired"

    async def test_an_expired_code_cannot_be_held_again(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        code = await self._checked_then_expired(
            async_client, app, db_session, cast, checked_ago=61
        )
        r = await _check(async_client, app, cast, cast.admin, code=code)
        assert r.status_code == 409
        assert _code(r) == "voucher.code_expired"

    async def test_checking_again_does_not_keep_an_expired_code_alive(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        """Re-checking inside the hold answers, but the hold runs from the
        last check *before* expiry, so a code is dead a minute after its two
        minutes at the latest, however often a redeemer checks it."""
        code = await self._checked_then_expired(
            async_client, app, db_session, cast, checked_ago=50
        )
        issued_id = (
            await db_session.execute(
                select(col(VoucherPass.id)).where(col(VoucherPass.code) == code)
            )
        ).scalar_one()
        held_since = (await _pass_row(db_session, str(issued_id))).checked_at

        r = await _check(async_client, app, cast, cast.admin, code=code)
        assert r.status_code == 200
        assert (await _pass_row(db_session, str(issued_id))).checked_at == held_since

        # Ten more seconds pass: the hold from before the expiry is over.
        p = await _pass_row(db_session, str(issued_id))
        p.checked_at = utc_now() - dt.timedelta(seconds=61)
        db_session.add(p)
        await db_session.flush()
        r = await _redeem(async_client, app, cast, cast.admin, code=code)
        assert r.status_code == 409
        assert _code(r) == "voucher.code_expired"

    async def test_checking_again_before_expiry_renews_the_hold(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        issued = await _issue(async_client, app, cast)
        await _check(async_client, app, cast, cast.admin, code=issued["code"])
        p = await _pass_row(db_session, issued["id"])
        p.checked_at = utc_now() - dt.timedelta(seconds=50)
        db_session.add(p)
        await db_session.flush()

        r = await _check(async_client, app, cast, cast.admin, code=issued["code"])
        assert r.status_code == 200
        checked_at = (await _pass_row(db_session, issued["id"])).checked_at
        assert checked_at is not None
        assert checked_at > utc_now() - dt.timedelta(seconds=10)


@pytest.mark.asyncio
class TestRotationRace:
    async def test_a_replaced_code_is_invalid(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        old = await _issue(async_client, app, cast)
        await _issue(async_client, app, cast)
        r = await _redeem(async_client, app, cast, cast.admin, code=old["code"])
        assert r.status_code == 404
        assert _code(r) == "voucher.code_invalid"

    async def test_replaced_between_lookup_and_lock_is_invalid_not_a_500(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The volunteer's screen issues a new code while a stand is redeeming
        the old one: found before the lock, gone after it."""
        old = await _issue(async_client, app, cast)
        real_lock = crud_voucher.lock_ledger

        async def lock_then_rotate(session: AsyncSession, **kw: Any) -> None:
            await real_lock(session, **kw)
            await vouchers.issue_pass(
                session,
                event_id=cast.event.id,
                user_id=cast.volunteer.id,
                now=utc_now(),
            )

        monkeypatch.setattr(crud_voucher, "lock_ledger", lock_then_rotate)
        r = await _redeem(async_client, app, cast, cast.admin, code=old["code"])
        assert r.status_code == 404
        assert _code(r) == "voucher.code_invalid"
        assert await _entries(db_session, cast) == []


# ── Redeeming ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRedeemByCode:
    @pytest.mark.parametrize("who", ["admin", "manager", "staff"])
    async def test_who_may_take_a_code(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
        who: str,
    ) -> None:
        redeemer: User = getattr(cast, who)
        issued = await _issue(async_client, app, cast)
        r = await _redeem(
            async_client, app, cast, redeemer, code=issued["code"], amount=2
        )

        assert r.status_code == 201, r.text
        body = r.json()
        assert body["available"] == 1
        assert body["replayed"] is False
        assert body["user_id"] == str(cast.volunteer.id)
        assert body["entry"]["amount"] == -2
        assert body["entry"]["method"] == "code"
        assert body["entry"]["task_name"] == "Theke"
        assert body["entry"]["actor_name"] == redeemer.name
        (entry,) = await _entries(db_session, cast)
        assert entry.pass_id == uuid.UUID(issued["id"])
        assert entry.actor_id == redeemer.id

    @pytest.mark.parametrize(
        ("now", "allowed"),
        [
            (dt.datetime(2026, 6, 11, 13, 31), True),  # 29 min before 14:00
            (dt.datetime(2026, 6, 11, 13, 29), False),  # 31 min before
            (dt.datetime(2026, 6, 11, 18, 29), True),  # 29 min after 18:00
            (dt.datetime(2026, 6, 11, 18, 31), False),  # 31 min after
        ],
    )
    async def test_on_shift_means_thirty_minutes_either_side(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        cast: Cast,
        wall_clock: Callable[[dt.datetime], None],
        now: dt.datetime,
        allowed: bool,
    ) -> None:
        wall_clock(now)
        issued = await _issue(async_client, app, cast)
        r = await _check(async_client, app, cast, cast.staff, code=issued["code"])
        if allowed:
            assert r.status_code == 200, r.text
        else:
            assert r.status_code == 403
            assert _code(r) == "voucher.not_allowed"

    async def test_an_untimed_shift_today_counts(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        await _shift_for(db_session, cast.point, cast.bystander, start=None, end=None)
        issued = await _issue(async_client, app, cast)
        r = await _check(async_client, app, cast, cast.bystander, code=issued["code"])
        assert r.status_code == 200

    async def test_a_member_not_on_shift_may_not(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        issued = await _issue(async_client, app, cast)
        r = await _redeem(async_client, app, cast, cast.bystander, code=issued["code"])
        assert r.status_code == 403
        assert _code(r) == "voucher.not_allowed"

    async def test_on_shift_at_another_task_is_not_on_shift_here(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        issued = await _issue(async_client, app, cast)
        r = await _redeem(
            async_client, app, cast, cast.second_staff, code=issued["code"]
        )
        assert r.status_code == 403
        assert _code(r) == "voucher.not_allowed"

    async def test_only_at_a_point(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        issued = await _issue(async_client, app, cast)
        r = await _redeem(
            async_client, app, cast, cast.admin, code=issued["code"], task=cast.plain
        )
        assert r.status_code == 422
        assert _code(r) == "voucher.not_a_point"

    async def test_another_events_task_is_not_found(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        issued = await _issue(async_client, app, cast)
        r = await _redeem(
            async_client,
            app,
            cast,
            cast.admin,
            code=issued["code"],
            task=cast.other_point,
        )
        assert r.status_code == 404
        assert _code(r) == "task.not_found"

    async def test_a_code_from_another_event_says_so(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        """The volunteer is in two events and showed the wrong one's code."""
        with act_as(app, cast.volunteer):
            r = await async_client.post(f"{_base(cast.other_event)}/me/pass")
        assert r.status_code == 201
        r = await _redeem(async_client, app, cast, cast.admin, code=r.json()["code"])
        assert r.status_code == 409
        assert _code(r) == "voucher.code_other_event"

    async def test_too_many_is_refused_and_the_code_still_works(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        issued = await _issue(async_client, app, cast)
        r = await _redeem(
            async_client, app, cast, cast.admin, code=issued["code"], amount=4
        )
        assert r.status_code == 409
        assert _code(r) == "voucher.insufficient"
        assert r.json()["available"] == 3
        # Nothing was written, so the same code redeems a smaller amount.
        assert (await _pass_row(db_session, issued["id"])).used_at is None
        r = await _redeem(
            async_client, app, cast, cast.admin, code=issued["code"], amount=3
        )
        assert r.status_code == 201
        assert r.json()["available"] == 0

    async def test_a_used_code_says_where_and_by_whom(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        issued = await _issue(async_client, app, cast)
        await _redeem(
            async_client, app, cast, cast.staff, code=issued["code"], amount=2
        )

        for attempt in (
            _redeem(async_client, app, cast, cast.admin, code=issued["code"]),
            _check(async_client, app, cast, cast.admin, code=issued["code"]),
        ):
            r = await attempt
            assert r.status_code == 409
            body = r.json()
            assert body["code"] == "voucher.code_used"
            assert body["amount"] == 2
            assert body["task_name"] == "Theke"
            assert body["actor_name"] == cast.staff.name
            assert body["used_at"]

    async def test_an_expired_code(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        issued = await _issue(async_client, app, cast)
        p = await _pass_row(db_session, issued["id"])
        p.expires_at = utc_now() - dt.timedelta(seconds=1)
        db_session.add(p)
        await db_session.flush()
        r = await _redeem(async_client, app, cast, cast.admin, code=issued["code"])
        assert r.status_code == 409
        assert _code(r) == "voucher.code_expired"

    @pytest.mark.parametrize("garbage", ["nonsense", "AAAAAA", "WV1:123"])
    async def test_garbage_is_an_invalid_code(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast, garbage: str
    ) -> None:
        r = await _redeem(async_client, app, cast, cast.admin, code=garbage)
        assert r.status_code == 404
        assert _code(r) == "voucher.code_invalid"

    async def test_the_code_is_read_like_a_human_types_it(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        issued = await _issue(async_client, app, cast)
        typed = f"{issued['code'][:3].lower()}-{issued['code'][3:].lower()}"
        r = await _redeem(async_client, app, cast, cast.admin, code=typed)
        assert r.status_code == 201

    async def test_exactly_one_of_code_and_person(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        r = await _redeem(async_client, app, cast, cast.admin)
        assert r.status_code == 422
        r = await _redeem(
            async_client,
            app,
            cast,
            cast.admin,
            code="K7M4QX",
            user_id=str(cast.volunteer.id),
        )
        assert r.status_code == 422

    async def test_check_takes_nothing(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        issued = await _issue(async_client, app, cast)
        r = await _check(async_client, app, cast, cast.staff, code=issued["code"])

        assert r.status_code == 200
        assert r.json() == {
            "user_id": str(cast.volunteer.id),
            "name": cast.volunteer.name,
            "avatar_etag": cast.volunteer.avatar_etag,
            "available": 3,
        }
        assert await _entries(db_session, cast) == []
        p = await _pass_row(db_session, issued["id"])
        assert p.used_at is None
        assert p.checked_at is not None


@pytest.mark.asyncio
class TestRetry:
    async def test_the_same_request_twice_debits_once(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        request_id = uuid.uuid4()
        first = await _redeem(
            async_client,
            app,
            cast,
            cast.admin,
            user_id=str(cast.volunteer.id),
            request_id=request_id,
        )
        again = await _redeem(
            async_client,
            app,
            cast,
            cast.admin,
            user_id=str(cast.volunteer.id),
            request_id=request_id,
        )

        assert first.status_code == 201
        assert again.status_code == 201
        assert again.json()["replayed"] is True
        assert again.json()["entry"]["id"] == first.json()["entry"]["id"]
        assert again.json()["available"] == 2
        assert len(await _entries(db_session, cast)) == 1

    async def test_a_code_redemption_retried_after_it_went_through(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        issued = await _issue(async_client, app, cast)
        request_id = uuid.uuid4()
        first = await _redeem(
            async_client,
            app,
            cast,
            cast.staff,
            code=issued["code"],
            request_id=request_id,
        )
        again = await _redeem(
            async_client,
            app,
            cast,
            cast.staff,
            code=issued["code"],
            request_id=request_id,
        )
        assert first.status_code == 201
        assert again.status_code == 201
        assert again.json()["replayed"] is True

    async def test_someone_elses_request_id_is_a_conflict(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        request_id = uuid.uuid4()
        await _redeem(
            async_client,
            app,
            cast,
            cast.admin,
            user_id=str(cast.volunteer.id),
            request_id=request_id,
        )
        r = await _redeem(
            async_client,
            app,
            cast,
            cast.manager,
            user_id=str(cast.volunteer.id),
            request_id=request_id,
        )
        assert r.status_code == 409
        assert _code(r) == "voucher.request_conflict"


@pytest.mark.asyncio
class TestRedeemManually:
    @pytest.mark.parametrize("rule", ["on_shift", "in_charge"])
    @pytest.mark.parametrize("who", ["admin", "manager"])
    async def test_admins_and_people_in_charge_may_pick_the_person(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
        who: str,
        rule: str,
    ) -> None:
        await _manual_rule(db_session, cast, rule)
        r = await _redeem(
            async_client,
            app,
            cast,
            getattr(cast, who),
            user_id=str(cast.volunteer.id),
        )
        assert r.status_code == 201
        assert r.json()["entry"]["method"] == "manual"

    @pytest.mark.parametrize("who", ["staff", "second_staff"])
    async def test_by_default_staff_on_shift_may_pick_at_their_point(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
        who: str,
    ) -> None:
        """No team needed: being on a running shift at the point is enough."""
        redeemer: User = getattr(cast, who)
        point = cast.point if who == "staff" else cast.second_point
        r = await _check(
            async_client,
            app,
            cast,
            redeemer,
            task=point,
            user_id=str(cast.volunteer.id),
        )
        assert r.status_code == 200, r.text
        assert r.json()["available"] == 3
        r = await _redeem(
            async_client,
            app,
            cast,
            redeemer,
            task=point,
            user_id=str(cast.volunteer.id),
        )
        assert r.status_code == 201, r.text
        # Traceable: the point's entries say who picked whom.
        assert r.json()["entry"]["method"] == "manual"
        assert r.json()["entry"]["actor_name"] == redeemer.name
        (entry,) = await _entries(db_session, cast)
        assert entry.actor_id == redeemer.id
        assert entry.task_id == point.id

    async def test_with_in_charge_staff_on_shift_need_the_code(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        await _manual_rule(db_session, cast, "in_charge")
        for call in (_redeem, _check):
            r = await call(
                async_client, app, cast, cast.staff, user_id=str(cast.volunteer.id)
            )
            assert r.status_code == 403
            assert _code(r) == "voucher.manual_not_allowed"
        # With the code it still works.
        issued = await _issue(async_client, app, cast)
        r = await _redeem(async_client, app, cast, cast.staff, code=issued["code"])
        assert r.status_code == 201

    @pytest.mark.parametrize("rule", ["on_shift", "in_charge"])
    @pytest.mark.parametrize("who", ["bystander", "second_staff"])
    async def test_not_on_shift_here_is_not_allowed_either_way(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
        who: str,
        rule: str,
    ) -> None:
        await _manual_rule(db_session, cast, rule)
        r = await _redeem(
            async_client, app, cast, getattr(cast, who), user_id=str(cast.volunteer.id)
        )
        assert r.status_code == 403
        assert _code(r) == "voucher.not_allowed"

    async def test_booking_yourself_onto_an_open_point_is_on_shift_there(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        """The door ``on_shift`` opens, which the event settings warn about: a
        member books a running shift at a point anyone may book and may pick
        people at once. Every such redemption names who made it, and
        ``in_charge`` closes the door again."""
        open_shift = await _shift_for(
            db_session, cast.second_point, None, start=dt.time(14), end=dt.time(18)
        )
        with act_as(app, cast.bystander):
            r = await async_client.post(
                "/api/v1/bookings/", json={"shift_id": str(open_shift.id)}
            )
        assert r.status_code == 201, r.text

        r = await _redeem(
            async_client,
            app,
            cast,
            cast.bystander,
            task=cast.second_point,
            user_id=str(cast.volunteer.id),
        )
        assert r.status_code == 201, r.text
        assert r.json()["entry"]["actor_name"] == cast.bystander.name

        await _manual_rule(db_session, cast, "in_charge")
        r = await _redeem(
            async_client,
            app,
            cast,
            cast.bystander,
            task=cast.second_point,
            user_id=str(cast.volunteer.id),
        )
        assert r.status_code == 403
        assert _code(r) == "voucher.manual_not_allowed"

    async def test_only_for_members(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        r = await _redeem(
            async_client, app, cast, cast.admin, user_id=str(cast.outsider.id)
        )
        assert r.status_code == 404
        assert _code(r) == "event.member_not_found"

    @pytest.mark.parametrize("who", ["admin", "manager", "staff"])
    async def test_never_more_than_they_have_whatever_the_picker_showed(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
        who: str,
    ) -> None:
        """The picker's counts are a read from a moment ago; the server checks
        the balance again under the ledger lock, for every redeemer."""
        redeemer: User = getattr(cast, who)
        volunteer = str(cast.volunteer.id)
        r = await _redeem(
            async_client, app, cast, redeemer, user_id=volunteer, amount=4
        )
        assert r.status_code == 409
        assert _code(r) == "voucher.insufficient"
        assert r.json()["available"] == 3
        assert await _entries(db_session, cast) == []

        r = await _redeem(
            async_client, app, cast, redeemer, user_id=volunteer, amount=3
        )
        assert r.status_code == 201
        r = await _redeem(async_client, app, cast, redeemer, user_id=volunteer)
        assert r.status_code == 409
        assert _code(r) == "voucher.insufficient"
        assert r.json()["available"] == 0
        # Someone who never earned any is refused the same way.
        r = await _redeem(
            async_client, app, cast, redeemer, user_id=str(cast.bystander.id)
        )
        assert r.status_code == 409
        assert _code(r) == "voucher.insufficient"
        assert len(await _entries(db_session, cast)) == 1


@pytest.mark.asyncio
class TestSnapshotsAndSandbox:
    async def test_a_redemption_keeps_the_points_name_after_the_task_is_gone(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        await _redeem(
            async_client, app, cast, cast.admin, user_id=str(cast.volunteer.id)
        )
        with act_as(app, cast.admin):
            r = await async_client.delete(f"/api/v1/tasks/{cast.point.id}")
        assert r.status_code == 204

        with act_as(app, cast.volunteer):
            r = await async_client.get(f"{_base(cast.event)}/me")
        (entry,) = r.json()["entries"]
        assert entry["task_name"] == "Theke"
        assert r.json()["summary"]["redeemed"] == 1

    async def test_a_demo_is_invisible_to_the_superadmin(
        self,
        async_client: AsyncClient,
        test_sandbox: SandboxSetup,
        as_admin: None,
    ) -> None:
        for method, path in (
            ("GET", "me"),
            ("GET", "people"),
            ("GET", "points"),
            ("POST", "me/pass"),
        ):
            r = await async_client.request(
                method, f"{_base(test_sandbox.event)}/{path}"
            )
            assert r.status_code == 404, path
            assert _code(r) == "event.not_found"


# ── Accounts ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAccounts:
    async def test_my_vouchers(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        with act_as(app, cast.volunteer):
            r = await async_client.get(f"{_base(cast.event)}/me")
        assert r.status_code == 200
        body = r.json()
        assert body["summary"]["earned"] == 3
        assert body["summary"]["available"] == 3
        assert body["summary"]["role"] == "member"
        # One number: earned vouchers stay earned, so there is no separate
        # balance that could go below zero.
        assert "balance" not in body["summary"]
        (shift,) = body["shifts"]
        assert shift["task_name"] == "Aufbau"
        assert shift["completed"] is True
        assert shift["vouchers"] == 3
        # 12:00 in Berlin in June is 10:00 UTC.
        assert shift["ends_at"] == "2026-06-11T10:00:00"

    async def test_not_for_an_outsider(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        with act_as(app, cast.outsider):
            r = await async_client.get(f"{_base(cast.event)}/me")
        assert r.status_code == 403

    async def test_one_persons_account(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        url = f"{_base(cast.event)}/people/{cast.volunteer.id}"
        with act_as(app, cast.admin):
            r = await async_client.get(url)
            assert r.status_code == 200
            assert "balance" not in r.json()["summary"]
        with act_as(app, cast.volunteer):
            assert (await async_client.get(url)).status_code == 200
        with act_as(app, cast.bystander):
            r = await async_client.get(url)
        assert r.status_code == 403
        assert _code(r) == "event.forbidden"

    async def test_an_admin_reads_only_people_who_have_a_part_in_the_event(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        """Anyone can create an event and be its admin, so being one must not
        open the name and e-mail of every account on the installation."""
        with act_as(app, cast.admin):
            r = await async_client.get(f"{_base(cast.event)}/people/{cast.outsider.id}")
        assert r.status_code == 404
        assert _code(r) == "event.member_not_found"
        assert cast.outsider.email is not None
        assert cast.outsider.email not in r.text

        # Someone who has left but worked here can still be looked up.
        await db_session.execute(
            delete(EventMembership).where(
                col(EventMembership.event_id) == cast.event.id,
                col(EventMembership.user_id) == cast.volunteer.id,
            )
        )
        await db_session.flush()
        with act_as(app, cast.admin):
            r = await async_client.get(
                f"{_base(cast.event)}/people/{cast.volunteer.id}"
            )
        assert r.status_code == 200
        assert r.json()["summary"]["role"] is None
        assert r.json()["summary"]["earned"] == 3

    async def test_the_overview_is_for_admins(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        url = f"{_base(cast.event)}/people"
        with act_as(app, cast.admin):
            r = await async_client.get(url)
        assert r.status_code == 200
        assert r.json()[0]["user_id"] == str(cast.volunteer.id)
        assert r.json()[0]["available"] == 3
        assert all("balance" not in row for row in r.json())
        for user in (cast.volunteer, cast.manager):
            with act_as(app, user):
                assert (await async_client.get(url)).status_code == 403


# ── Corrections ───────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCorrections:
    async def _create(
        self,
        client: AsyncClient,
        app: FastAPI,
        cast: Cast,
        *,
        as_user: User | None = None,
        **body: Any,
    ) -> Response:
        payload = {"user_id": str(cast.volunteer.id), "amount": 2, "note": "Aufbau"}
        payload.update(body)
        with act_as(app, as_user or cast.admin):
            return await client.post(f"{_base(cast.event)}/adjustments", json=payload)

    async def test_an_admin_adds_one(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        r = await self._create(async_client, app, cast, note="  Aufbau  ")
        assert r.status_code == 201
        body = r.json()
        assert body["kind"] == "adjustment"
        assert body["amount"] == 2
        assert body["note"] == "Aufbau"
        assert body["actor_name"] == cast.admin.name

        # 3 earned + 2: taking away 6 would go below zero, so the balance
        # stays as it is; taking away exactly the 5 left is fine.
        r = await self._create(async_client, app, cast, amount=-6)
        assert r.status_code == 409
        assert _code(r) == "voucher.correction_exceeds_available"
        assert r.json()["available"] == 5
        r = await self._create(async_client, app, cast, amount=-5)
        assert r.status_code == 201
        with act_as(app, cast.volunteer):
            summary = (await async_client.get(f"{_base(cast.event)}/me")).json()[
                "summary"
            ]
        assert summary["adjusted"] == -3
        assert summary["available"] == 0

    @pytest.mark.parametrize(
        "body", [{"amount": 0}, {"note": "   "}, {"note": ""}, {"amount": 1000}]
    )
    async def test_refuses_nonsense(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast, body: dict[str, Any]
    ) -> None:
        r = await self._create(async_client, app, cast, **body)
        assert r.status_code == 422

    async def test_not_for_someone_who_never_was_in_the_event(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        r = await self._create(async_client, app, cast, user_id=str(cast.outsider.id))
        assert r.status_code == 404
        assert _code(r) == "event.member_not_found"

    async def test_a_former_member_with_bookings_can_be_settled(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        await _shift_for(
            db_session, cast.work, cast.outsider, start=dt.time(6), end=dt.time(7)
        )
        r = await self._create(async_client, app, cast, user_id=str(cast.outsider.id))
        assert r.status_code == 201

    async def test_a_former_member_with_entries_can_be_settled(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        db_session.add(
            VoucherEntry(
                event_id=cast.event.id,
                user_id=cast.outsider.id,
                kind="redemption",
                amount=-1,
                method="manual",
            )
        )
        await db_session.flush()
        r = await self._create(async_client, app, cast, user_id=str(cast.outsider.id))
        assert r.status_code == 201

    async def test_a_former_member_with_only_settled_earnings_can_be_settled(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        """The volunteer leaves, then an organiser deletes their ended shift:
        what it earned is settled and the booking cancelled, so the earning is
        all that says they worked here. They stay in the overview, and their
        row still opens and takes a correction."""
        await db_session.execute(
            delete(EventMembership).where(
                col(EventMembership.event_id) == cast.event.id,
                col(EventMembership.user_id) == cast.volunteer.id,
            )
        )
        await db_session.flush()
        shift_id = (
            await db_session.execute(
                select(col(Shift.id)).where(col(Shift.task_id) == cast.work.id)
            )
        ).scalar_one()
        with act_as(app, cast.admin):
            r = await async_client.delete(f"/api/v1/shifts/{shift_id}")
            assert r.status_code == 204, r.text
            overview = (await async_client.get(f"{_base(cast.event)}/people")).json()
        assert (
            await crud_booking.count_by_user(
                db_session,
                user_id=cast.volunteer.id,
                status="confirmed",
                event_id=cast.event.id,
            )
            == 0
        )
        assert await _entries(db_session, cast) == []
        (row,) = [b for b in overview if b["user_id"] == str(cast.volunteer.id)]
        assert (row["role"], row["available"]) == (None, 3)

        with act_as(app, cast.admin):
            r = await async_client.get(
                f"{_base(cast.event)}/people/{cast.volunteer.id}"
            )
        assert r.status_code == 200, r.text
        assert r.json()["summary"]["earned"] == 3
        r = await self._create(async_client, app, cast, amount=-1)
        assert r.status_code == 201, r.text

    @pytest.mark.parametrize("who", ["volunteer", "manager"])
    async def test_admins_only(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast, who: str
    ) -> None:
        r = await self._create(async_client, app, cast, as_user=getattr(cast, who))
        assert r.status_code == 403

    async def test_edit_and_delete_a_correction(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        entry_id = (await self._create(async_client, app, cast)).json()["id"]
        url = f"{_base(cast.event)}/adjustments/{entry_id}"
        with act_as(app, cast.admin):
            r = await async_client.patch(url, json={"amount": -1, "note": "Doch nicht"})
            assert r.status_code == 200
            assert r.json()["amount"] == -1
            assert r.json()["note"] == "Doch nicht"
            assert (
                await async_client.patch(url, json={"amount": 0})
            ).status_code == 422
            assert (await async_client.delete(url)).status_code == 204
        assert await _entries(db_session, cast) == []

    async def test_a_change_may_not_take_away_more_than_is_left(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        """3 earned, a correction of -1 leaves 2: changing it to -10 would take
        9 more, so it is refused; to -3 takes 2 and is fine."""
        entry_id = (await self._create(async_client, app, cast, amount=-1)).json()["id"]
        url = f"{_base(cast.event)}/adjustments/{entry_id}"
        with act_as(app, cast.admin):
            r = await async_client.patch(url, json={"amount": -10})
            assert r.status_code == 409
            assert _code(r) == "voucher.correction_exceeds_available"
            assert r.json()["available"] == 2
            # Only the note: no amount, no check.
            r = await async_client.patch(url, json={"note": "Nur der Grund"})
            assert r.status_code == 200
            r = await async_client.patch(url, json={"amount": -3})
            assert r.status_code == 200
        (entry,) = await _entries(db_session, cast)
        assert (entry.amount, entry.note) == (-3, "Nur der Grund")

    async def test_deleting_an_addition_already_spent_is_refused(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        """3 earned and 5 added, 5 redeemed at a stand: 3 are left, so the 5
        added can no longer be taken back."""
        entry_id = (await self._create(async_client, app, cast, amount=5)).json()["id"]
        r = await _redeem(
            async_client,
            app,
            cast,
            cast.admin,
            amount=5,
            user_id=str(cast.volunteer.id),
        )
        assert r.status_code == 201, r.text
        url = f"{_base(cast.event)}/adjustments/{entry_id}"
        with act_as(app, cast.admin):
            r = await async_client.delete(url)
        assert r.status_code == 409
        assert _code(r) == "voucher.correction_exceeds_available"
        assert r.json()["available"] == 3
        assert len(await _entries(db_session, cast)) == 2

    async def test_adding_is_always_allowed(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        """Nothing to cap, even for someone with nothing left."""
        r = await self._create(async_client, app, cast, amount=-3)
        assert r.status_code == 201
        r = await self._create(async_client, app, cast, amount=4)
        assert r.status_code == 201

    async def test_a_redemption_cannot_be_edited(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        r = await _redeem(
            async_client, app, cast, cast.admin, user_id=str(cast.volunteer.id)
        )
        url = f"{_base(cast.event)}/adjustments/{r.json()['entry']['id']}"
        with act_as(app, cast.admin):
            for r in (
                await async_client.patch(url, json={"amount": -3}),
                await async_client.delete(url),
            ):
                assert r.status_code == 409
                assert _code(r) == "voucher.entry_not_editable"

    async def test_an_entry_of_another_event_is_not_found(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        elsewhere = VoucherEntry(
            event_id=cast.other_event.id,
            user_id=cast.volunteer.id,
            kind="adjustment",
            amount=1,
            note="Anderswo",
        )
        db_session.add(elsewhere)
        await db_session.flush()
        with act_as(app, cast.admin):
            r = await async_client.delete(
                f"{_base(cast.event)}/adjustments/{elsewhere.id}"
            )
        assert r.status_code == 404
        assert _code(r) == "voucher.entry_not_found"


# ── Points ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPoints:
    async def _points(
        self, client: AsyncClient, app: FastAPI, cast: Cast, user: User
    ) -> dict[str, dict[str, Any]]:
        with act_as(app, user):
            r = await client.get(f"{_base(cast.event)}/points")
        assert r.status_code == 200
        return {p["name"]: p for p in r.json()}

    @pytest.mark.parametrize(
        ("rule", "who", "theke", "ausgabe"),
        [
            # (can_redeem, can_redeem_manually) at each point
            ("on_shift", "admin", (True, True), (True, True)),
            ("on_shift", "manager", (True, True), (False, False)),
            ("on_shift", "staff", (True, True), (False, False)),
            ("on_shift", "second_staff", (False, False), (True, True)),
            ("on_shift", "bystander", (False, False), (False, False)),
            ("in_charge", "admin", (True, True), (True, True)),
            ("in_charge", "manager", (True, True), (False, False)),
            ("in_charge", "staff", (True, False), (False, False)),
            ("in_charge", "second_staff", (False, False), (True, False)),
            ("in_charge", "bystander", (False, False), (False, False)),
        ],
    )
    async def test_who_may_redeem_where(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
        rule: str,
        who: str,
        theke: tuple[bool, bool],
        ausgabe: tuple[bool, bool],
    ) -> None:
        await _manual_rule(db_session, cast, rule)
        points = await self._points(async_client, app, cast, getattr(cast, who))
        assert set(points) == {"Theke", "Ausgabe"}
        for name, expected in (("Theke", theke), ("Ausgabe", ausgabe)):
            assert (
                points[name]["can_redeem"],
                points[name]["can_redeem_manually"],
            ) == expected, name
        # The volunteer desk is gone: the event decides, not the point.
        assert "is_desk" not in points["Ausgabe"]
        assert [m["user_id"] for m in points["Theke"]["managers"]] == [
            str(cast.manager.id)
        ]

    async def test_a_draft_point_only_for_those_who_run_it(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        cast.point.status = "draft"
        db_session.add(cast.point)
        await db_session.flush()
        assert "Theke" in await self._points(async_client, app, cast, cast.manager)
        assert "Theke" in await self._points(async_client, app, cast, cast.admin)
        assert "Theke" not in await self._points(async_client, app, cast, cast.staff)

    async def test_recent_redemptions_at_a_point(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        issued = await _issue(async_client, app, cast)
        await _redeem(
            async_client, app, cast, cast.staff, code=issued["code"], amount=1
        )
        await _redeem(
            async_client,
            app,
            cast,
            cast.manager,
            user_id=str(cast.volunteer.id),
            amount=2,
        )
        url = f"{_base(cast.event)}/points/{cast.point.id}/entries"

        for user in (cast.admin, cast.manager):
            with act_as(app, user):
                r = await async_client.get(url)
            assert r.status_code == 200
            assert r.json()["today_amount"] == 3
            assert r.json()["today_count"] == 2
            assert r.json()["total_amount"] == 3
            assert r.json()["total_count"] == 2
            assert len(r.json()["items"]) == 2
            assert r.json()["items"][0]["user_name"] == cast.volunteer.name

        with act_as(app, cast.staff):
            r = await async_client.get(url)
        assert r.status_code == 200
        assert [i["actor_name"] for i in r.json()["items"]] == [cast.staff.name]
        assert r.json()["today_amount"] == 1
        assert r.json()["today_count"] == 1
        assert r.json()["total_amount"] == 1
        assert r.json()["total_count"] == 1

        with act_as(app, cast.bystander):
            r = await async_client.get(url)
        assert r.status_code == 403
        assert _code(r) == "voucher.not_allowed"

    async def test_today_counts_the_whole_day_not_the_page(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        """The header's "Today: n vouchers" adds up the whole event day.

        The day starts at midnight on the event wall clock (Berlin, UTC+2 in
        June): 23:50 the evening before is yesterday, and 00:10, still 10 June
        in UTC, is today. Entries beyond ``limit`` still count; an on-shift
        redeemer gets the totals of their own.
        """
        # 23:50 on 10 June in Berlin is 21:50 UTC: yesterday, left out.
        yesterday = dt.datetime(2026, 6, 10, 21, 50)
        # 00:10 on 11 June in Berlin is 22:10 UTC the day before: today.
        just_after_midnight = dt.datetime(2026, 6, 10, 22, 10)
        rows = [
            (yesterday, 5, cast.manager),
            (just_after_midnight, 2, cast.manager),
            (dt.datetime(2026, 6, 11, 9, 0), 1, cast.staff),
            (dt.datetime(2026, 6, 11, 11, 0), 3, cast.staff),
        ]
        for created_at, amount, actor in rows:
            db_session.add(
                VoucherEntry(
                    event_id=cast.event.id,
                    user_id=cast.volunteer.id,
                    kind="redemption",
                    amount=-amount,
                    method="manual",
                    task_id=cast.point.id,
                    task_name=cast.point.name,
                    actor_id=actor.id,
                    actor_name=actor.name,
                    created_at=created_at,
                )
            )
        await db_session.flush()
        url = f"{_base(cast.event)}/points/{cast.point.id}/entries"

        with act_as(app, cast.manager):
            r = await async_client.get(url, params={"limit": 1})
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1
        assert r.json()["today_count"] == 3
        assert r.json()["today_amount"] == 6
        # The total takes in yesterday as well, still not just the page.
        assert r.json()["total_count"] == 4
        assert r.json()["total_amount"] == 11

        with act_as(app, cast.staff):
            r = await async_client.get(url)
        assert r.status_code == 200
        assert r.json()["today_count"] == 2
        assert r.json()["today_amount"] == 4
        assert r.json()["total_count"] == 2
        assert r.json()["total_amount"] == 4

    async def test_the_totals_leave_out_other_points_and_corrections(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        """What "redeemed here" means: redemptions at this point, and nothing
        else in the volunteer's ledger."""
        await _redeem(
            async_client, app, cast, cast.admin, user_id=str(cast.volunteer.id)
        )
        await _redeem(
            async_client,
            app,
            cast,
            cast.admin,
            task=cast.second_point,
            user_id=str(cast.volunteer.id),
        )
        with act_as(app, cast.admin):
            r = await async_client.post(
                f"{_base(cast.event)}/adjustments",
                json={"user_id": str(cast.volunteer.id), "amount": 5, "note": "Bonus"},
            )
        assert r.status_code == 201, r.text
        with act_as(app, cast.admin):
            r = await async_client.get(
                f"{_base(cast.event)}/points/{cast.point.id}/entries"
            )
        assert (r.json()["total_count"], r.json()["total_amount"]) == (1, 1)

    async def test_recent_redemptions_need_the_task_in_this_event(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.get(
                f"{_base(cast.event)}/points/{cast.other_point.id}/entries"
            )
            assert r.status_code == 404
            assert _code(r) == "task.not_found"
            r = await async_client.get(
                f"{_base(cast.event)}/points/{cast.plain.id}/entries"
            )
            assert r.status_code == 422
            assert _code(r) == "voucher.not_a_point"


@pytest.mark.asyncio
class TestPointPeople:
    """``GET .../points/{task_id}/people``: what everyone can redeem, for
    whoever may pick the person at that point."""

    def _url(self, cast: Cast, task: Task | None = None) -> str:
        return f"{_base(cast.event)}/points/{(task or cast.point).id}/people"

    async def _get(
        self,
        client: AsyncClient,
        app: FastAPI,
        cast: Cast,
        user: User,
        task: Task | None = None,
    ) -> Response:
        with act_as(app, user):
            return await client.get(self._url(cast, task))

    async def _member_ids(self, db: AsyncSession, event: Event) -> set[str]:
        rows = await db.execute(
            select(col(EventMembership.user_id)).where(
                col(EventMembership.event_id) == event.id
            )
        )
        return {str(uid) for uid in rows.scalars()}

    @pytest.mark.parametrize("rule", ["on_shift", "in_charge"])
    @pytest.mark.parametrize("who", ["admin", "manager"])
    async def test_admins_and_people_in_charge_see_everyones_count(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
        who: str,
        rule: str,
    ) -> None:
        await _manual_rule(db_session, cast, rule)
        r = await self._get(async_client, app, cast, getattr(cast, who))
        assert r.status_code == 200, r.text
        counts = {p["user_id"]: p["available"] for p in r.json()}
        # Every member of the event, and only them.
        assert set(counts) == await self._member_ids(db_session, cast.event)
        assert counts[str(cast.volunteer.id)] == 3
        assert counts[str(cast.bystander.id)] == 0
        # Nothing but the number: names and faces come from the member list.
        assert all(set(p) == {"user_id", "available"} for p in r.json())

    async def test_staff_on_shift_see_the_same_numbers_by_default(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        admin_view = await self._get(async_client, app, cast, cast.admin)
        staff_view = await self._get(async_client, app, cast, cast.staff)
        assert staff_view.status_code == 200, staff_view.text
        assert sorted(staff_view.json(), key=lambda p: p["user_id"]) == sorted(
            admin_view.json(), key=lambda p: p["user_id"]
        )
        # The second point's staff, at their own point.
        r = await self._get(
            async_client, app, cast, cast.second_staff, task=cast.second_point
        )
        assert r.status_code == 200

    async def test_with_in_charge_staff_on_shift_get_none(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        """They need the code there, so they have no use for anyone's count."""
        await _manual_rule(db_session, cast, "in_charge")
        r = await self._get(async_client, app, cast, cast.staff)
        assert r.status_code == 403
        assert _code(r) == "voucher.manual_not_allowed"

    @pytest.mark.parametrize("rule", ["on_shift", "in_charge"])
    @pytest.mark.parametrize("who", ["bystander", "second_staff", "volunteer"])
    async def test_a_member_not_redeeming_here_gets_none(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
        who: str,
        rule: str,
    ) -> None:
        await _manual_rule(db_session, cast, rule)
        r = await self._get(async_client, app, cast, getattr(cast, who))
        assert r.status_code == 403
        assert _code(r) == "voucher.not_allowed"

    async def test_after_the_shift_the_staff_get_none(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        monkeypatch: pytest.MonkeyPatch,
        cast: Cast,
    ) -> None:
        """Half an hour after 18:00 the shift no longer runs."""
        monkeypatch.setattr(
            "app.logic.clock.wall_clock_now",
            fixed_clock(dt.datetime(2026, 6, 11, 18, 31)),
        )
        r = await self._get(async_client, app, cast, cast.staff)
        assert r.status_code == 403
        assert _code(r) == "voucher.not_allowed"

    async def test_another_event_stays_out_of_it(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        # Someone in no event may look at this public one, and gets nothing.
        r = await self._get(async_client, app, cast, cast.outsider)
        assert r.status_code == 403
        assert _code(r) == "voucher.not_allowed"
        # The other event's point through this event's address is no point here.
        r = await self._get(async_client, app, cast, cast.admin, task=cast.other_point)
        assert r.status_code == 404
        assert _code(r) == "task.not_found"
        # And a member here who is in no role there cannot read that event's.
        with act_as(app, cast.manager):
            r = await async_client.get(
                f"{_base(cast.other_event)}/points/{cast.other_point.id}/people"
            )
        assert r.status_code == 404

    async def test_only_at_a_point(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        r = await self._get(async_client, app, cast, cast.admin, task=cast.plain)
        assert r.status_code == 422
        assert _code(r) == "voucher.not_a_point"

    async def test_someone_who_left_is_not_listed(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        """They keep their vouchers in the organisers' overview, but nobody can
        pick them at a stand any more."""
        await db_session.execute(
            delete(EventMembership).where(
                col(EventMembership.user_id) == cast.volunteer.id,
                col(EventMembership.event_id) == cast.event.id,
            )
        )
        await db_session.flush()
        r = await self._get(async_client, app, cast, cast.manager)
        assert str(cast.volunteer.id) not in {p["user_id"] for p in r.json()}
        with act_as(app, cast.admin):
            overview = await async_client.get(f"{_base(cast.event)}/people")
        assert str(cast.volunteer.id) in {p["user_id"] for p in overview.json()}

    async def test_a_redemption_shows_in_the_next_read(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        await _redeem(
            async_client,
            app,
            cast,
            cast.staff,
            user_id=str(cast.volunteer.id),
            amount=2,
        )
        r = await self._get(async_client, app, cast, cast.staff)
        counts = {p["user_id"]: p["available"] for p in r.json()}
        assert counts[str(cast.volunteer.id)] == 1


# ── Flags on events and tasks ─────────────────────────────────────


@pytest.mark.asyncio
class TestFlags:
    async def test_event_counts_for_members(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        # A draft that earns and a draft point do not count.
        await _task(
            db_session,
            cast.event,
            cast.volunteer,
            name="Entwurf",
            status="draft",
            vouchers_per_shift=2,
            is_voucher_point=True,
        )
        with act_as(app, cast.volunteer):
            r = await async_client.get(f"/api/v1/events/{cast.event.id}")
        assert r.json()["voucher_task_count"] == 1
        assert r.json()["voucher_point_count"] == 2

        # An archived task still earns (its shifts keep counting, so the
        # organisers still need the overview), but no longer takes vouchers.
        await _task(
            db_session,
            cast.event,
            cast.volunteer,
            name="Archiv",
            status="archived",
            vouchers_per_shift=2,
            is_voucher_point=True,
        )
        with act_as(app, cast.volunteer):
            r = await async_client.get(f"/api/v1/events/{cast.event.id}")
        assert r.json()["voucher_task_count"] == 2
        assert r.json()["voucher_point_count"] == 2

        with act_as(app, cast.outsider):
            r = await async_client.get(f"/api/v1/events/{cast.event.id}")
        assert r.status_code == 200  # a public event
        assert r.json()["voucher_task_count"] == 0
        assert r.json()["voucher_point_count"] == 0

    @pytest.mark.parametrize(
        ("who", "expected"),
        [
            ("admin", True),
            ("manager", True),
            ("staff", True),
            ("bystander", False),
        ],
    )
    async def test_task_can_redeem(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        cast: Cast,
        who: str,
        expected: bool,
    ) -> None:
        with act_as(app, getattr(cast, who)):
            one = await async_client.get(f"/api/v1/tasks/{cast.point.id}")
            listed = await async_client.get(
                "/api/v1/tasks/", params={"event_id": str(cast.event.id)}
            )
            plain = await async_client.get(f"/api/v1/tasks/{cast.plain.id}")
        assert one.json()["can_redeem"] is expected
        by_id = {t["id"]: t for t in listed.json()["items"]}
        assert by_id[str(cast.point.id)]["can_redeem"] is expected
        assert plain.json()["can_redeem"] is False

    async def test_a_shift_just_after_midnight_opens_before_it(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
        wall_clock: Callable[[dt.datetime], None],
    ) -> None:
        tomorrow = DAY + dt.timedelta(days=1)
        await _shift_for(
            db_session,
            cast.point,
            cast.bystander,
            date=tomorrow,
            start=dt.time(0, 15),
            end=dt.time(4),
        )
        wall_clock(dt.datetime(2026, 6, 11, 23, 50))
        with act_as(app, cast.bystander):
            r = await async_client.get(f"/api/v1/tasks/{cast.point.id}")
        assert r.json()["can_redeem"] is True


# ── Task settings ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestTaskSettings:
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("vouchers_per_shift", 5),
            ("is_voucher_point", False),
        ],
    )
    async def test_people_in_charge_cannot_change_them(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        cast: Cast,
        field: str,
        value: Any,
    ) -> None:
        with act_as(app, cast.manager):
            r = await async_client.patch(
                f"/api/v1/tasks/{cast.point.id}", json={field: value}
            )
        assert r.status_code == 403
        assert r.json()["code"] == "task.admin_only_field"
        assert r.json()["fields"] == [field]

    async def test_sent_unchanged_they_are_ignored(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        with act_as(app, cast.manager):
            r = await async_client.patch(
                f"/api/v1/tasks/{cast.point.id}",
                json={
                    "name": "Bar",
                    "vouchers_per_shift": 0,
                    "is_voucher_point": True,
                },
            )
        assert r.status_code == 200
        assert r.json()["name"] == "Bar"

    async def test_an_admin_sets_them(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        url = f"/api/v1/tasks/{cast.second_point.id}"
        with act_as(app, cast.admin):
            r = await async_client.patch(url, json={"vouchers_per_shift": 4})
            assert r.status_code == 200
            assert r.json()["vouchers_per_shift"] == 4

            r = await async_client.patch(url, json={"is_voucher_point": False})
            assert r.status_code == 200
            assert r.json()["is_voucher_point"] is False

            r = await async_client.patch(url, json={"vouchers_per_shift": 51})
            assert r.status_code == 422
            r = await async_client.patch(url, json={"vouchers_per_shift": None})
            assert r.status_code == 200
            assert r.json()["vouchers_per_shift"] == 4

    async def test_an_old_clients_desk_switch_is_ignored(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        """``is_voucher_desk`` is gone; a client that still sends it is not
        refused, and nothing reads it back."""
        with act_as(app, cast.admin):
            r = await async_client.patch(
                f"/api/v1/tasks/{cast.point.id}", json={"is_voucher_desk": True}
            )
        assert r.status_code == 200
        assert "is_voucher_desk" not in r.json()

    async def test_created_with_shifts(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.post(
                "/api/v1/tasks/with-shifts",
                json={
                    "name": "Getränke",
                    "start_date": "2026-06-12",
                    "end_date": "2026-06-12",
                    "event_id": str(cast.event.id),
                    "vouchers_per_shift": 2,
                    "is_voucher_point": True,
                    # An old client: ignored.
                    "is_voucher_desk": True,
                    "schedule": {
                        "default_start_time": "10:00:00",
                        "default_end_time": "12:00:00",
                        "shift_duration_minutes": 60,
                    },
                },
            )
        assert r.status_code == 201, r.text
        task = r.json()["task"]
        assert task["vouchers_per_shift"] == 2
        assert task["is_voucher_point"] is True
        assert "is_voucher_desk" not in task


# ── Leaving the event ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestLeaving:
    @pytest.mark.parametrize("removed_by", ["self", "admin"])
    async def test_unfinished_bookings_are_cancelled_and_worked_ones_kept(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
        removed_by: str,
    ) -> None:
        later = await _shift_for(
            db_session,
            cast.work,
            cast.staff,
            date=DAY + dt.timedelta(days=1),
            start=dt.time(10),
            end=dt.time(12),
        )
        earlier = await _shift_for(
            db_session, cast.work, cast.staff, start=dt.time(9), end=dt.time(11)
        )
        # cast.staff_shift (14:00-18:00 today) is running: not over yet.
        actor = cast.staff if removed_by == "self" else cast.admin
        with act_as(app, actor):
            r = await async_client.delete(
                f"/api/v1/events/{cast.event.id}/members/{cast.staff.id}"
            )
        assert r.status_code == 204

        rows = await db_session.execute(
            select(Booking, Shift)
            .join(Shift, col(Shift.id) == col(Booking.shift_id))
            .where(col(Booking.user_id) == cast.staff.id)
            .execution_options(populate_existing=True)
        )
        by_shift = {shift.id: booking for booking, shift in rows.all()}
        assert by_shift[earlier.id].status == "confirmed"
        for gone in (later, cast.staff_shift):
            booking = by_shift[gone.id]
            assert booking.status == "cancelled"
            assert booking.cancelled_shift_title == gone.title
            assert booking.cancelled_shift_date == gone.date
            assert booking.cancelled_task_name in ("Aufbau", "Theke")

        # What was worked still counts for them.
        acc = await vouchers.account(db_session, cast.event.id, cast.staff, now=NOW)
        assert acc.summary.earned == 3
        assert acc.summary.upcoming == 0

    async def test_their_reminders_go_with_the_booking(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
    ) -> None:
        from app.models.booking_reminder import BookingReminder

        booking = (
            await db_session.execute(
                select(Booking).where(
                    col(Booking.shift_id) == cast.staff_shift.id,
                    col(Booking.user_id) == cast.staff.id,
                )
            )
        ).scalar_one()
        db_session.add(
            BookingReminder(
                booking_id=booking.id,
                user_id=cast.staff.id,
                shift_id=cast.staff_shift.id,
                remind_at=dt.datetime(2099, 1, 1),
                offset_minutes=60,
            )
        )
        await db_session.flush()

        with act_as(app, cast.staff):
            r = await async_client.delete(
                f"/api/v1/events/{cast.event.id}/members/{cast.staff.id}"
            )
        assert r.status_code == 204
        pending = await db_session.scalar(
            select(func.count())
            .select_from(BookingReminder)
            .where(
                col(BookingReminder.booking_id) == booking.id,
                col(BookingReminder.status) == "pending",
            )
        )
        assert pending == 0


@pytest.mark.asyncio
class TestAnArchivedPoint:
    """It has left the list of points, so nothing else may reach it either."""

    @pytest_asyncio.fixture
    async def archived(self, db_session: AsyncSession, cast: Cast) -> Task:
        cast.point.status = "archived"
        db_session.add(cast.point)
        await db_session.flush()
        return cast.point

    @pytest.mark.parametrize("who", ["admin", "manager", "staff"])
    async def test_redeeming_is_refused_and_takes_nothing(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        db_session: AsyncSession,
        cast: Cast,
        archived: Task,
        who: str,
    ) -> None:
        issued = await _issue(async_client, app, cast)

        r = await _redeem(
            async_client, app, cast, getattr(cast, who), code=issued["code"]
        )

        assert r.status_code == 409
        assert _code(r) == "voucher.point_archived"
        assert await _entries(db_session, cast) == []

    async def test_checking_a_code_is_refused(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast, archived: Task
    ) -> None:
        issued = await _issue(async_client, app, cast)

        r = await _check(async_client, app, cast, cast.admin, code=issued["code"])

        assert r.status_code == 409
        assert _code(r) == "voucher.point_archived"

    @pytest.mark.parametrize("path", ["entries", "people"])
    async def test_its_lists_are_refused(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        cast: Cast,
        archived: Task,
        path: str,
    ) -> None:
        with act_as(app, cast.admin):
            r = await async_client.get(
                f"{_base(cast.event)}/points/{archived.id}/{path}"
            )

        assert r.status_code == 409
        assert _code(r) == "voucher.point_archived"

    async def test_the_gate_still_comes_first(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast, archived: Task
    ) -> None:
        """A bystander learns nothing about the task's status."""
        issued = await _issue(async_client, app, cast)

        r = await _redeem(async_client, app, cast, cast.bystander, code=issued["code"])

        assert r.status_code == 403
        assert _code(r) == "voucher.not_allowed"

    @pytest.mark.parametrize("who", ["admin", "manager"])
    async def test_the_task_says_it_cannot_redeem(
        self,
        async_client: AsyncClient,
        app: FastAPI,
        cast: Cast,
        archived: Task,
        who: str,
    ) -> None:
        with act_as(app, getattr(cast, who)):
            r = await async_client.get(f"/api/v1/tasks/{archived.id}")

        assert r.status_code == 200, r.text
        assert r.json()["can_redeem"] is False

    async def test_a_published_point_is_unaffected(
        self, async_client: AsyncClient, app: FastAPI, cast: Cast
    ) -> None:
        issued = await _issue(async_client, app, cast)

        r = await _redeem(async_client, app, cast, cast.admin, code=issued["code"])

        assert r.status_code == 201, r.text
