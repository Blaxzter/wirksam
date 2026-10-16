import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy import CursorResult, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, col

from app.logic.images import NormalizedImage
from app.models.booking import Booking
from app.models.location import Location
from app.models.shift import Shift
from app.models.task import Task
from app.models.venue_plan import VenueMarker, VenuePlan, VenuePlanImage, VenueShape
from app.schemas.venue_map import (
    CANVAS_PRESETS,
    CanvasPreset,
    VenueLocationStat,
    VenueMarkerCreate,
    VenueMarkerRead,
    VenuePlanRead,
    VenueShapeRead,
)


def _now() -> datetime:
    """Naive UTC, matching how every other timestamp in the app is stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


_PLAN_ORDER = (col(VenuePlan.sort_order), col(VenuePlan.created_at), col(VenuePlan.id))
_SHAPE_ORDER = (
    col(VenueShape.sort_order),
    col(VenueShape.created_at),
    col(VenueShape.id),
)
# The longer side of a canvas that replaces a removed picture.
_CANVAS_LONG_SIDE = 1600


def drawing_fields(shape: VenueShape) -> dict[str, Any]:
    """A shape's drawing, without its plan, its id or its location link.

    What every copy of a drawing carries over: the event clone, saving a plan
    as a template and starting a plan from one.
    """
    return {
        "kind": shape.kind,
        "style": shape.style,
        "points": [list(p) for p in shape.points],
        "label": shape.label,
        "label_size": shape.label_size,
        "label_x": shape.label_x,
        "label_y": shape.label_y,
        "stroke_width": shape.stroke_width,
        "prop": shape.prop,
        "rotation": shape.rotation,
        "scale": shape.scale,
        "sort_order": shape.sort_order,
    }


async def copy_image_bytes(
    session: AsyncSession,
    *,
    source: type[SQLModel],
    source_key: str,
    source_id: uuid.UUID,
    target: type[SQLModel],
    target_key: str,
    target_id: uuid.UUID,
    now: datetime,
) -> bool:
    """Copy one image row between the image tables, inside the database.

    ``source``/``target`` are image models (``VenuePlanImage``,
    ``VenueTemplateImage``) and ``*_key`` their owner column. One
    ``INSERT ... SELECT``, so the bytes are never pulled into Python. The
    target's owner row must already be flushed. Returns whether a row was
    copied (False when the source has no image).
    """
    src = cast(sa.Table, sa.inspect(source).local_table)
    dst = cast(sa.Table, sa.inspect(target).local_table)
    result = await session.execute(
        sa.insert(dst).from_select(
            [
                "id",
                "created_at",
                "updated_at",
                target_key,
                "data",
                "content_type",
                "etag",
            ],
            select(
                func.gen_random_uuid(),
                sa.literal(now, sa.DateTime()),
                sa.literal(now, sa.DateTime()),
                sa.literal(target_id, sa.Uuid[uuid.UUID]()),
                src.c.data,
                src.c.content_type,
                src.c.etag,
            ).where(src.c[source_key] == source_id),
        )
    )
    return cast(CursorResult[Any], result).rowcount > 0


class CRUDVenueMap:
    """Venue plans, their image bytes, their markers and their shapes.

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

    async def list_shapes_for_plans(
        self, session: AsyncSession, *, plan_ids: Sequence[uuid.UUID]
    ) -> list[VenueShape]:
        """Shapes of ``plan_ids``, per plan in drawing order."""
        if not plan_ids:
            return []
        result = await session.execute(
            select(VenueShape)
            .where(col(VenueShape.plan_id).in_(plan_ids))
            .order_by(col(VenueShape.plan_id), *_SHAPE_ORDER)
        )
        return list(result.scalars().all())

    async def plan_reads(
        self, session: AsyncSession, *, plans: Sequence[VenuePlan]
    ) -> list[VenuePlanRead]:
        """``plans`` as reads with markers and shapes nested — two queries."""
        plan_ids = [p.id for p in plans]
        markers = await self.list_markers_for_plans(session, plan_ids=plan_ids)
        shapes = await self.list_shapes_for_plans(session, plan_ids=plan_ids)
        markers_by_plan: dict[uuid.UUID, list[VenueMarkerRead]] = defaultdict(list)
        for marker in markers:
            markers_by_plan[marker.plan_id].append(
                VenueMarkerRead.model_validate(marker)
            )
        shapes_by_plan: dict[uuid.UUID, list[VenueShapeRead]] = defaultdict(list)
        for shape in shapes:
            shapes_by_plan[shape.plan_id].append(VenueShapeRead.model_validate(shape))
        return [
            VenuePlanRead.model_validate(plan).model_copy(
                update={
                    "markers": markers_by_plan.get(plan.id, []),
                    "shapes": shapes_by_plan.get(plan.id, []),
                }
            )
            for plan in plans
        ]

    async def list_plans_full(
        self, session: AsyncSession, *, event_id: uuid.UUID
    ) -> list[VenuePlanRead]:
        """Plans in display order with markers and shapes nested — three queries."""
        plans = await self.list_plans(session, event_id=event_id)
        return await self.plan_reads(session, plans=plans)

    async def create_plan(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        name: str,
        canvas: CanvasPreset = "landscape",
    ) -> VenuePlan:
        """Append a blank plan of the ``canvas`` aspect after the event's others."""
        canvas_width, canvas_height = CANVAS_PRESETS[canvas]
        plan = VenuePlan(
            event_id=event_id,
            name=name,
            sort_order=await self.next_sort_order(session, event_id=event_id),
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )
        session.add(plan)
        await session.flush()
        await session.refresh(plan)
        return plan

    async def next_sort_order(
        self, session: AsyncSession, *, event_id: uuid.UUID
    ) -> int:
        """The ``sort_order`` that puts a new plan after the event's others."""
        current_max = await session.scalar(
            select(func.max(col(VenuePlan.sort_order))).where(
                col(VenuePlan.event_id) == event_id
            )
        )
        return 0 if current_max is None else current_max + 1

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
        """Delete a plan; its image row, markers and shapes go with it (DB cascade)."""
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

    async def count_visible_plans_by_event(
        self, session: AsyncSession, *, event_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """How many plans *with an image or a shape* each event has (absent = 0).

        A plan with neither is unfinished editor state (even with pins on it),
        so it does not count towards showing the map to members.
        """
        if not event_ids:
            return {}
        has_shape = (
            select(sa.literal(1))
            .where(col(VenueShape.plan_id) == col(VenuePlan.id))
            .correlate(VenuePlan)
            .exists()
        )
        result = await session.execute(
            select(col(VenuePlan.event_id), func.count())
            .where(
                col(VenuePlan.event_id).in_(event_ids),
                sa.or_(col(VenuePlan.image_etag).is_not(None), has_shape),
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

    async def delete_image(
        self, session: AsyncSession, *, plan: VenuePlan
    ) -> VenuePlan:
        """Remove the plan's picture and turn it into a blank canvas.

        The canvas takes the picture's aspect with its longer side scaled to
        1600, so the normalised shapes and markers stay where they were.
        """
        image = await self.get_image(session, plan_id=plan.id)
        if image is not None:
            await session.delete(image)
        if plan.image_width and plan.image_height:
            scale = _CANVAS_LONG_SIDE / max(plan.image_width, plan.image_height)
            plan.canvas_width = max(1, round(plan.image_width * scale))
            plan.canvas_height = max(1, round(plan.image_height * scale))
        plan.image_etag = None
        plan.image_width = None
        plan.image_height = None
        plan.updated_at = _now()
        session.add(plan)
        await session.flush()
        await session.refresh(plan)
        return plan

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

    # ── Staffing ───────────────────────────────────────────────────────────

    async def location_stats(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        day: date,
        include_unpublished: bool,
    ) -> list[VenueLocationStat]:
        """Per-location staffing over the event's shifts on ``day``.

        One aggregate query. Only confirmed bookings count, as everywhere
        ``current_bookings`` is computed; ``include_unpublished`` is for event
        admins, everyone else sees published tasks only. Locations without a
        shift that day are absent.
        """
        # Correlated per-shift count, so only this event's shifts on ``day``
        # are counted rather than every booking on the platform.
        booked = (
            select(func.count())
            .where(
                col(Booking.shift_id) == col(Shift.id),
                col(Booking.status) == "confirmed",
            )
            .correlate(Shift)
            .scalar_subquery()
        )
        # Cap each shift at its capacity before summing: an over-booked shift
        # (possible after shift regeneration lowers max_bookings) must not
        # hide a free place in another shift at the same location.
        capped = func.least(booked, col(Shift.max_bookings))
        query = (
            select(
                col(Shift.location_id),
                func.count(col(Shift.id)),
                func.coalesce(func.sum(capped), 0),
                func.coalesce(func.sum(col(Shift.max_bookings)), 0),
                func.count(col(Shift.id)).filter(booked < col(Shift.max_bookings)),
            )
            .join(Task, col(Task.id) == col(Shift.task_id))
            .where(
                col(Task.event_id) == event_id,
                col(Shift.date) == day,
                col(Shift.location_id).is_not(None),
            )
            .group_by(col(Shift.location_id))
            .order_by(col(Shift.location_id))
        )
        if not include_unpublished:
            query = query.where(col(Task.status) == "published")

        result = await session.execute(query)
        return [
            VenueLocationStat(
                location_id=location_id,
                shift_count=int(shift_count),
                booked=int(booked_total),
                capacity=int(capacity),
                open_shifts=int(open_shifts),
            )
            for location_id, shift_count, booked_total, capacity, open_shifts in (
                result.tuples().all()
            )
            if location_id is not None
        ]

    # ── Event clone ────────────────────────────────────────────────────────

    async def copy_for_clone(
        self,
        session: AsyncSession,
        *,
        source_event_id: uuid.UUID,
        new_event_id: uuid.UUID,
    ) -> tuple[dict[uuid.UUID, uuid.UUID], int]:
        """Copy an event's locations, plans (with image bytes), markers and shapes.

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
        new_plans: dict[uuid.UUID, VenuePlan] = {}
        for src in source_plans:
            new_id = uuid.uuid4()
            plan_map[src.id] = new_id
            new_plans[new_id] = VenuePlan(
                id=new_id,
                created_at=now,
                updated_at=now,
                event_id=new_event_id,
                name=src.name,
                sort_order=src.sort_order,
                image_etag=src.image_etag,
                image_width=src.image_width,
                image_height=src.image_height,
                canvas_width=src.canvas_width,
                canvas_height=src.canvas_height,
                # Set to 1 below for a plan whose drawing is copied: 0 tells
                # clients there is nothing drawn to fetch.
                shapes_revision=0,
            )
            session.add(new_plans[new_id])
        # The image INSERT ... SELECT below is a Core statement, so the plan
        # rows it points at must be in the database first.
        await session.flush()

        for old_plan_id, new_plan_id in plan_map.items():
            await copy_image_bytes(
                session,
                source=VenuePlanImage,
                source_key="plan_id",
                source_id=old_plan_id,
                target=VenuePlanImage,
                target_key="plan_id",
                target_id=new_plan_id,
                now=now,
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
        shapes = await self.list_shapes_for_plans(session, plan_ids=list(plan_map))
        for shape in shapes:
            new_plans[plan_map[shape.plan_id]].shapes_revision = 1
            session.add(
                VenueShape(
                    created_at=now,
                    updated_at=now,
                    plan_id=plan_map[shape.plan_id],
                    # Unlike a marker, an area is worth keeping without its
                    # place: a link that cannot be remapped is cleared and the
                    # drawing stays.
                    location_id=(
                        location_map.get(shape.location_id)
                        if shape.location_id is not None
                        else None
                    ),
                    **drawing_fields(shape),
                )
            )
        await session.flush()
        return location_map, len(plan_map)


venue_map = CRUDVenueMap()
