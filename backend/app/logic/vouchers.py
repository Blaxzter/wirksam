"""Volunteer vouchers: what someone has earned, and spending it at a stand.

**Earned is earned.** A volunteer earns ``task.vouchers_per_shift`` for every
booking that counts as worked (``work_hours.counts_as_worked``) on a shift that
has ended (``work_hours.shift_ends_at`` against ``clock.wall_clock_now()``).
That figure is *derived*, like worked hours (``app.logic.work_hours``), until
something would change it for a shift already over: a rate change, deleting
or moving a shift, a batch or the task, the event's shift dates, deleting the
account that created the task. Every one of those routes first calls
:func:`settle_earnings`, which freezes what the ended bookings earned in
``voucher_earnings``. Reads (:func:`_voucher_shifts`) add the settled rows to
the bookings not settled yet, in one statement.

That is correct because of one invariant: every ended, worked booking without
an earning row still derives today exactly what it earned when its shift
ended. Time passing cannot break it (a shift ends at the rate in force, which
stays the current rate until a rate change settles it), and every other change
settles first. A settled booking is left out of the derivation for good, so a
shift moved into the future and ending again cannot earn twice.

``voucher_entries`` holds what cannot be derived at all: redemptions and the
corrections event admins make. So::

    balance   = earned - redeemed + adjusted     (may be below zero)
    available = max(balance, 0)

Nothing takes earned vouchers back any more, but a correction can still take a
balance below zero. The app then shows 0 available and refuses redemptions.

Neither query filters on membership or task status. Someone who worked and then
left still worked, and an archived task's shifts still count. What keeps that
honest is upstream: leaving cancels the person's unfinished bookings, nobody can
book an ended shift, nor (unless they manage the task) a shift that earns
vouchers once it has started, and members cannot book shifts of unpublished
tasks.

**Redeeming** (:func:`redeem`) is serialised per (event, volunteer) with a
transaction-scoped advisory lock (``crud.voucher.lock_ledger``). It is a logic
function rather than route code so the concurrency test can call it on two
sessions. Settling takes no lock: it turns a derived amount into the same
stored amount, so no total changes, and a redemption reading the earned
figure in one statement sees the booking either derived or settled, never both
nor neither. The routes do all the gating: this module must not import
``app.logic.permissions``, which imports it.

Design: ``docs/plans/2026-10-30-task-managers-and-vouchers.md``, and for
settling ``docs/plans/2026-11-02-people-in-charge-and-vouchers-followups.md``
(Decision G).
"""

import datetime as dt
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

from sqlalchemy import exists, false, select, true, union_all
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import col

from app.core.config import settings
from app.core.errors import raise_problem
from app.crud.event_membership import event_membership as crud_membership
from app.crud.voucher import voucher as crud_voucher
from app.logic import clock
from app.logic.work_hours import counts_as_worked, shift_ends_at
from app.models.booking import Booking
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.models.voucher import VoucherEarning, VoucherEntry, VoucherPass
from app.schemas.event_membership import EventRole
from app.schemas.voucher import (
    VoucherAccount,
    VoucherBalance,
    VoucherCheckResult,
    VoucherEntryRead,
    VoucherPassStatus,
    VoucherRedeemResult,
    VoucherShift,
)

#: How long a code lives.
PASS_TTL = dt.timedelta(seconds=120)
#: After a successful check, the pass stays redeemable this long even if it
#: runs out meanwhile, so a slow network between "check" and "redeem" never
#: loses it.
PASS_HOLD = dt.timedelta(seconds=60)
#: No 0 O 1 I L: a code is read off a screen and may be typed in.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 6
#: What the QR code holds in front of the code.
QR_PREFIX = "WV1:"
#: A shift "runs", for redeeming at its task, from this long before its start...
REDEEM_GRACE_BEFORE = dt.timedelta(minutes=30)
#: ...to this long after its end.
REDEEM_GRACE_AFTER = dt.timedelta(minutes=30)


# --- Pure helpers ---------------------------------------------------------


def generate_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(raw: str) -> str | None:
    """A typed or scanned code as stored, or None if it cannot be one.

    Upper-cases, drops the QR prefix, dashes and spaces ("k7m-4qx" works).
    """
    value = raw.strip().upper()
    if value.startswith(QR_PREFIX):
        value = value[len(QR_PREFIX) :]
    value = value.replace("-", "").replace(" ", "")
    if len(value) != CODE_LENGTH or any(c not in CODE_ALPHABET for c in value):
        return None
    return value


