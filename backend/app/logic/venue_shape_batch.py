"""Applying a batch of shape edits to a venue plan (#185 phase 2).

The editor sends every change (a drawn rectangle, a dragged vertex, an undo)
as a list of create/update/delete ops through one endpoint. The batch is
atomic: any failing op raises before the request commits, so nothing of it is
applied and the revision stays where it was. Clients may pick the id of a new
shape, which is what lets an undo of a delete re-create the very same shape.

Lives apart from :mod:`app.logic.venue_shapes` because it needs the request
schemas, and those import the pure geometry from there.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic_core import PydanticCustomError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.errors import raise_problem
from app.logic import venue_shapes
from app.models.location import Location
from app.models.venue_plan import VenuePlan, VenueShape
from app.schemas.venue_map import (
    ShapeCreateOp,
    ShapeDeleteOp,
    VenuePlanShapesRead,
    VenueShapeBatch,
    VenueShapeRead,
    VenueShapeUpdate,
)

REVISION_CONFLICT = "venue_shape.revision_conflict"
NOT_FOUND = "venue_shape.not_found"
ID_TAKEN = "venue_shape.id_taken"
TOO_MANY = "venue_shape.too_many"
TOO_MANY_POINTS = "venue_shape.too_many_points"

# Fields that cannot be cleared: an explicit null for them is ignored.
# ``prop``, ``rotation`` and ``scale`` always have a value on a prop and none
# on any other kind, so a null for them never means anything either.
_NOT_NULLABLE = frozenset(
    {"style", "points", "label_size", "sort_order", "prop", "rotation", "scale"}
)


def _now() -> datetime:
    """Naive UTC, matching how every other timestamp in the app is stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def shape_order_key(shape: VenueShape) -> tuple[int, datetime, str]:
    return (shape.sort_order, shape.created_at, str(shape.id))


def _check_link(
    location_id: uuid.UUID | None, event_locations: set[uuid.UUID], index: int
) -> None:
    if location_id is not None and location_id not in event_locations:
        raise_problem(
            422,
            code="location.wrong_event",
            detail=f"ops[{index}]: Location does not belong to this event",
        )


def _merge_update(
    shape: VenueShape, patch: VenueShapeUpdate, index: int
) -> dict[str, Any]:
    """The shape's fields with ``patch`` applied and the geometry re-validated."""
    merged: dict[str, Any] = {
        "style": shape.style,
        "points": shape.points,
        "label": shape.label,
        "label_size": shape.label_size,
        "label_x": shape.label_x,
        "label_y": shape.label_y,
        "stroke_width": shape.stroke_width,
        "location_id": shape.location_id,
        "sort_order": shape.sort_order,
        "prop": shape.prop,
        "rotation": shape.rotation,
        "scale": shape.scale,
    }
    for field in patch.model_fields_set:
        value = getattr(patch, field)
        if value is None and field in _NOT_NULLABLE:
            continue
        merged[field] = value
    try:
        geometry = venue_shapes.validate_geometry(
            kind=shape.kind,
            style=merged["style"],
            points=merged["points"],
            label=merged["label"],
            stroke_width=merged["stroke_width"],
            location_id=merged["location_id"],
            label_x=merged["label_x"],
            label_y=merged["label_y"],
            prop=merged["prop"],
            rotation=merged["rotation"],
            scale=merged["scale"],
        )
    except PydanticCustomError as exc:
        raise_problem(422, code=exc.type, detail=f"ops[{index}]: {exc.message()}")
    merged["points"] = geometry.points
    merged["stroke_width"] = geometry.stroke_width
    # A style patch on a prop is overridden by its family's style, on purpose.
    merged["style"] = geometry.style
    merged["prop"] = geometry.prop
    merged["rotation"] = geometry.rotation
    merged["scale"] = geometry.scale
    return merged


