import datetime as dt
import uuid
from collections.abc import Iterable
from typing import Any, Literal, cast

from sqlalchemy import CursorResult, and_, false, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlmodel import col

from app.crud.base import CRUDBase
from app.crud.shift import WallClocks, on_own_clock, wall_clocks
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.schemas.event import EventCreate, EventUpdate

EventSortField = Literal["name", "start_date", "end_date", "status", "created_at"]

EventScope = Literal["mine", "discover", "featured", "all"]
"""Which slice of the catalogue a caller is asking for.

``mine`` — events the caller is a member of, at any status.
``discover`` — public, published events they are *not* yet in.
``featured`` — the superadmin-curated home screen selection.
``all`` — everything; only honoured for the platform superadmin.
"""


class CRUDEvent(CRUDBase[Event, EventCreate, EventUpdate]):
    async def zone_of(self, db: AsyncSession, event_id: uuid.UUID | None) -> str | None:
        """The event's zone for ``clock``. ``None`` for a task without an event,
        which the clock reads as ``settings.EVENT_TIMEZONE``.

        ``session.get``, so an event the request has loaded costs no query.
        """
        if event_id is None:
            return None
        event = await db.get(Event, event_id)
        return event.timezone if event is not None else None

    async def zones_by_id(
        self, db: AsyncSession, event_ids: Iterable[uuid.UUID | None]
    ) -> dict[uuid.UUID | None, str]:
        """``{event_id: zone}`` for several events, in one query."""
        ids = {event_id for event_id in event_ids if event_id is not None}
        if not ids:
            return {}
        result = await db.execute(
            select(col(Event.id), col(Event.timezone)).where(col(Event.id).in_(ids))
        )
        return {row[0]: row[1] for row in result.all()}

    def _apply_scope(
        self,
        query: Select[Any],
        *,
        scope: EventScope,
        member_event_ids: list[uuid.UUID],
    ) -> Select[Any]:
        """Restrict to the slice the caller asked for.

        This is the read-side counterpart to ``logic.permissions``: a private
        event must never appear in a list for someone who is not in it, so the
        membership check lives in the WHERE clause rather than in a post-filter
        that a future caller could forget to apply.
        """
        if scope == "all":
            # "Everything" still stops short of the demos. A sandbox event
            # belongs to exactly one guest and is not part of the installation
            # in any meaningful sense - showing it to the superadmin would put
            # a stranger's throwaway data in the admin event list, where the
            # only available action on it is to break it.
            return query.where(col(Event.is_sandbox).is_(False))

        if scope == "mine":
            if not member_event_ids:
                # No memberships — force an empty result rather than falling
                # through to an unfiltered query.
                return query.where(false())
            return query.where(col(Event.id).in_(member_event_ids))

        # ``mine`` above is membership-scoped and therefore already correct
        # for a guest looking at their own demo. Discover and Featured are the
        # opposite case: they list events to people who are not in them, so the
        # exclusion has to be explicit. Sandboxes are also seeded private,
        # which makes this the second of two locks rather than the only one.
        public_and_live = and_(
            col(Event.visibility) == "public",
            col(Event.status) == "published",
            col(Event.is_sandbox).is_(False),
        )
        if scope == "featured":
            return query.where(and_(public_and_live, col(Event.is_featured).is_(True)))

        # discover: public and published, minus what the caller is already in
        if member_event_ids:
            return query.where(
                and_(public_and_live, col(Event.id).notin_(member_event_ids))
            )
        return query.where(public_and_live)

    def _apply_common_filters(
        self,
        query: Select[Any],
        *,
        search: str | None = None,
        status: str | None = None,
        visibility: str | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        expired_on: tuple[bool, WallClocks] | None = None,
        also_include_ids: list[uuid.UUID] | None = None,
    ) -> Select[Any]:
        if search:
            query = query.where(
                col(Event.name).ilike(f"%{search}%")
                | col(Event.description).ilike(f"%{search}%")
            )
        if status:
            status_filter = col(Event.status) == status
            if also_include_ids:
                status_filter = or_(status_filter, col(Event.id).in_(also_include_ids))
            query = query.where(status_filter)
        if visibility:
            query = query.where(col(Event.visibility) == visibility)
        if date_from:
            query = query.where(col(Event.end_date) >= date_from)
        if date_to:
            query = query.where(col(Event.start_date) <= date_to)
        if expired_on is not None:
            # Each event's last day is over on its own clock.
            expired, clocks = expired_on
            over = on_own_clock(
                clocks,
                col(Event.timezone),
                lambda now: col(Event.end_date) < now.date(),
            )
            query = query.where(over if expired else ~over)
        return query

    async def get_multi_filtered(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        scope: EventScope = "mine",
        member_event_ids: list[uuid.UUID] | None = None,
        search: str | None = None,
        status: str | None = None,
        visibility: str | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        is_expired: bool | None = None,
        sort_by: EventSortField = "start_date",
        sort_dir: Literal["asc", "desc"] = "asc",
        also_include_ids: list[uuid.UUID] | None = None,
    ) -> list[Event]:
        query = self._apply_scope(
            select(Event),
            scope=scope,
            member_event_ids=member_event_ids or [],
        )
        query = self._apply_common_filters(
            query,
            search=search,
            status=status,
            visibility=visibility,
            date_from=date_from,
            date_to=date_to,
            expired_on=None
            if is_expired is None
            else (is_expired, await wall_clocks(db)),
            also_include_ids=also_include_ids,
        )
        order_col = getattr(Event, sort_by)
        query = query.order_by(
            col(order_col).asc() if sort_dir == "asc" else col(order_col).desc()
        )
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_count_filtered(
        self,
        db: AsyncSession,
        *,
        scope: EventScope = "mine",
        member_event_ids: list[uuid.UUID] | None = None,
        search: str | None = None,
        status: str | None = None,
        visibility: str | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        is_expired: bool | None = None,
        also_include_ids: list[uuid.UUID] | None = None,
    ) -> int:
        query = self._apply_scope(
            select(func.count()).select_from(Event),
            scope=scope,
            member_event_ids=member_event_ids or [],
        )
        query = self._apply_common_filters(
            query,
            search=search,
            status=status,
            visibility=visibility,
            date_from=date_from,
            date_to=date_to,
            expired_on=None
            if is_expired is None
            else (is_expired, await wall_clocks(db)),
            also_include_ids=also_include_ids,
        )
        result = await db.execute(query)
        return result.scalar_one()

    async def count_owned_by(self, db: AsyncSession, *, user_id: uuid.UUID) -> int:
        """Count events this user owns (via an ``owner`` membership)."""
        result = await db.execute(
            select(func.count())
            .select_from(EventMembership)
            .where(
                col(EventMembership.user_id) == user_id,
                col(EventMembership.role) == "owner",
            )
        )
        return result.scalar_one()

    async def reassign_owner(
        self,
        db: AsyncSession,
        *,
        from_user_id: uuid.UUID,
        to_user_id: uuid.UUID,
    ) -> tuple[int, list[uuid.UUID]]:
        """Hand every event owned by one user to another.

        Both the denormalised ``created_by_id`` and the ``owner`` membership
        rows move, and any membership the target already held in those events
        is replaced so they are not left with a weaker role than owner.

        Returns the number of memberships moved and the ids of those events.
        The source user is no longer a member of any of them afterwards, so a
        caller that keeps the account clears what hangs off that membership.
        """
        owned_result = await db.execute(
            select(col(EventMembership.event_id)).where(
                col(EventMembership.user_id) == from_user_id,
                col(EventMembership.role) == "owner",
            )
        )
        owned_event_ids = list(owned_result.scalars().all())

        await db.execute(
            update(Event)
            .where(col(Event.created_by_id) == from_user_id)
            .values(created_by_id=to_user_id)
        )

        if not owned_event_ids:
            return 0, []

        # Clear any weaker membership the target already has in these events,
        # so the unique (user, event) constraint does not reject the handover.
        from sqlalchemy import delete as sa_delete

        await db.execute(
            sa_delete(EventMembership).where(
                col(EventMembership.user_id) == to_user_id,
                col(EventMembership.event_id).in_(owned_event_ids),
            )
        )
        result = cast(
            CursorResult[Any],
            await db.execute(
                update(EventMembership)
                .where(
                    col(EventMembership.user_id) == from_user_id,
                    col(EventMembership.role) == "owner",
                )
                .values(user_id=to_user_id)
            ),
        )
        return (result.rowcount if result.rowcount > 0 else 0), owned_event_ids


event = CRUDEvent(Event)