def redeem_window(
    date: dt.date, start: dt.time | None, end: dt.time | None
) -> tuple[dt.datetime, dt.datetime]:
    """When someone on this shift may redeem at its task (event wall clock).

    From ``REDEEM_GRACE_BEFORE`` before its start to ``REDEEM_GRACE_AFTER``
    after its end. A shift without times runs all day.
    """
    opens = dt.datetime.combine(date, start or dt.time()) - REDEEM_GRACE_BEFORE
    closes = shift_ends_at(date, start, end) + REDEEM_GRACE_AFTER
    return opens, closes


def redeem_window_dates(now: dt.datetime) -> tuple[dt.date, dt.date]:
    """The shift dates whose :func:`redeem_window` can contain ``now``.

    Yesterday (an overnight shift still running, or one that ended within the
    grace) through tomorrow (a shift at 00:15 opens at 23:45).
    """
    return (
        (now - REDEEM_GRACE_AFTER).date() - dt.timedelta(days=1),
        (now + REDEEM_GRACE_BEFORE).date(),
    )


def in_redeem_window(
    now: dt.datetime, date: dt.date, start: dt.time | None, end: dt.time | None
) -> bool:
    opens, closes = redeem_window(date, start, end)
    return opens <= now <= closes


def pass_redeemable(p: VoucherPass, utc_now: dt.datetime) -> bool:
    """Unused, and either not yet expired or held by a check."""
    if p.used_at is not None:
        return False
    if p.expires_at > utc_now:
        return True
    return p.checked_at is not None and p.checked_at + PASS_HOLD > utc_now


def to_utc(wall: dt.datetime) -> dt.datetime:
    """A wall-clock time in ``EVENT_TIMEZONE`` as naive UTC (stored timestamps)."""
    aware = wall.replace(tzinfo=ZoneInfo(settings.EVENT_TIMEZONE))
    return aware.astimezone(dt.UTC).replace(tzinfo=None)


# --- What someone has ------------------------------------------------------


@dataclass
class _Tally:
    earned: int = 0
    upcoming: int = 0
    redeemed: int = 0
    adjusted: int = 0
    shifts: list[VoucherShift] = field(default_factory=list)

    def add_shift(self, shift: VoucherShift) -> None:
        self.shifts.append(shift)
        if shift.completed:
            self.earned += shift.vouchers
        else:
            self.upcoming += shift.vouchers

    @property
    def balance(self) -> int:
        return self.earned - self.redeemed + self.adjusted

    @property
    def is_zero(self) -> bool:
        return self.earned == 0 and self.redeemed == 0 and self.adjusted == 0

    def summary(self, user: User, role: EventRole | None) -> VoucherBalance:
        return VoucherBalance(
            user_id=user.id,
            name=user.name,
            email=user.email,
            avatar_etag=user.avatar_etag,
            role=role,
            earned=self.earned,
            upcoming=self.upcoming,
            redeemed=self.redeemed,
            adjusted=self.adjusted,
            balance=self.balance,
            available=max(self.balance, 0),
        )


# --- Settling ----------------------------------------------------------------

#: Rows per INSERT when settling: 14 parameters each, well under asyncpg's
#: 32767 parameters per statement.
_SETTLE_CHUNK = 1000