async def apply_batch(
    session: AsyncSession, *, plan: VenuePlan, batch: VenueShapeBatch
) -> VenuePlanShapesRead:
    """Apply ``batch`` to ``plan`` in order, all or nothing, and bump its revision.

    Errors (``venue_shape.*``, ``location.wrong_event``) name the failing op as
    ``ops[i]`` in the detail. Never commits; the request owns the transaction,
    and a raised problem rolls the whole batch back with it.
    """
    # Row lock: two editors saving at once are serialised here, so the second
    # one sees the first one's revision and gets its 409.
    await session.refresh(plan, with_for_update=True)
    # A savepoint, so a failing op undoes the ops before it even when the
    # caller's transaction goes on (and in tests, which share one session).
    async with session.begin_nested():
        if (
            batch.expected_revision is not None
            and batch.expected_revision != plan.shapes_revision
        ):
            raise_problem(
                409,
                code=REVISION_CONFLICT,
                detail="The map was changed in the meantime; reload it and try again",
            )

        rows = (
            (
                await session.execute(
                    select(VenueShape).where(col(VenueShape.plan_id) == plan.id)
                )
            )
            .scalars()
            .all()
        )
        by_id: dict[uuid.UUID, VenueShape] = {s.id: s for s in rows}
        event_locations = set(
            (
                await session.execute(
                    select(col(Location.id)).where(
                        col(Location.event_id) == plan.event_id
                    )
                )
            )
            .scalars()
            .all()
        )
        now = _now()

        for index, op in enumerate(batch.ops):
            if isinstance(op, ShapeCreateOp):
                data = op.shape
                if data.id is not None and (
                    data.id in by_id
                    or await session.get(VenueShape, data.id) is not None
                ):
                    raise_problem(
                        409,
                        code=ID_TAKEN,
                        detail=f"ops[{index}]: A shape with this id already exists",
                    )
                _check_link(data.location_id, event_locations, index)
                sort_order = data.sort_order
                if sort_order is None:
                    sort_order = (
                        max((s.sort_order for s in by_id.values()), default=-1) + 1
                    )
                shape = VenueShape(
                    id=data.id or uuid.uuid4(),
                    created_at=now,
                    updated_at=now,
                    plan_id=plan.id,
                    location_id=data.location_id,
                    kind=data.kind,
                    style=data.style,
                    points=data.points,
                    label=data.label,
                    label_size=data.label_size,
                    label_x=data.label_x,
                    label_y=data.label_y,
                    stroke_width=data.stroke_width,
                    prop=data.prop,
                    rotation=data.rotation,
                    scale=data.scale,
                    sort_order=sort_order,
                )
                session.add(shape)
                by_id[shape.id] = shape
                continue

            shape = by_id.get(op.id)
            if shape is None:
                raise_problem(
                    404,
                    code=NOT_FOUND,
                    detail=f"ops[{index}]: Shape not found on this plan",
                )
            if isinstance(op, ShapeDeleteOp):
                if shape in session.new:
                    # Created earlier in this very batch and never flushed:
                    # there is no row to delete, only the pending add to drop.
                    session.expunge(shape)
                else:
                    await session.delete(shape)
                del by_id[op.id]
                # Flushed at once, so a create re-using this id later in the same
                # batch (an undo inside a redo) does not collide with it.
                await session.flush()
                continue

            merged = _merge_update(shape, op.patch, index)
            if merged["location_id"] != shape.location_id:
                _check_link(merged["location_id"], event_locations, index)
            for field, value in merged.items():
                setattr(shape, field, value)
            shape.updated_at = now
            session.add(shape)

        if len(by_id) > venue_shapes.MAX_SHAPES_PER_PLAN:
            raise_problem(
                422,
                code=TOO_MANY,
                detail=(
                    f"A plan can hold at most {venue_shapes.MAX_SHAPES_PER_PLAN} shapes"
                ),
            )

        if (
            sum(len(s.points) for s in by_id.values())
            > venue_shapes.MAX_POINTS_PER_PLAN
        ):
            raise_problem(
                422,
                code=TOO_MANY_POINTS,
                detail=(
                    "A plan can hold at most "
                    f"{venue_shapes.MAX_POINTS_PER_PLAN} points in all its shapes"
                ),
            )

        plan.shapes_revision += 1
        plan.updated_at = now
        session.add(plan)
        await session.flush()
    return VenuePlanShapesRead(
        plan_id=plan.id,
        revision=plan.shapes_revision,
        shapes=[
            VenueShapeRead.model_validate(s)
            for s in sorted(by_id.values(), key=shape_order_key)
        ],
    )
