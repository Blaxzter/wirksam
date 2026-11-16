"""What the public page of a shared list shows, for strangers and for the
organisers' preview alike.

The list's title and intro, its event, its form settings, how long a
guest's data is kept and, while it is live, the shifts it offers by day with
their free places and the vouchers each earns. While the list shows first
names, each shift also names the guests whose sign-up was told so
(``bookings.show_first_name``), through whichever list, under the name of
that sign-up, and counts everyone else. Members are never named here: nobody
asked them.
"""

import uuid
from collections.abc import Collection
from itertools import groupby
from typing import Literal, cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.logic import clock
from app.logic.shared_lists import offer
from app.logic.shared_lists.normalize import first_name
from app.logic.shared_lists.offer import EffectiveStatus, OfferedShift
from app.models.booking import Booking
from app.models.event import Event
from app.models.shared_list import AskMode, SharedList, SharedListGuest, ShowNames
from app.models.user import User
from app.schemas.public_shared_list import (
    PublicDay,
    PublicEventRef,
    PublicSharedList,
    PublicShift,
)


def event_ref(event: Event) -> PublicEventRef:
    return PublicEventRef(
        name=event.name,
        start_date=event.start_date,
        end_date=event.end_date,
        timezone=event.timezone,
    )


async def first_names(
    session: AsyncSession, shift_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """Per shift, the first names of confirmed guest sign-ups that agreed to
    be named, each under its own name, in the order they signed up.

    Only guests with a live contact row: an erased guest is never named, nor
    one whose event was deleted, even where a moved task took their booking
    to another event."""
    if not shift_ids:
        return {}
    rows = await session.execute(
        select(col(Booking.shift_id), col(Booking.guest_name))
        .join(User, col(User.id) == col(Booking.user_id))
        .join(SharedListGuest, col(SharedListGuest.user_id) == col(User.id))
        .where(
            col(Booking.shift_id).in_(shift_ids),
            col(Booking.status) == "confirmed",
            col(Booking.show_first_name),
            col(User.is_list_guest),
            col(SharedListGuest.erased_at).is_(None),
            col(Booking.guest_name).is_not(None),
        )
        .order_by(col(Booking.created_at), col(Booking.id))
    )
    names: dict[uuid.UUID, list[str]] = {}
    for shift_id, name in rows.all():
        if shift_id is not None and name:
            names.setdefault(shift_id, []).append(first_name(name))
    return names


def public_shift(offered: OfferedShift, *, names: list[str] | None) -> PublicShift:
    """One shift as strangers see it. ``names`` None: the list names nobody."""
    free = offered.free
    named = names or []
    return PublicShift(
        id=offered.shift.id,
        task_id=offered.task.id,
        task_name=offered.task.name,
        location=offered.shift.location,
        start_time=offered.shift.start_time,
        end_time=offered.shift.end_time,
        capacity=offered.shift.max_bookings,
        free=free,
        full=free == 0,
        names=named,
        others_count=max(0, offered.confirmed - len(named)) if names is not None else 0,
        vouchers=offered.task.vouchers_per_shift,
    )


def _public_status(effective: EffectiveStatus) -> Literal["live", "paused", "closed"]:
    """Strangers are not told why a list closed."""
    if effective in ("expired", "ended"):
        return "closed"
    return "paused" if effective == "paused" else "live"


async def build_public_list(
    session: AsyncSession, shared_list: SharedList, *, event: Event
) -> PublicSharedList:
    """The public page of ``shared_list``, on its event's clock."""
    now_wall = clock.wall_clock_now(event.timezone)
    effective = offer.effective_status(
        shared_list,
        event=event,
        last_start=await offer.last_start(session, shared_list),
        now_wall=now_wall,
    )
    days: list[PublicDay] = []
    if effective == "live":
        offered = await offer.list_shifts(session, shared_list, now_wall=now_wall)
        names = (
            await first_names(session, [o.shift.id for o in offered])
            if shared_list.show_names == "first"
            else None
        )
        days = [
            PublicDay(
                date=date,
                shifts=[
                    public_shift(
                        o, names=None if names is None else names.get(o.shift.id, [])
                    )
                    for o in group
                ],
            )
            for date, group in groupby(offered, key=lambda o: o.shift.date)
        ]
    return PublicSharedList(
        code=shared_list.code,
        title=shared_list.title,
        intro=shared_list.intro,
        status=_public_status(effective),
        event=event_ref(event),
        # The CHECK constraints hold these to their literals.
        ask_email=cast(AskMode, shared_list.ask_email),
        ask_phone=cast(AskMode, shared_list.ask_phone),
        show_names=cast(ShowNames, shared_list.show_names),
        max_per_person=shared_list.max_per_person,
        days=days,
        retention_days=settings.GUEST_DATA_RETENTION_DAYS,
    )


async def count_view(session: AsyncSession, shared_list_id: uuid.UUID) -> None:
    """Count one opening of the public page.

    An atomic increment, issued last in the request so its row lock lasts
    only until the commit; it does not wait for sign-ups in flight, which
    hold the row ``FOR KEY SHARE``.
    """
    await session.execute(
        update(SharedList)
        .where(col(SharedList.id) == shared_list_id)
        .values(view_count=col(SharedList.view_count) + 1)
        .execution_options(synchronize_session=False)
    )