async def settle_earnings(
    session: AsyncSession,
    *,
    now: dt.datetime,
    task_ids: Sequence[uuid.UUID] | None = None,
    shift_ids: Sequence[uuid.UUID] | None = None,
    include_zero: bool = False,
) -> int:
    """Freeze what ended, worked bookings on these tasks or shifts have earned,
    before a change that would alter it. Returns the rows written.

    Called in the route's transaction, before the change, with the ``now``
    (event wall clock) the route uses. Candidates: bookings that
    ``counts_as_worked()``, on a task that belongs to an event, on a shift
    that has ended by ``now``, without an earning row yet; and only tasks
    that earn vouchers, unless ``include_zero``. A rate change passes
    ``include_zero=True``, so that raising a rate from 0 does not pay for
    shifts already over; every other change skips tasks at 0, whose bookings
    earn nothing whatever happens to them.

    Idempotent: ``ON CONFLICT (booking_id) DO NOTHING``, so settling a booking
    twice, or from two requests at once, writes one row. Takes no lock (see
    the module docstring). Never writes for a shift still running.
    """
    if task_ids is None and shift_ids is None:
        msg = "settle_earnings needs task_ids or shift_ids"
        raise TypeError(msg)
    if (task_ids is not None and not task_ids) or (
        shift_ids is not None and not shift_ids
    ):
        return 0

    query = (
        select(
            col(Booking.id),
            col(Booking.user_id),
            col(Task.event_id),
            col(Task.vouchers_per_shift),
            col(Task.id),
            col(Task.name),
            col(Shift.id),
            col(Shift.title),
            col(Shift.date),
            col(Shift.start_time),
            col(Shift.end_time),
        )
        .join(Shift, col(Shift.id) == col(Booking.shift_id))
        .join(Task, col(Task.id) == col(Shift.task_id))
        .where(
            counts_as_worked(),
            col(Task.event_id).is_not(None),
            # A cheap prefilter: an overnight shift dated yesterday ends today,
            # one dated tomorrow cannot have ended. The exact test is below.
            col(Shift.date) <= now.date(),
            ~exists().where(col(VoucherEarning.booking_id) == col(Booking.id)),
        )
    )
    if task_ids is not None:
        query = query.where(col(Task.id).in_(list(task_ids)))
    if shift_ids is not None:
        query = query.where(col(Shift.id).in_(list(shift_ids)))
    if not include_zero:
        query = query.where(col(Task.vouchers_per_shift) > 0)

    stamp = clock.utc_now()
    values: list[dict[str, Any]] = [
        {
            "id": uuid.uuid4(),
            "created_at": stamp,
            "updated_at": stamp,
            "event_id": event_id,
            "user_id": user_id,
            "booking_id": booking_id,
            "amount": per_shift,
            "task_id": task_id,
            "task_name": task_name,
            "shift_id": shift_id,
            "shift_title": title,
            "shift_date": date,
            "shift_start_time": start,
            "shift_end_time": end,
        }
        for (
            booking_id,
            user_id,
            event_id,
            per_shift,
            task_id,
            task_name,
            shift_id,
            title,
            date,
            start,
            end,
        ) in (await session.execute(query)).all()
        if shift_ends_at(date, start, end) <= now
    ]

    written = 0
    for i in range(0, len(values), _SETTLE_CHUNK):
        result = await session.execute(
            pg_insert(VoucherEarning)
            .values(values[i : i + _SETTLE_CHUNK])
            .on_conflict_do_nothing(index_elements=["booking_id"])
            .returning(col(VoucherEarning.id))
        )
        written += len(result.all())
    return written


# --- Earned: settled rows and derived ones -----------------------------------


async def _voucher_shifts(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
    now: dt.datetime,
) -> list[tuple[uuid.UUID, VoucherShift]]:
    """``(booker, shift)`` for every booking that earns vouchers in the event.

    One statement, so one snapshot: the settled rows of the event (those
    worth something, shown from their snapshot and always earned) ``UNION
    ALL`` the bookings not settled yet, derived from the current task and
    shift. A settlement committing meanwhile is counted either as derived or
    as settled, never both and never neither. ``now`` is the event wall
    clock: a derived row whose shift has ended counts as earned, the rest as
    upcoming.

    A settled row's ``shift_id`` / ``task_id`` are None once that shift or
    task is gone, so the client does not link to it.
    """
    live_shift = aliased(Shift, name="live_shift")
    live_task = aliased(Task, name="live_task")
    settled = (
        select(
            col(VoucherEarning.booking_id),
            col(VoucherEarning.user_id),
            col(live_shift.id),
            col(live_task.id),
            col(VoucherEarning.task_name),
            col(VoucherEarning.shift_title),
            col(VoucherEarning.shift_date),
            col(VoucherEarning.shift_start_time),
            col(VoucherEarning.shift_end_time),
            col(VoucherEarning.amount),
            true(),
        )
        .outerjoin(live_shift, col(live_shift.id) == col(VoucherEarning.shift_id))
        .outerjoin(live_task, col(live_task.id) == col(VoucherEarning.task_id))
        .where(
            col(VoucherEarning.event_id) == event_id,
            col(VoucherEarning.amount) > 0,
        )
    )
    derived = (
        select(
            col(Booking.id),
            col(Booking.user_id),
            col(Shift.id),
            col(Task.id),
            col(Task.name),
            col(Shift.title),
            col(Shift.date),
            col(Shift.start_time),
            col(Shift.end_time),
            col(Task.vouchers_per_shift),
            false(),
        )
        .join(Shift, col(Shift.id) == col(Booking.shift_id))
        .join(Task, col(Task.id) == col(Shift.task_id))
        .where(
            col(Task.event_id) == event_id,
            counts_as_worked(),
            col(Task.vouchers_per_shift) > 0,
            ~exists().where(col(VoucherEarning.booking_id) == col(Booking.id)),
        )
    )
    if user_id is not None:
        settled = settled.where(col(VoucherEarning.user_id) == user_id)
        derived = derived.where(col(Booking.user_id) == user_id)
    result = await session.execute(union_all(settled, derived))

    rows: list[tuple[uuid.UUID, VoucherShift]] = []
    for (
        booking_id,
        booker_id,
        shift_id,
        task_id,
        task_name,
        title,
        date,
        start,
        end,
        amount,
        is_settled,
    ) in result.all():
        ends = shift_ends_at(date, start, end)
        rows.append(
            (
                booker_id,
                VoucherShift(
                    booking_id=booking_id,
                    shift_id=shift_id,
                    task_id=task_id,
                    task_name=task_name,
                    title=title,
                    date=date,
                    start_time=start,
                    end_time=end,
                    ends_at=to_utc(ends),
                    vouchers=amount,
                    completed=bool(is_settled) or ends <= now,
                    settled=bool(is_settled),
                ),
            )
        )
    # In shift order, as the rota reads; a shift without a start time last
    # on its day, as Postgres sorts NULLs.
    rows.sort(
        key=lambda r: (
            r[1].date,
            r[1].start_time is None,
            r[1].start_time or dt.time(),
        )
    )
    return rows


