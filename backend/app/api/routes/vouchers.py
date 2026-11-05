"""Volunteer vouchers: balances, codes, redemptions and corrections.

Every route starts with the event's visibility check, as ``work_hours`` does,
so a sandbox demo stays a 404 even for the superadmin; ``require_event_role``
alone would let them through. Literal sub-paths (``me``, ``people/{user_id}``)
keep any ``{user_id}`` route from swallowing ``me``.

What the numbers mean and how a redemption is serialised: ``app.logic.vouchers``.
Who may redeem where: ``app.logic.permissions.require_voucher_redeemer``.
"""

import datetime as dt
import uuid
from typing import NoReturn

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.core.rate_limit import voucher_code_limiter, voucher_pass_limiter
from app.crud.booking import booking as crud_booking
from app.crud.event import event as crud_event
from app.crud.event_membership import event_membership as crud_membership
from app.crud.task_manager import task_manager as crud_task_manager
from app.crud.user import user as crud_user
from app.crud.voucher import voucher as crud_voucher
from app.logic import clock, vouchers
from app.logic.permissions import (
    may_redeem_manually,
    on_shift_task_ids,
    require_event_role,
    require_event_visible,
    require_voucher_redeemer,
    role_at_least,
)
from app.models.event import Event
from app.models.task import Task
from app.models.user import User
from app.models.voucher import VoucherEntry
from app.schemas.task_manager import TaskManagerBrief
from app.schemas.voucher import (
    PointPersonVouchers,
    PointRedemptionList,
    PointRedemptionRead,
    VoucherAccount,
    VoucherAdjustmentCreate,
    VoucherAdjustmentUpdate,
    VoucherBalance,
    VoucherCheckRequest,
    VoucherCheckResult,
    VoucherEntryRead,
    VoucherPassRead,
    VoucherPassStatus,
    VoucherPointRead,
    VoucherRedeemRequest,
    VoucherRedeemResult,
)

router = APIRouter(prefix="/events", tags=["vouchers"])


async def _event_for(session: AsyncSession, user: User, event_id: uuid.UUID) -> Event:
    # Visibility first: it 404s a sandbox demo for everyone but its guest,
    # which require_event_role alone would let the superadmin through.
    event = await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_visible(user, session, event)
    return event


async def _point_in_event(
    session: AsyncSession, *, event_id: uuid.UUID, task_id: uuid.UUID
) -> Task:
    task = await session.get(Task, task_id)
    if task is None or task.event_id != event_id:
        raise_problem(404, code="task.not_found", detail="No such task in this event")
    return task


def _require_point(task: Task) -> None:
    """The task takes vouchers. An archived one has left the list of points, so
    it has stopped taking them too."""
    if not task.is_voucher_point:
        raise_problem(
            422,
            code="voucher.not_a_point",
            detail="Vouchers cannot be redeemed at this task",
        )
    if task.status == "archived":
        raise_problem(
            409,
            code="voucher.point_archived",
            detail="This task is archived, so it no longer takes vouchers",
        )


# --- The volunteer's own ----------------------------------------------------


