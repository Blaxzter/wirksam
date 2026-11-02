"""The stored half of voucher balances, and the codes that spend them.

Never commits; the request owns the transaction. Who may call what is decided
in the routes (``app.logic.permissions``), and the rules (how long a code
lives, how long a check holds it) come from ``app.logic.vouchers``, which
passes them in: this module only knows the rows.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from typing import Any, cast

from sqlalchemy import CursorResult, and_, delete, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.user import User
from app.models.voucher import VoucherEarning, VoucherEntry, VoucherPass

#: How many fresh codes ``issue_pass`` tries before giving up. With 31^6
#: codes and a few dozen live ones, a second attempt is already rare.
_ISSUE_ATTEMPTS = 5


class CRUDVoucher:
    # --- The ledger -------------------------------------------------------

    async def ledger_totals(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> dict[uuid.UUID, tuple[int, int]]:
        """``{user_id: (redeemed, adjusted)}``; ``redeemed`` as a positive number."""
        query = (
            select(
                col(VoucherEntry.user_id),
                col(VoucherEntry.kind),
                func.sum(col(VoucherEntry.amount)),
            )
            .where(col(VoucherEntry.event_id) == event_id)
            .group_by(col(VoucherEntry.user_id), col(VoucherEntry.kind))
        )
        if user_id is not None:
            query = query.where(col(VoucherEntry.user_id) == user_id)
        out: dict[uuid.UUID, tuple[int, int]] = {}
        for uid, kind, total in (await session.execute(query)).all():
            redeemed, adjusted = out.get(uid, (0, 0))
            if kind == "redemption":
                redeemed -= int(total or 0)
            else:
                adjusted += int(total or 0)
            out[uid] = (redeemed, adjusted)
        return out

    async def list_for_user(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[VoucherEntry]:
        """One person's entries in the event, newest first."""
        result = await session.execute(
            select(VoucherEntry)
            .where(
                col(VoucherEntry.event_id) == event_id,
                col(VoucherEntry.user_id) == user_id,
            )
            .order_by(col(VoucherEntry.created_at).desc())
        )
        return list(result.scalars().all())

    async def list_for_point(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        task_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[tuple[VoucherEntry, User | None]]:
        """Redemptions made at one point, newest first, with whose they were.

        Filtered on the event *and* the task, so a task id from another event
        finds nothing. ``actor_id`` narrows it to one redeemer's own.
        """
        query = (
            select(VoucherEntry, User)
            .outerjoin(User, col(User.id) == col(VoucherEntry.user_id))
            .where(
                col(VoucherEntry.event_id) == event_id,
                col(VoucherEntry.task_id) == task_id,
                col(VoucherEntry.kind) == "redemption",
            )
            .order_by(col(VoucherEntry.created_at).desc())
            .limit(limit)
        )
        if actor_id is not None:
            query = query.where(col(VoucherEntry.actor_id) == actor_id)
        return [(e, u) for e, u in (await session.execute(query)).all()]

    async def point_totals_since(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        task_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        since: dt.datetime,
    ) -> tuple[int, int]:
        """``(redemptions, vouchers)`` made at one point from ``since`` on.

        The same rows as :meth:`list_for_point`, counted in the database, so
        the total is not limited to the page on screen. ``since`` is naive
        UTC, like ``created_at``; vouchers come back as a positive number.
        """
        query = select(
            func.count(),
            func.coalesce(func.sum(col(VoucherEntry.amount)), 0),
        ).where(
            col(VoucherEntry.event_id) == event_id,
            col(VoucherEntry.task_id) == task_id,
            col(VoucherEntry.kind) == "redemption",
            col(VoucherEntry.created_at) >= since,
        )
        if actor_id is not None:
            query = query.where(col(VoucherEntry.actor_id) == actor_id)
        count, total = (await session.execute(query)).one()
        return int(count), -int(total)

    async def get_in_event(
        self,
        session: AsyncSession,
        *,
        entry_id: uuid.UUID,
        event_id: uuid.UUID,
        fresh: bool = False,
    ) -> VoucherEntry | None:
        """One entry of the event. ``fresh`` overwrites a copy the session
        already holds with what is committed now, for a read again under
        :meth:`lock_ledger`."""
        query = select(VoucherEntry).where(
            col(VoucherEntry.id) == entry_id,
            col(VoucherEntry.event_id) == event_id,
        )
        if fresh:
            query = query.execution_options(populate_existing=True)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def find_entry_by_request_id(
        self,
        session: AsyncSession,
        *,
        request_id: uuid.UUID,
    ) -> VoucherEntry | None:
        result = await session.execute(
            select(VoucherEntry)
            .where(col(VoucherEntry.request_id) == request_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def entry_for_pass(
        self,
        session: AsyncSession,
        *,
        pass_id: uuid.UUID,
    ) -> VoucherEntry | None:
        result = await session.execute(
            select(VoucherEntry).where(col(VoucherEntry.pass_id) == pass_id)
        )
        return result.scalar_one_or_none()

    async def has_entries(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Whether this person has any ledger row in the event."""
        result = await session.execute(
            select(col(VoucherEntry.id))
            .where(
                col(VoucherEntry.event_id) == event_id,
                col(VoucherEntry.user_id) == user_id,
            )
            .limit(1)
        )
        return result.first() is not None

    async def has_earnings(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Whether this person has a settled earning worth something in the
        event: the rows ``logic.vouchers`` counts as earned."""
        result = await session.execute(
            select(col(VoucherEarning.id))
            .where(
                col(VoucherEarning.event_id) == event_id,
                col(VoucherEarning.user_id) == user_id,
                col(VoucherEarning.amount) > 0,
            )
            .limit(1)
        )
        return result.first() is not None

    async def lock_ledger(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Serialise every write to one volunteer's balance in one event.

        A transaction-scoped advisory lock: the balance is derived, so there is
        no row to lock ``FOR UPDATE``, and locking the user row would also block
        every insert that takes a key-share lock on it (bookings,
        notifications). Released at commit or rollback, so it cannot leak. Under
        READ COMMITTED every statement after it sees what the previous holder
        committed. A hash collision only serialises two unrelated volunteers.
        """
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"vouchers:{event_id}:{user_id}"},
        )

    # --- Passes -----------------------------------------------------------

    async def issue_pass(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
        now: dt.datetime,
        ttl: dt.timedelta,
        hold: dt.timedelta,
        new_code: Callable[[], str],
    ) -> VoucherPass:
        """Insert a fresh pass and delete the user's other unused, unheld ones.

        The code is unique across the installation; a collision retries with
        a new one. A pass a redeemer is holding right now (checked within
        ``hold``) survives, so a slow network between "check" and "redeem"
        never loses it. Used passes stay, so their status can still say
        "redeemed".
        """
        issued: VoucherPass | None = None
        for _ in range(_ISSUE_ATTEMPTS):
            candidate = VoucherPass(
                event_id=event_id,
                user_id=user_id,
                code=new_code(),
                expires_at=now + ttl,
            )
            try:
                async with session.begin_nested():
                    session.add(candidate)
                    await session.flush()
            except IntegrityError as exc:
                if "uq_voucher_passes_code" not in str(exc.orig):
                    raise
                continue
            issued = candidate
            break
        if issued is None:  # pragma: no cover - 887 million codes, five tries
            msg = "Could not find a free voucher code"
            raise RuntimeError(msg)

        await session.execute(
            delete(VoucherPass).where(
                col(VoucherPass.event_id) == event_id,
                col(VoucherPass.user_id) == user_id,
                col(VoucherPass.id) != issued.id,
                col(VoucherPass.used_at).is_(None),
                or_(
                    col(VoucherPass.checked_at).is_(None),
                    col(VoucherPass.checked_at) <= now - hold,
                ),
            )
        )
        return issued

    async def find_pass_by_code(
        self,
        session: AsyncSession,
        *,
        code: str,
    ) -> VoucherPass | None:
        result = await session.execute(
            select(VoucherPass)
            .where(col(VoucherPass.code) == code)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def reload_pass(
        self,
        session: AsyncSession,
        *,
        pass_id: uuid.UUID,
    ) -> VoucherPass | None:
        """The pass as the database has it now, not as the identity map does.

        For the re-read under the ledger lock: the first read happened before
        the lock, and a plain ``get`` would hand back that stale object.
        """
        result = await session.execute(
            select(VoucherPass)
            .where(col(VoucherPass.id) == pass_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_pass_for_user(
        self,
        session: AsyncSession,
        *,
        pass_id: uuid.UUID,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> VoucherPass | None:
        result = await session.execute(
            select(VoucherPass)
            .where(
                col(VoucherPass.id) == pass_id,
                col(VoucherPass.event_id) == event_id,
                col(VoucherPass.user_id) == user_id,
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def hold_pass(
        self,
        session: AsyncSession,
        *,
        pass_id: uuid.UUID,
        now: dt.datetime,
    ) -> bool:
        """Mark a pass as checked, which keeps it redeemable for the hold
        (``logic.vouchers.PASS_HOLD``) from ``now``.

        Only a pass that has not yet expired can be held. A check after its
        expiry, while an earlier hold still runs, finds it redeemable but does
        not move the hold on, so however often it is checked a code is dead
        one hold after its expiry at the latest, and a held code outlives the
        volunteer's next one by no more than that. False when the hold was not
        moved.
        """
        result = cast(
            CursorResult[Any],
            await session.execute(
                update(VoucherPass)
                .where(
                    col(VoucherPass.id) == pass_id,
                    col(VoucherPass.used_at).is_(None),
                    col(VoucherPass.expires_at) > now,
                )
                .values(checked_at=now)
            ),
        )
        return result.rowcount > 0

    async def consume_pass(
        self,
        session: AsyncSession,
        *,
        pass_id: uuid.UUID,
        now: dt.datetime,
        hold: dt.timedelta,
    ) -> bool:
        """Mark a pass used; False if it was used or had run out meanwhile."""
        result = await session.execute(
            update(VoucherPass)
            .where(
                col(VoucherPass.id) == pass_id,
                col(VoucherPass.used_at).is_(None),
                _redeemable_at(now, hold),
            )
            .values(used_at=now)
            .returning(col(VoucherPass.id))
        )
        return result.first() is not None


def _redeemable_at(now: dt.datetime, hold: dt.timedelta) -> Any:
    """SQL for ``logic.vouchers.pass_redeemable`` minus the ``used_at`` test."""
    return or_(
        col(VoucherPass.expires_at) > now,
        and_(
            col(VoucherPass.checked_at).is_not(None),
            col(VoucherPass.checked_at) > now - hold,
        ),
    )


voucher = CRUDVoucher()