async def _tally(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
    now: dt.datetime,
) -> dict[uuid.UUID, _Tally]:
    tallies: dict[uuid.UUID, _Tally] = {}
    for booker_id, shift in await _voucher_shifts(
        session, event_id, user_id=user_id, now=now
    ):
        tallies.setdefault(booker_id, _Tally()).add_shift(shift)
    # A second statement, as before settling existed: the ledger only moves
    # under ``lock_ledger``, which every writer to it holds.
    totals = await crud_voucher.ledger_totals(
        session, event_id=event_id, user_id=user_id
    )
    for uid, (redeemed, adjusted) in totals.items():
        tally = tallies.setdefault(uid, _Tally())
        tally.redeemed = redeemed
        tally.adjusted = adjusted
    return tallies


async def available_for(
    session: AsyncSession,
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    now: dt.datetime,
) -> int:
    """What this person can redeem in the event right now (never below 0)."""
    tally = (await _tally(session, event_id, user_id=user_id, now=now)).get(user_id)
    return max(tally.balance, 0) if tally else 0


async def account(
    session: AsyncSession,
    event_id: uuid.UUID,
    user: User,
    *,
    now: dt.datetime,
) -> VoucherAccount:
    """One person's vouchers in the event, with the shifts and entries behind them."""
    tally = (await _tally(session, event_id, user_id=user.id, now=now)).get(
        user.id, _Tally()
    )
    role = await crud_membership.get_role(session, user_id=user.id, event_id=event_id)
    entries = await crud_voucher.list_for_user(
        session, event_id=event_id, user_id=user.id
    )
    return VoucherAccount(
        summary=tally.summary(user, role),
        shifts=tally.shifts,
        entries=[VoucherEntryRead.model_validate(e) for e in entries],
    )


async def balances(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    now: dt.datetime,
) -> list[VoucherBalance]:
    """Everyone in the event, plus former members whose numbers are not all zero.

    Sorted by what they can redeem, most first, then by name: the top of the
    list is where an organiser looks for anything unusual.
    """
    tallies = await _tally(session, event_id, now=now)

    out: list[VoucherBalance] = []
    seen: set[uuid.UUID] = set()
    for membership, user in await crud_membership.list_members(
        session, event_id=event_id
    ):
        seen.add(user.id)
        out.append(
            tallies.get(user.id, _Tally()).summary(user, membership.role)  # type: ignore[arg-type]
        )

    former_ids = [
        uid for uid, tally in tallies.items() if uid not in seen and not tally.is_zero
    ]
    if former_ids:
        result = await session.execute(select(User).where(col(User.id).in_(former_ids)))
        for user in result.scalars().all():
            out.append(tallies[user.id].summary(user, None))

    out.sort(key=lambda b: (-b.available, (b.name or b.email or "").lower()))
    return out


# --- Codes -----------------------------------------------------------------


async def issue_pass(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    now: dt.datetime,
) -> VoucherPass:
    """A fresh code for the volunteer; their old unused, unheld one stops working."""
    return await crud_voucher.issue_pass(
        session,
        event_id=event_id,
        user_id=user_id,
        now=now,
        ttl=PASS_TTL,
        hold=PASS_HOLD,
        new_code=generate_code,
    )