@router.get("/{event_id}/vouchers/me", response_model=VoucherAccount)
async def get_my_vouchers(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> VoucherAccount:
    """The caller's vouchers in the event, with the shifts and entries behind them."""
    event = await _event_for(session, current_user, event_id)
    await require_event_role(current_user, session, event_id, minimum="member")
    return await vouchers.account(
        session, event_id, current_user, now=clock.wall_clock_now(event.timezone)
    )


@router.post(
    "/{event_id}/vouchers/me/pass", response_model=VoucherPassRead, status_code=201
)
async def issue_my_pass(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> VoucherPassRead:
    """A fresh code to show at a stand. The caller's previous unused code stops
    working, unless a redeemer is holding it right now."""
    event = await _event_for(session, current_user, event_id)
    await require_event_role(current_user, session, event_id, minimum="member")
    await voucher_pass_limiter.check(str(current_user.id))
    p = await vouchers.issue_pass(
        session, event_id=event_id, user_id=current_user.id, now=clock.utc_now()
    )
    return VoucherPassRead(
        id=p.id,
        code=p.code,
        qr_payload=f"{vouchers.QR_PREFIX}{p.code}",
        expires_at=p.expires_at,
        ttl_seconds=int(vouchers.PASS_TTL.total_seconds()),
        event_name=event.name,
    )


@router.get("/{event_id}/vouchers/me/pass/{pass_id}", response_model=VoucherPassStatus)
async def get_my_pass_status(
    event_id: uuid.UUID,
    pass_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> VoucherPassStatus:
    """What happened to one of the caller's codes: still showing, being
    redeemed, used, or expired. 404 once it was replaced or is not theirs."""
    event = await _event_for(session, current_user, event_id)
    await require_event_role(current_user, session, event_id, minimum="member")
    return await vouchers.pass_status(
        session,
        event_id=event_id,
        user_id=current_user.id,
        pass_id=pass_id,
        utc_now=clock.utc_now(),
        wall_now=clock.wall_clock_now(event.timezone),
    )


# --- Redemption points -------------------------------------------------------


@router.get("/{event_id}/vouchers/points", response_model=list[VoucherPointRead])
async def list_voucher_points(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> list[VoucherPointRead]:
    """The event's tasks that take vouchers, and whether the caller may redeem
    at each right now. Published ones, plus drafts the caller can manage."""
    event = await _event_for(session, current_user, event_id)
    role = await require_event_role(current_user, session, event_id, minimum="member")
    is_admin = role_at_least(role, "admin")
    in_charge = set(
        await crud_task_manager.task_ids_for_user(session, user_id=current_user.id)
    )

    result = await session.execute(
        select(Task)
        .where(col(Task.event_id) == event_id, col(Task.is_voucher_point).is_(True))
        .order_by(col(Task.name))
    )
    points = [
        t
        for t in result.scalars().all()
        if t.status == "published"
        or (t.status == "draft" and (is_admin or t.id in in_charge))
    ]
    if not points:
        return []

    managers = await crud_task_manager.managers_for_tasks(
        session, task_ids=(t.id for t in points)
    )
    on_shift = await on_shift_task_ids(
        current_user,
        session,
        [t.id for t in points if not is_admin and t.id not in in_charge],
        now=clock.wall_clock_now(event.timezone),
    )
    out: list[VoucherPointRead] = []
    for t in points:
        kind = (
            "admin"
            if is_admin
            else "manager"
            if t.id in in_charge
            else "on_shift"
            if t.id in on_shift
            else None
        )
        out.append(
            VoucherPointRead(
                task_id=t.id,
                name=t.name,
                location=t.location,
                can_redeem=kind is not None,
                can_redeem_manually=kind is not None
                and may_redeem_manually(kind, event),
                managers=[
                    TaskManagerBrief(
                        user_id=u.id, name=u.name, avatar_etag=u.avatar_etag
                    )
                    for _, u in managers.get(t.id, [])
                ],
            )
        )
    return out


@router.get(
    "/{event_id}/vouchers/points/{task_id}/entries",
    response_model=PointRedemptionList,
)
async def list_point_redemptions(
    event_id: uuid.UUID,
    task_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
) -> PointRedemptionList:
    """Redemptions made at one point, newest first, and the totals there:
    today's and over every day.

    Event admins and its people in charge see every one; someone redeeming
    because they are on shift there sees the ones they made, and their own
    totals. "Today" is the event wall-clock day. Both totals count every
    entry rather than the ``limit`` on screen.
    """
    event = await _event_for(session, current_user, event_id)
    task = await _point_in_event(session, event_id=event_id, task_id=task_id)
    wall_now = clock.wall_clock_now(event.timezone)
    kind = await require_voucher_redeemer(
        current_user, session, task, event=event, now=wall_now
    )
    _require_point(task)
    actor_id = current_user.id if kind == "on_shift" else None
    rows = await crud_voucher.list_for_point(
        session,
        event_id=event_id,
        task_id=task.id,
        actor_id=actor_id,
        limit=limit,
    )
    items = [
        PointRedemptionRead(
            **VoucherEntryRead.model_validate(entry).model_dump(),
            user_id=entry.user_id,
            user_name=(user.name or user.email) if user else None,
        )
        for entry, user in rows
    ]
    totals = await crud_voucher.point_totals(
        session,
        event_id=event_id,
        task_id=task.id,
        actor_id=actor_id,
        today_since=clock.wall_clock_to_utc(
            dt.datetime.combine(wall_now.date(), dt.time()), event.timezone
        ),
    )
    return PointRedemptionList(items=items, **totals._asdict())


@router.get(
    "/{event_id}/vouchers/points/{task_id}/people",
    response_model=list[PointPersonVouchers],
)
async def list_point_people(
    event_id: uuid.UUID,
    task_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> list[PointPersonVouchers]:
    """What each member of the event can redeem now, for picking the person
    at one point without a code.

    For whoever may redeem manually there (``require_voucher_redeemer`` with
    ``manual``: 403 ``voucher.not_allowed`` or ``voucher.manual_not_allowed``
    otherwise), so the people in charge and the staff on shift see the same
    numbers as the organisers. Current members of this event only, and only
    their id and what they can redeem: the picker has the rest from the
    member list, and a redemption checks the balance again under its lock.
    """
    event = await _event_for(session, current_user, event_id)
    task = await _point_in_event(session, event_id=event_id, task_id=task_id)
    wall_now = clock.wall_clock_now(event.timezone)
    await require_voucher_redeemer(
        current_user, session, task, event=event, now=wall_now, manual=True
    )
    _require_point(task)
    available = await vouchers.available_for_members(session, event_id, now=wall_now)
    return [
        PointPersonVouchers(user_id=user_id, available=n)
        for user_id, n in available.items()
    ]


@router.post("/{event_id}/vouchers/check", response_model=VoucherCheckResult)
async def check_voucher(
    event_id: uuid.UUID,
    body: VoucherCheckRequest,
    session: DBDep,
    current_user: CurrentUser,
) -> VoucherCheckResult:
    """Who is in front of the redeemer and how many they can redeem.

    Takes nothing. A code is held for a minute, so it still redeems if it runs
    out while the amount is chosen.
    """
    event = await _event_for(session, current_user, event_id)
    task = await _point_in_event(session, event_id=event_id, task_id=body.task_id)
    await require_voucher_redeemer(
        current_user,
        session,
        task,
        event=event,
        now=clock.wall_clock_now(event.timezone),
        manual=body.user_id is not None,
    )
    _require_point(task)
    if body.code is not None:
        await voucher_code_limiter.check(str(current_user.id))
    return await vouchers.check(
        session,
        event_id=event_id,
        code=body.code,
        user_id=body.user_id,
        wall_now=clock.wall_clock_now(event.timezone),
        utc_now=clock.utc_now(),
    )


@router.post(
    "/{event_id}/vouchers/redeem", response_model=VoucherRedeemResult, status_code=201
)
async def redeem_vouchers(
    event_id: uuid.UUID,
    body: VoucherRedeemRequest,
    session: DBDep,
    current_user: CurrentUser,
) -> VoucherRedeemResult:
    """Take vouchers from a volunteer at a point.

    A retry with the same ``request_id`` returns the first result
    (``replayed``) instead of taking them twice.
    """
    event = await _event_for(session, current_user, event_id)
    task = await _point_in_event(session, event_id=event_id, task_id=body.task_id)
    await require_voucher_redeemer(
        current_user,
        session,
        task,
        event=event,
        now=clock.wall_clock_now(event.timezone),
        manual=body.user_id is not None,
    )
    _require_point(task)
    if body.code is not None:
        await voucher_code_limiter.check(str(current_user.id))
    return await vouchers.redeem(
        session,
        event_id=event_id,
        task=task,
        redeemer=current_user,
        code=body.code,
        user_id=body.user_id,
        amount=body.amount,
        request_id=body.request_id,
        wall_now=clock.wall_clock_now(event.timezone),
        utc_now=clock.utc_now(),
    )


# --- The organisers' overview -----------------------------------------------


@router.get("/{event_id}/vouchers/people", response_model=list[VoucherBalance])
async def list_voucher_balances(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> list[VoucherBalance]:
    """Everyone's vouchers, most available first. Event admins only."""
    event = await _event_for(session, current_user, event_id)
    await require_event_role(current_user, session, event_id, minimum="admin")
    return await vouchers.balances(
        session, event_id, now=clock.wall_clock_now(event.timezone)
    )


@router.get("/{event_id}/vouchers/people/{user_id}", response_model=VoucherAccount)
async def get_voucher_account(
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> VoucherAccount:
    """One person's vouchers. Anyone in the event may read their own; reading
    someone else's needs admin, and that someone must have a part in the event
    (the rule corrections use): anyone can create an event and so be its
    admin, and the account carries a name and e-mail address."""
    event = await _event_for(session, current_user, event_id)
    is_self = user_id == current_user.id
    await require_event_role(
        current_user, session, event_id, minimum="member" if is_self else "admin"
    )
    if is_self:
        user = current_user
    else:
        if not await _appears_in_event(session, event_id=event_id, user_id=user_id):
            _no_part_in_event()
        user = await crud_user.get(session, id=user_id, raise_404_error=True)
    return await vouchers.account(
        session, event_id, user, now=clock.wall_clock_now(event.timezone)
    )


@router.post(
    "/{event_id}/vouchers/adjustments",
    response_model=VoucherEntryRead,
    status_code=201,
)
async def create_voucher_adjustment(
    event_id: uuid.UUID,
    body: VoucherAdjustmentCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> VoucherEntry:
    """Add or take away vouchers by hand, with a reason. Event admins only.

    For a current member, or for someone who has left but still has entries,
    settled earnings or bookings in the event, so an organiser can settle a
    former member's balance.
    Taking away more than the person can still redeem is refused with 409
    ``voucher.correction_exceeds_available``: a balance never goes below zero.
    """
    await _event_for(session, current_user, event_id)
    await require_event_role(current_user, session, event_id, minimum="admin")
    if not await _appears_in_event(session, event_id=event_id, user_id=body.user_id):
        _no_part_in_event()
    # The same lock as a redemption: a correction in the middle of one would
    # otherwise change the balance it is checking against.
    await crud_voucher.lock_ledger(session, event_id=event_id, user_id=body.user_id)
    await _refuse_below_zero(
        session, event_id=event_id, user_id=body.user_id, change=body.amount
    )
    now = clock.utc_now()
    entry = VoucherEntry(
        event_id=event_id,
        user_id=body.user_id,
        kind="adjustment",
        amount=body.amount,
        note=body.note,
        actor_id=current_user.id,
        actor_name=current_user.name or current_user.email,
        created_at=now,
        updated_at=now,
    )
    session.add(entry)
    await session.flush()
    await session.refresh(entry)
    return entry


@router.patch(
    "/{event_id}/vouchers/adjustments/{entry_id}", response_model=VoucherEntryRead
)
async def update_voucher_adjustment(
    event_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: VoucherAdjustmentUpdate,
    session: DBDep,
    current_user: CurrentUser,
) -> VoucherEntry:
    """Change a correction. Redemptions cannot be changed. Event admins only.

    A new amount that would take the person below zero is refused with 409
    ``voucher.correction_exceeds_available``.
    """
    await _event_for(session, current_user, event_id)
    await require_event_role(current_user, session, event_id, minimum="admin")
    entry = await _locked_adjustment(session, event_id=event_id, entry_id=entry_id)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if "amount" in data:
        await _refuse_below_zero(
            session,
            event_id=event_id,
            user_id=entry.user_id,
            change=data["amount"] - entry.amount,
        )
    for key, value in data.items():
        setattr(entry, key, value)
    entry.updated_at = clock.utc_now()
    session.add(entry)
    await session.flush()
    await session.refresh(entry)
    return entry


@router.delete("/{event_id}/vouchers/adjustments/{entry_id}", status_code=204)
async def delete_voucher_adjustment(
    event_id: uuid.UUID,
    entry_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Delete a correction. Redemptions cannot be deleted. Event admins only.

    Deleting a correction that added more than the person can still redeem is
    refused with 409 ``voucher.correction_exceeds_available``: those vouchers
    are already spent.
    """
    await _event_for(session, current_user, event_id)
    await require_event_role(current_user, session, event_id, minimum="admin")
    entry = await _locked_adjustment(session, event_id=event_id, entry_id=entry_id)
    await _refuse_below_zero(
        session, event_id=event_id, user_id=entry.user_id, change=-entry.amount
    )
    await session.delete(entry)
    await session.flush()


async def _refuse_below_zero(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    change: int,
) -> None:
    """409 ``voucher.correction_exceeds_available`` when ``change`` (what the
    correction does to the balance, signed) would take away more than the
    person can still redeem. Call it under ``lock_ledger``.

    Adding is always allowed, also to a balance left below zero by rows
    written under the old rules.
    """
    if change >= 0:
        return
    available = await vouchers.available_for(
        session,
        event_id,
        user_id,
        now=clock.wall_clock_now(await crud_event.zone_of(session, event_id)),
    )
    if -change > available:
        raise_problem(
            409,
            code="voucher.correction_exceeds_available",
            detail=f"That would take away more than the {available} still available",
            extensions={"available": available},
        )


async def _locked_adjustment(
    session: AsyncSession, *, event_id: uuid.UUID, entry_id: uuid.UUID
) -> VoucherEntry:
    """The correction, read again under its person's ``lock_ledger``.

    The lock's key needs the entry's ``user_id``, so the entry is read once
    before it. Another organiser may change or delete the same correction
    while this request waits for the lock, and the session would keep the
    amount it read first; checking a change against that stale amount could
    take the balance below zero. The second read takes what is committed
    (a 404 if it is gone). ``user_id`` itself never changes, so the lock
    still fits.
    """
    entry = await _adjustment_or_error(session, event_id=event_id, entry_id=entry_id)
    await crud_voucher.lock_ledger(session, event_id=event_id, user_id=entry.user_id)
    return await _adjustment_or_error(
        session, event_id=event_id, entry_id=entry_id, fresh=True
    )


async def _adjustment_or_error(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    entry_id: uuid.UUID,
    fresh: bool = False,
) -> VoucherEntry:
    entry = await crud_voucher.get_in_event(
        session, entry_id=entry_id, event_id=event_id, fresh=fresh
    )
    if entry is None:
        raise_problem(
            404, code="voucher.entry_not_found", detail="Voucher entry not found"
        )
    if entry.kind != "adjustment":
        raise_problem(
            409,
            code="voucher.entry_not_editable",
            detail="A redemption cannot be changed; add a correction instead",
        )
    return entry


def _no_part_in_event() -> NoReturn:
    raise_problem(
        404,
        code="event.member_not_found",
        detail="That person has no part in this event",
    )


async def _appears_in_event(
    session: AsyncSession, *, event_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """A current member, or someone with entries, settled earnings or confirmed
    bookings here.

    Covers everyone ``vouchers.balances`` lists as a former member, so an
    organiser can open and correct every row of the overview. Settled earnings
    count on their own: deleting an ended shift or its task cancels the
    booking behind the earning, and moving the task to another event takes
    the booking with it.
    """
    if await crud_membership.get(session, user_id=user_id, event_id=event_id):
        return True
    if await crud_voucher.has_entries(session, event_id=event_id, user_id=user_id):
        return True
    if await crud_voucher.has_earnings(session, event_id=event_id, user_id=user_id):
        return True
    return (
        await crud_booking.count_by_user(
            session, user_id=user_id, status="confirmed", event_id=event_id
        )
        > 0
    )
