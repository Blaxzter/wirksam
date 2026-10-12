import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import cast

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic.images import NormalizedImage
from app.models.location import Location
from app.models.venue_plan import VenueMarker, VenuePlan, VenuePlanImage
from app.schemas.venue_map import (
    VenueMarkerCreate,
    VenueMarkerRead,
    VenuePlanRead,
)


def _now() -> datetime:
    """Naive UTC, matching how every other timestamp in the app is stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


_PLAN_ORDER = (col(VenuePlan.sort_order), col(VenuePlan.created_at), col(VenuePlan.id))


class CRUDVenueMap:
    """Venue plans, their image bytes and their markers.

    Never commits; the request owns the transaction.
    """

    # ── Plans ──────────────────────────────────────────────────────────────

    async def get_plan(
        self, session: AsyncSession, *, plan_id: uuid.UUID
    ) -> VenuePlan | None:
        return await session.get(VenuePlan, plan_id)

    async def list_plans(
        self, session: AsyncSession, *, event_id: uuid.UUID
    ) -> list[VenuePlan]:
        """An event's plans in display order (``sort_order``, then age)."""
        result = await session.execute(
            select(VenuePlan)
            .where(col(VenuePlan.event_id) == event_id)
            .order_by(*_PLAN_ORDER)
        )
        return list(result.scalars().all())

    async def list_markers_for_plans(
        self, session: AsyncSession, *, plan_ids: Sequence[uuid.UUID]
    ) -> list[VenueMarker]:
        if not plan_ids:
            return []
        result = await session.execute(
            select(VenueMarker)
            .where(col(VenueMarker.plan_id).in_(plan_ids))
            .order_by(col(VenueMarker.created_at), col(VenueMarker.id))
        )
        return list(result.scalars().all())

    async def list_plans_with_markers(
        self, session: AsyncSession, *, event_id: uuid.UUID
    ) -> list[VenuePlanRead]:
        """Plans in display order with their markers nested — two queries."""
        plans = await self.list_plans(session, event_id=event_id)
        markers = await self.list_markers_for_plans(
            session, plan_ids=[p.id for p in plans]
        )
        by_plan: dict[uuid.UUID, list[VenueMarkerRead]] = defaultdict(list)
        for marker in markers:
            by_plan[marker.plan_id].append(VenueMarkerRead.model_validate(marker))
        return [
            VenuePlanRead.model_validate(plan).model_copy(
                update={"markers": by_plan.get(plan.id, [])}
            )
            for plan in plans
        ]

    async def create_plan(
        self, session: AsyncSession, *, event_id: uuid.UUID, name: str
    ) -> VenuePlan:
        """Append a plan after the event's existing ones."""
        current_max = await session.scalar(
            select(func.max(col(VenuePlan.sort_order))).where(
                col(VenuePlan.event_id) == event_id
            )
        )
        plan = VenuePlan(
            event_id=event_id,
            name=name,
            sort_order=0 if current_max is None else current_max + 1,
        )
        session.add(plan)
        await session.flush()
        await session.refresh(plan)
        return plan

    async def rename_plan(
        self, session: AsyncSession, *, plan: VenuePlan, name: str
    ) -> VenuePlan:
        plan.name = name
        plan.updated_at = _now()
        session.add(plan)
        await session.flush()
        await session.refresh(plan)
        return plan

    async def delete_plan(self, session: AsyncSession, *, plan: VenuePlan) -> None:
        """Delete a plan; its image row and markers go with it (DB cascade)."""
        await session.delete(plan)
        await session.flush()

    async def reorder(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        plan_ids: Sequence[uuid.UUID],
    ) -> list[VenuePlan]:
        """Set ``sort_order`` to the position of each id in ``plan_ids``.

        Raises ``ValueError`` unless ``plan_ids`` names every plan of the event
        exactly once; the route turns that into 422 ``venue_plan.order_mismatch``.
        """
        plans = await self.list_plans(session, event_id=event_id)
        if len(plan_ids) != len(set(plan_ids)) or set(plan_ids) != {
            p.id for p in plans
        }:
            raise ValueError("plan_ids must list every plan of the event exactly once")
        by_id = {p.id: p for p in plans}
        now = _now()
        for position, plan_id in enumerate(plan_ids):
            plan = by_id[plan_id]
            if plan.sort_order != position:
                plan.sort_order = position
                plan.updated_at = now
                session.add(plan)
        await session.flush()
        return [by_id[plan_id] for plan_id in plan_ids]

    async def count_plans_with_image_by_event(
        self, session: AsyncSession, *, event_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """How many plans *with an image* each event has (absent means 0).

        A plan without an image is unfinished editor state, so it does not
        count towards showing the map to members.
        """
        if not event_ids:
            return {}
        result = await session.execute(
            select(col(VenuePlan.event_id), func.count())
            .where(
                col(VenuePlan.event_id).in_(event_ids),
                col(VenuePlan.image_etag).is_not(None),
            )
            .group_by(col(VenuePlan.event_id))
        )
        return dict(result.tuples().all())

    # ── Images ─────────────────────────────────────────────────────────────

    async def get_image(
        self, session: AsyncSession, *, plan_id: uuid.UUID
    ) -> VenuePlanImage | None:
        result = await session.execute(
            select(VenuePlanImage).where(col(VenuePlanImage.plan_id) == plan_id)
        )
        return result.scalars().first()

    async def upsert_image(
        self,
        session: AsyncSession,
        *,
        plan: VenuePlan,
        image: NormalizedImage,
    ) -> VenuePlanImage:
        """Store ``image`` as the plan's picture and mirror its etag and size
        onto the plan row. Markers keep their normalised coordinates.

        One ``INSERT ... ON CONFLICT (plan_id) DO UPDATE``, so two first
        uploads racing for the same plan both succeed (last one wins) instead
        of the second tripping the unique index.
        """
        now = _now()
        insert_stmt = pg_insert(VenuePlanImage).values(
            id=uuid.uuid4(),
            created_at=now,
            updated_at=now,
            plan_id=plan.id,
            data=image.data,
            content_type=image.content_type,
            etag=image.etag,
        )
        excluded = insert_stmt.excluded
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["plan_id"],
            set_={
                "data": excluded.data,
                "content_type": excluded.content_type,
                "etag": excluded.etag,
                "updated_at": excluded.updated_at,
            },
        ).returning(VenuePlanImage)
        result = await session.execute(
            select(VenuePlanImage)
            .from_statement(stmt)
            .execution_options(populate_existing=True)
        )
        row = result.scalars().one()

        plan.image_etag = image.etag
        plan.image_width = image.width
        plan.image_height = image.height
        plan.updated_at = now
        session.add(plan)
        await session.flush()
        return row

    # ── Markers ────────────────────────────────────────────────────────────

    async def get_marker(
        self, session: AsyncSession, *, marker_id: uuid.UUID
    ) -> VenueMarker | None:
        return await session.get(VenueMarker, marker_id)

    async def get_marker_for_location(
        self,
        session: AsyncSession,
        *,
        plan_id: uuid.UUID,
        location_id: uuid.UUID,
        exclude_id: uuid.UUID | None = None,
    ) -> VenueMarker | None:
        """The plan's marker for ``location_id``, if it already has one."""
        query = select(VenueMarker).where(
            col(VenueMarker.plan_id) == plan_id,
            col(VenueMarker.location_id) == location_id,
        )
        if exclude_id is not None:
            query = query.where(col(VenueMarker.id) != exclude_id)
        result = await session.execute(query)
        return result.scalars().first()

    async def create_marker(
        self,
        session: AsyncSession,
        *,
        plan_id: uuid.UUID,
        data: VenueMarkerCreate,
    ) -> VenueMarker:
        marker = VenueMarker(plan_id=plan_id, **data.model_dump())
        session.add(marker)
        await session.flush()
        await session.refresh(marker)
        return marker

    # ── Event clone ────────────────────────────────────────────────────────

    async def copy_for_clone(
        self,
        session: AsyncSession,
        *,
        source_event_id: uuid.UUID,
        new_event_id: uuid.UUID,
    ) -> tuple[dict[uuid.UUID, uuid.UUID], int]:
        """Copy an event's locations, plans (with image bytes) and markers.

        Returns ``(location_map, plans_created)`` where ``location_map`` maps
        each source location id to its copy, for remapping ``location_id`` on
        the cloned tasks, batches and shifts. Image bytes are copied inside the
        database, never pulled into Python.
        """
        now = _now()

        source_locations = (
            (
                await session.execute(
                    select(Location).where(col(Location.event_id) == source_event_id)
                )
            )
            .scalars()
            .all()
        )
        location_map: dict[uuid.UUID, uuid.UUID] = {}
        for src in source_locations:
            new_id = uuid.uuid4()
            location_map[src.id] = new_id
            session.add(
                Location(
                    id=new_id,
                    created_at=now,
                    updated_at=now,
                    event_id=new_event_id,
                    name=src.name,
                    description=src.description,
                    address=src.address,
                    map_url=src.map_url,
                    contact=src.contact,
                )
            )

        source_plans = await self.list_plans(session, event_id=source_event_id)
        plan_map: dict[uuid.UUID, uuid.UUID] = {}
        for src in source_plans:
            new_id = uuid.uuid4()
            plan_map[src.id] = new_id
            session.add(
                VenuePlan(
                    id=new_id,
                    created_at=now,
                    updated_at=now,
                    event_id=new_event_id,
                    name=src.name,
                    sort_order=src.sort_order,
                    image_etag=src.image_etag,
                    image_width=src.image_width,
                    image_height=src.image_height,
                )
            )
        # The image INSERT ... SELECT below is a Core statement, so the plan
        # rows it points at must be in the database first.
        await session.flush()

        images = cast(sa.Table, sa.inspect(VenuePlanImage).local_table)
        for old_plan_id, new_plan_id in plan_map.items():
            await session.execute(
                sa.insert(images).from_select(
                    [
                        "id",
                        "created_at",
                        "updated_at",
                        "plan_id",
                        "data",
                        "content_type",
                        "etag",
                    ],
                    select(
                        func.gen_random_uuid(),
                        sa.literal(now, sa.DateTime()),
                        sa.literal(now, sa.DateTime()),
                        sa.literal(new_plan_id, sa.Uuid[uuid.UUID]()),
                        images.c.data,
                        images.c.content_type,
                        images.c.etag,
                    ).where(images.c.plan_id == old_plan_id),
                )
            )

        markers = await self.list_markers_for_plans(session, plan_ids=list(plan_map))
        for src in markers:
            new_location_id: uuid.UUID | None = None
            if src.location_id is not None:
                new_location_id = location_map.get(src.location_id)
                if new_location_id is None:
                    # Points outside the source event; nothing to remap to.
                    continue
            session.add(
                VenueMarker(
                    created_at=now,
                    updated_at=now,
                    plan_id=plan_map[src.plan_id],
                    location_id=new_location_id,
                    kind=src.kind,
                    label=src.label,
                    x=src.x,
                    y=src.y,
                )
            )
        await session.flush()
        return location_map, len(plan_map)


venue_map = CRUDVenueMap()