async def pass_status(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    pass_id: uuid.UUID,
    utc_now: dt.datetime,
    wall_now: dt.datetime,
) -> VoucherPassStatus:
    """What has happened to one of the caller's codes; 404 if it is gone."""
    p = await crud_voucher.get_pass_for_user(
        session, pass_id=pass_id, event_id=event_id, user_id=user_id
    )
    if p is None:
        raise_problem(
            404, code="voucher.pass_not_found", detail="This code no longer exists"
        )
    available = await available_for(session, event_id, user_id, now=wall_now)
    if p.used_at is not None:
        entry = await crud_voucher.entry_for_pass(session, pass_id=p.id)
        return VoucherPassStatus(
            status="used",
            redeemed_amount=-entry.amount if entry else None,
            task_name=entry.task_name if entry else None,
            available=available,
        )
    if not pass_redeemable(p, utc_now):
        return VoucherPassStatus(status="expired", available=available)
    if p.checked_at is not None:
        return VoucherPassStatus(status="checking", available=available)
    return VoucherPassStatus(status="active", available=available)


# --- Checking and redeeming --------------------------------------------------


async def _pass_for_code(
    session: AsyncSession, *, event_id: uuid.UUID, code: str
) -> VoucherPass:
    normalized = normalize_code(code)
    p = (
        await crud_voucher.find_pass_by_code(session, code=normalized)
        if normalized
        else None
    )
    if p is None:
        raise_problem(404, code="voucher.code_invalid", detail="This code is not valid")
    if p.event_id != event_id:
        raise_problem(
            409,
            code="voucher.code_other_event",
            detail="This code was issued for a different event",
        )
    return p


async def _member_or_404(
    session: AsyncSession, *, event_id: uuid.UUID, user_id: uuid.UUID
) -> User:
    if await crud_membership.get(session, user_id=user_id, event_id=event_id) is None:
        raise_problem(
            404,
            code="event.member_not_found",
            detail="That person is not a member of this event",
        )
    user = await session.get(User, user_id)
    assert user is not None  # a membership row implies the user
    return user


async def _raise_if_unusable(
    session: AsyncSession, p: VoucherPass, *, utc_now: dt.datetime
) -> None:
    """409 for a used or expired pass. A used one says where and by whom."""
    if p.used_at is not None:
        entry = await crud_voucher.entry_for_pass(session, pass_id=p.id)
        _raise_code_used(entry, used_at=p.used_at)
    if not pass_redeemable(p, utc_now):
        raise_problem(409, code="voucher.code_expired", detail="This code has expired")


def _raise_code_used(
    entry: VoucherEntry | None, *, used_at: dt.datetime | None
) -> NoReturn:
    extensions: dict[str, object] = {
        "amount": -entry.amount if entry else None,
        "task_name": entry.task_name if entry else None,
        "actor_name": entry.actor_name if entry else None,
        "used_at": used_at.isoformat() if used_at else None,
    }
    raise_problem(
        409,
        code="voucher.code_used",
        detail="This code has already been used",
        extensions=extensions,
    )


async def check(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    code: str | None,
    user_id: uuid.UUID | None,
    wall_now: dt.datetime,
    utc_now: dt.datetime,
) -> VoucherCheckResult:
    """Who is in front of the redeemer, and how many they can redeem.

    Writes nothing to the ledger. A code is *held* (``checked_at``), which
    keeps it redeemable for ``PASS_HOLD`` while the redeemer picks an amount.
    Only an unexpired code takes a new hold: checking an expired one inside
    its hold answers as before but does not extend it, so re-checking cannot
    keep a code alive.
    """
    p: VoucherPass | None = None
    if code is not None:
        p = await _pass_for_code(session, event_id=event_id, code=code)
        volunteer_id = p.user_id
    else:
        assert user_id is not None  # the schema requires one of the two
        volunteer_id = user_id
    volunteer = await _member_or_404(session, event_id=event_id, user_id=volunteer_id)
    if p is not None:
        await _raise_if_unusable(session, p, utc_now=utc_now)
        await crud_voucher.hold_pass(session, pass_id=p.id, now=utc_now)
    return VoucherCheckResult(
        user_id=volunteer.id,
        name=volunteer.name,
        avatar_etag=volunteer.avatar_etag,
        available=await available_for(session, event_id, volunteer.id, now=wall_now),
    )


