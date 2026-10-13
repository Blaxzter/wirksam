import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic.venue_shapes import LINKABLE_KINDS, shape_anchor
from app.models.location import Location
from app.models.venue_plan import VenueMarker, VenuePlan, VenueShape
from app.schemas.location import LocationCreate, LocationPin, LocationUpdate


def _now() -> datetime:
    """Naive UTC, matching how every other timestamp in the app is stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CRUDLocation:
    """Per-event locations. Never commits; the request owns the transaction.

    Keeping the ``location`` text of tasks, batches and shifts in step with a
    rename is :func:`app.logic.locations.propagate_rename`, called by the route.
    """

    async def get(
        self, session: AsyncSession, *, location_id: uuid.UUID
    ) -> Location | None:
        return await session.get(Location, location_id)

    async def list_for_event(
        self, session: AsyncSession, *, event_id: uuid.UUID
    ) -> list[Location]:
        """All of an event's locations, alphabetically regardless of case."""
        result = await session.execute(
            select(Location)
            .where(col(Location.event_id) == event_id)
            .order_by(func.lower(col(Location.name)), col(Location.name))
        )
        return list(result.scalars().all())

    async def get_by_name_ci(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> Location | None:
        """The event's location called ``name``, ignoring case and outer spaces.

        The unique constraint is case-sensitive (the backfill needs exact
        matching); this is the friendlier check the routes run first, so
        "Foyer" and "foyer" cannot both be created by hand. ``exclude_id``
        skips the row being renamed.
        """
        query = select(Location).where(
            col(Location.event_id) == event_id,
            func.lower(col(Location.name)) == name.strip().lower(),
        )
        if exclude_id is not None:
            query = query.where(col(Location.id) != exclude_id)
        result = await session.execute(query)
        return result.scalars().first()

    async def create(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        data: LocationCreate,
    ) -> Location:
        obj = Location(event_id=event_id, **data.model_dump())
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
        return obj

    async def update(
        self,
        session: AsyncSession,
        *,
        location: Location,
        data: LocationUpdate,
    ) -> Location:
        """Apply the fields the client sent (``exclude_unset``)."""
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(location, field, value)
        location.updated_at = _now()
        session.add(location)
        await session.flush()
        await session.refresh(location)
        return location

    async def delete(self, session: AsyncSession, *, location: Location) -> None:
        """Delete a location. The database nulls ``location_id`` on tasks,
        batches, shifts and shapes (their text and drawing stay) and drops its
        markers."""
        await session.delete(location)
        await session.flush()

    async def pins_for_location(
        self, session: AsyncSession, *, location_id: uuid.UUID
    ) -> list[LocationPin]:
        """Every placement of a location, in plan order.

        A marker wins. On a plan where the location has no marker but a linked
        rect or polygon, the first such area (by ``sort_order``) yields a pin
        at its centroid, so a drawn room shows up in mini-maps too.
        """
        marker_rows = (
            (
                await session.execute(
                    select(VenueMarker, VenuePlan)
                    .join(VenuePlan, col(VenuePlan.id) == col(VenueMarker.plan_id))
                    .where(col(VenueMarker.location_id) == location_id)
                )
            )
            .tuples()
            .all()
        )
        shape_rows = (
            (
                await session.execute(
                    select(VenueShape, VenuePlan)
                    .join(VenuePlan, col(VenuePlan.id) == col(VenueShape.plan_id))
                    .where(
                        col(VenueShape.location_id) == location_id,
                        col(VenueShape.kind).in_(LINKABLE_KINDS),
                    )
                    .order_by(
                        col(VenueShape.sort_order),
                        col(VenueShape.created_at),
                        col(VenueShape.id),
                    )
                )
            )
            .tuples()
            .all()
        )

        # (plan, marker id, shape, x, y) per placement.
        placed: list[
            tuple[VenuePlan, uuid.UUID | None, VenueShape | None, float, float]
        ] = [
            (plan, marker.id, None, marker.x, marker.y) for marker, plan in marker_rows
        ]
        with_marker = {plan.id for plan, *_ in placed}
        for shape, plan in shape_rows:
            if plan.id in with_marker:
                continue
            with_marker.add(plan.id)
            x, y = shape_anchor(shape.kind, shape.points)
            placed.append((plan, None, shape, x, y))
        if not placed:
            return []

        counts = dict(
            (
                await session.execute(
                    select(col(VenueShape.plan_id), func.count())
                    .where(col(VenueShape.plan_id).in_({p.id for p, *_ in placed}))
                    .group_by(col(VenueShape.plan_id))
                )
            )
            .tuples()
            .all()
        )
        placed.sort(
            key=lambda row: (row[0].sort_order, row[0].created_at, str(row[0].id))
        )
        return [
            LocationPin(
                plan_id=plan.id,
                plan_name=plan.name,
                marker_id=marker_id,
                shape_id=shape.id if shape is not None else None,
                image_etag=plan.image_etag,
                image_width=plan.image_width,
                image_height=plan.image_height,
                canvas_width=plan.canvas_width,
                canvas_height=plan.canvas_height,
                shapes_revision=plan.shapes_revision,
                shape_count=counts.get(plan.id, 0),
                x=x,
                y=y,
            )
            for plan, marker_id, shape, x, y in placed
        ]


location = CRUDLocation()