async def _replayed(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    redeemer: User,
    request_id: uuid.UUID,
    wall_now: dt.datetime,
) -> VoucherRedeemResult | None:
    """The earlier result for this ``request_id``, or None if there is none.

    409 ``voucher.request_conflict`` if the id belongs to another redeemer or
    event: a client-generated key must never let one person read another's
    redemption.
    """
    earlier = await crud_voucher.find_entry_by_request_id(
        session, request_id=request_id
    )
    if earlier is None:
        return None
    if earlier.event_id != event_id or earlier.actor_id != redeemer.id:
        raise_problem(
            409,
            code="voucher.request_conflict",
            detail="This request id belongs to a different redemption",
        )
    volunteer = await session.get(User, earlier.user_id)
    return VoucherRedeemResult(
        entry=VoucherEntryRead.model_validate(earlier),
        user_id=earlier.user_id,
        name=volunteer.name if volunteer else None,
        available=await available_for(session, event_id, earlier.user_id, now=wall_now),
        replayed=True,
    )


async def redeem(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    task: Task,
    redeemer: User,
    code: str | None,
    user_id: uuid.UUID | None,
    amount: int,
    request_id: uuid.UUID,
    wall_now: dt.datetime,
    utc_now: dt.datetime,
) -> VoucherRedeemResult:
    """Take ``amount`` vouchers from the volunteer at the point ``task``.

    The caller has already checked that the task is a point in this event and
    that ``redeemer`` may redeem there (manually, if ``user_id`` is given).
    Nothing is written before the last check passes, so a refusal does not
    rely on a rollback.
    """
    # Who: the pass's owner, or the person picked from the list.
    p: VoucherPass | None = None
    if code is not None:
        p = await _pass_for_code(session, event_id=event_id, code=code)
        volunteer_id = p.user_id
    else:
        assert user_id is not None  # the schema requires one of the two
        volunteer_id = user_id
    volunteer = await _member_or_404(session, event_id=event_id, user_id=volunteer_id)

    # From here until commit, nobody else changes this balance.
    await crud_voucher.lock_ledger(session, event_id=event_id, user_id=volunteer.id)

    replay = await _replayed(
        session,
        event_id=event_id,
        redeemer=redeemer,
        request_id=request_id,
        wall_now=wall_now,
    )
    if replay is not None:
        return replay

    if p is not None:
        # Read again under the lock: the first read is in the identity map
        # from before it, and the pass may since have been used, or replaced
        # by a new code on the volunteer's screen.
        fresh = await crud_voucher.reload_pass(session, pass_id=p.id)
        if fresh is None:
            raise_problem(
                404, code="voucher.code_invalid", detail="This code is not valid"
            )
        p = fresh
        await _raise_if_unusable(session, p, utc_now=utc_now)

    available = await available_for(session, event_id, volunteer.id, now=wall_now)
    if amount > available:
        raise_problem(
            409,
            code="voucher.insufficient",
            detail=f"Only {available} available",
            extensions={"available": available},
        )

    if p is not None and not await crud_voucher.consume_pass(
        session, pass_id=p.id, now=utc_now, hold=PASS_HOLD
    ):
        # A backstop: the lock above already serialises redemptions, so this
        # only happens when the hold ran out in the last few milliseconds.
        gone = await crud_voucher.reload_pass(session, pass_id=p.id)
        if gone is not None:
            await _raise_if_unusable(session, gone, utc_now=utc_now)
        _raise_code_used(None, used_at=None)

    entry = VoucherEntry(
        event_id=event_id,
        user_id=volunteer.id,
        kind="redemption",
        amount=-amount,
        method="code" if p is not None else "manual",
        task_id=task.id,
        task_name=task.name,
        actor_id=redeemer.id,
        actor_name=redeemer.name or redeemer.email,
        pass_id=p.id if p is not None else None,
        request_id=request_id,
        created_at=utc_now,
        updated_at=utc_now,
    )
    try:
        async with session.begin_nested():
            session.add(entry)
            await session.flush()
    except IntegrityError as exc:
        # Last backstops; the lock makes both unreachable in practice.
        if "request_id" in str(exc.orig):
            replay = await _replayed(
                session,
                event_id=event_id,
                redeemer=redeemer,
                request_id=request_id,
                wall_now=wall_now,
            )
            if replay is not None:
                return replay
        _raise_code_used(None, used_at=None)

    return VoucherRedeemResult(
        entry=VoucherEntryRead.model_validate(entry),
        user_id=volunteer.id,
        name=volunteer.name,
        available=available - amount,
    )
