"""Venue plans, markers and the member map view (#185).

The map is **member-only**. A non-member gets a 404 even on a public event, so
nothing here can be used to probe a plan, a marker or an image by id. That is
:func:`require_event_visible` plus "no role → 404" inline, rather than a third
permission gate, so the two gates in ``logic/permissions.py`` stay the only
ones.

Plan images are served by an authenticated GET with ``Cache-Control: private``;
the frontend fetches them with its bearer token and shows a blob URL. There are
no public image URLs.
"""

import datetime as dt
import uuid
from typing import NoReturn

from fastapi import APIRouter, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlmodel import col

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.event import event as crud_event
from app.crud.location import location as crud_location
from app.crud.venue_map import venue_map as crud_venue_map
from app.logic.images import MAX_INPUT_BYTES, ImageProcessingError
from app.logic.locations import resolve_location
from app.logic.permissions import require_event_role, require_event_visible
from app.logic.venue_map import normalize_plan_image
from app.models.booking import Booking
from app.models.event import Event
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.models.venue_plan import VenueMarker, VenuePlan
from app.schemas.event_membership import EventRole
from app.schemas.location import LocationRead
from app.schemas.venue_map import (
    MARKER_LOCATION_REQUIRED,
    VenueMapRead,
    VenueMarkerCreate,
    VenueMarkerRead,
    VenueMarkerUpdate,
    VenuePlanCreate,
    VenuePlanOrder,
    VenuePlanRead,
    VenuePlanUpdate,
    marker_kind_mismatch,
)

router = APIRouter(tags=["venue-map"])

# The image URL carries ``?v=<etag>``, so a new upload is a new URL; a week of
# private caching is safe and keeps re-opening the map cheap.
_IMAGE_CACHE_CONTROL = "private, max-age=604800"


# ── Gates ──────────────────────────────────────────────────────────────────


async def _member_event(
    user: User, session: DBDep, event_id: uuid.UUID
) -> tuple[Event, EventRole]:
    """Load the event and require membership; anyone else gets a 404."""
    event = await crud_event.get(session, event_id, raise_404_error=True)
    role = await require_event_visible(user, session, event)
    if role is None:
        # Visible (public + published) but not a member: the map is not theirs
        # to see, and a 403 would confirm the thing they asked about exists.
        raise_problem(404, code="event.not_found", detail="Event not found")
    return event, role


async def _admin_event(user: User, session: DBDep, event_id: uuid.UUID) -> Event:
    """Members who are not admins get 403; non-members get 404 as above."""
    event, _ = await _member_event(user, session, event_id)
    await require_event_role(user, session, event.id, minimum="admin")
    return event


async def _load_plan(session: DBDep, plan_id: uuid.UUID) -> VenuePlan:
    plan = await crud_venue_map.get_plan(session, plan_id=plan_id)
    if plan is None:
        raise_problem(404, code="venue_plan.not_found", detail="Venue plan not found")
    return plan


async def _load_marker(session: DBDep, marker_id: uuid.UUID) -> VenueMarker:
    marker = await crud_venue_map.get_marker(session, marker_id=marker_id)
    if marker is None:
        raise_problem(
            404, code="venue_marker.not_found", detail="Venue marker not found"
        )
    return marker


async def _plan_read(session: DBDep, plan: VenuePlan) -> VenuePlanRead:
    markers = await crud_venue_map.list_markers_for_plans(session, plan_ids=[plan.id])
    return VenuePlanRead.model_validate(plan).model_copy(
        update={"markers": [VenueMarkerRead.model_validate(m) for m in markers]}
    )


async def _check_marker_location(
    session: DBDep,
    *,
    plan: VenuePlan,
    location_id: uuid.UUID | None,
    exclude_marker_id: uuid.UUID | None = None,
) -> None:
    """The location must be of the plan's event and not already on this plan."""
    if location_id is None:
        return
    await resolve_location(session, event_id=plan.event_id, location_id=location_id)
    clash = await crud_venue_map.get_marker_for_location(
        session,
        plan_id=plan.id,
        location_id=location_id,
        exclude_id=exclude_marker_id,
    )
    if clash is not None:
        _raise_duplicate_location()


def _raise_duplicate_location() -> NoReturn:
    raise_problem(
        409,
        code="venue_marker.duplicate_location",
        detail="This location is already on this plan",
    )


# ── Member map view ────────────────────────────────────────────────────────


@router.get("/events/{event_id}/venue-map", response_model=VenueMapRead)
async def get_venue_map(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    on: dt.date | None = None,
) -> VenueMapRead:
    """Everything the map screen needs in one call.

    Plans in display order with their markers, every location of the event,
    and the locations of the caller's own confirmed bookings on ``on``
    (default: today) so the map can highlight where they are needed.
    """
    event, _ = await _member_event(current_user, session, event_id)
    day = on or dt.date.today()

    plans = await crud_venue_map.list_plans_with_markers(session, event_id=event.id)
    locations = await crud_location.list_for_event(session, event_id=event.id)

    result = await session.execute(
        select(col(Shift.location_id))
        .join(Booking, col(Booking.shift_id) == col(Shift.id))
        .join(Task, col(Task.id) == col(Shift.task_id))
        .where(
            col(Booking.user_id) == current_user.id,
            col(Booking.status) == "confirmed",
            col(Shift.date) == day,
            col(Task.event_id) == event.id,
            col(Shift.location_id).is_not(None),
        )
        .distinct()
    )
    my_location_ids = sorted(
        (loc_id for loc_id in result.scalars().all() if loc_id is not None),
        key=str,
    )

    return VenueMapRead(
        event_id=event.id,
        on=day,
        plans=plans,
        locations=[LocationRead.model_validate(loc) for loc in locations],
        my_location_ids=my_location_ids,
    )


# ── Plans ──────────────────────────────────────────────────────────────────


@router.post(
    "/events/{event_id}/venue-plans",
    response_model=VenuePlanRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_venue_plan(
    event_id: uuid.UUID,
    body: VenuePlanCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> VenuePlanRead:
    """Add an (image-less) plan after the event's existing ones."""
    event = await _admin_event(current_user, session, event_id)
    plan = await crud_venue_map.create_plan(session, event_id=event.id, name=body.name)
    return VenuePlanRead.model_validate(plan)


@router.put("/events/{event_id}/venue-plans/order", response_model=list[VenuePlanRead])
async def reorder_venue_plans(
    event_id: uuid.UUID,
    body: VenuePlanOrder,
    session: DBDep,
    current_user: CurrentUser,
) -> list[VenuePlanRead]:
    """Set the display order. ``plan_ids`` must name every plan exactly once."""
    event = await _admin_event(current_user, session, event_id)
    try:
        await crud_venue_map.reorder(session, event_id=event.id, plan_ids=body.plan_ids)
    except ValueError:
        raise_problem(
            422,
            code="venue_plan.order_mismatch",
            detail="The list must contain every plan of this event exactly once",
        )
    return await crud_venue_map.list_plans_with_markers(session, event_id=event.id)


@router.patch("/venue-plans/{plan_id}", response_model=VenuePlanRead)
async def update_venue_plan(
    plan_id: uuid.UUID,
    body: VenuePlanUpdate,
    session: DBDep,
    current_user: CurrentUser,
) -> VenuePlanRead:
    plan = await _load_plan(session, plan_id)
    await _admin_event(current_user, session, plan.event_id)
    if body.name is not None:
        plan = await crud_venue_map.rename_plan(session, plan=plan, name=body.name)
    return await _plan_read(session, plan)


@router.delete("/venue-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_venue_plan(
    plan_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Delete a plan together with its image and markers."""
    plan = await _load_plan(session, plan_id)
    await _admin_event(current_user, session, plan.event_id)
    await crud_venue_map.delete_plan(session, plan=plan)


# ── Plan image ─────────────────────────────────────────────────────────────


@router.put("/venue-plans/{plan_id}/image", response_model=VenuePlanRead)
async def upload_venue_plan_image(
    plan_id: uuid.UUID,
    file: UploadFile,
    session: DBDep,
    current_user: CurrentUser,
) -> VenuePlanRead:
    """Upload or replace a plan's image.

    It is shrunk to fit 2560 px, re-encoded as WebP and stored in the database.
    Markers keep their normalised coordinates, so replacing a plan with a
    redrawn version of the same venue leaves them where they were.

    Refused in a demo event and for a demo guest anywhere (they can create
    events of their own): every other map edit is open to a sandbox guest so
    they can try the editor, but an anonymous visitor uploading arbitrary
    images into our database is not something a demo needs.
    """
    plan = await _load_plan(session, plan_id)
    event = await _admin_event(current_user, session, plan.event_id)
    if event.is_sandbox or current_user.is_sandbox:
        raise_problem(
            403,
            code="sandbox.upload_disabled",
            detail="Images cannot be uploaded in a demo event",
        )

    if file.size is not None and file.size > MAX_INPUT_BYTES:
        raise_problem(
            400,
            code="venue_plan.invalid_image",
            detail="Image exceeds 20 MB upload limit",
        )
    raw = await file.read()
    try:
        # Decoding is CPU-bound and can take seconds; keep it off the loop.
        image = await run_in_threadpool(normalize_plan_image, raw)
    except ImageProcessingError as exc:
        raise_problem(400, code="venue_plan.invalid_image", detail=str(exc))

    await crud_venue_map.upsert_image(session, plan=plan, image=image)
    await session.refresh(plan)
    return await _plan_read(session, plan)


@router.get(
    "/venue-plans/{plan_id}/image",
    response_class=Response,
    responses={
        200: {"content": {"image/webp": {}}, "description": "The plan image"},
        304: {"description": "Not modified"},
    },
)
async def get_venue_plan_image(
    plan_id: uuid.UUID,
    request: Request,
    session: DBDep,
    current_user: CurrentUser,
) -> Response:
    """Serve a plan's image bytes to members of its event."""
    plan = await _load_plan(session, plan_id)
    await _member_event(current_user, session, plan.event_id)
    image = await crud_venue_map.get_image(session, plan_id=plan.id)
    if image is None:
        raise_problem(
            404, code="venue_plan.image_not_found", detail="This plan has no image"
        )

    etag_header = f'"{image.etag}"'
    headers = {"ETag": etag_header, "Cache-Control": _IMAGE_CACHE_CONTROL}
    if request.headers.get("if-none-match") == etag_header:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=image.data, media_type=image.content_type, headers=headers)


# ── Markers ────────────────────────────────────────────────────────────────


@router.post(
    "/venue-plans/{plan_id}/markers",
    response_model=VenueMarkerRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_venue_marker(
    plan_id: uuid.UUID,
    body: VenueMarkerCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> VenueMarkerRead:
    """Place a marker. A location may appear once per plan."""
    plan = await _load_plan(session, plan_id)
    await _admin_event(current_user, session, plan.event_id)
    await _check_marker_location(session, plan=plan, location_id=body.location_id)
    try:
        # A savepoint, so losing a race on the unique constraint leaves the
        # request's transaction usable for the 409.
        async with session.begin_nested():
            marker = await crud_venue_map.create_marker(
                session, plan_id=plan.id, data=body
            )
    except IntegrityError:
        _raise_duplicate_location()
    return VenueMarkerRead.model_validate(marker)


@router.patch("/venue-markers/{marker_id}", response_model=VenueMarkerRead)
async def update_venue_marker(
    marker_id: uuid.UUID,
    body: VenueMarkerUpdate,
    session: DBDep,
    current_user: CurrentUser,
) -> VenueMarkerRead:
    """Move, relabel or re-kind a marker.

    ``kind``, ``x`` and ``y`` cannot be cleared, so an explicit ``null`` for
    them is ignored. The kind/location pairing is checked on the merged row.
    """
    marker = await _load_marker(session, marker_id)
    plan = await _load_plan(session, marker.plan_id)
    await _admin_event(current_user, session, plan.event_id)

    fields = body.model_fields_set
    kind = body.kind if "kind" in fields and body.kind is not None else marker.kind
    location_id = body.location_id if "location_id" in fields else marker.location_id
    if marker_kind_mismatch(kind, location_id):
        raise_problem(
            422,
            code=MARKER_LOCATION_REQUIRED,
            detail="A location marker needs a location, and only a location marker may have one",
        )
    if location_id != marker.location_id:
        await _check_marker_location(
            session,
            plan=plan,
            location_id=location_id,
            exclude_marker_id=marker.id,
        )

    marker.kind = kind
    marker.location_id = location_id
    if "label" in fields:
        marker.label = body.label
    if body.x is not None:
        marker.x = body.x
    if body.y is not None:
        marker.y = body.y
    marker.updated_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    session.add(marker)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        _raise_duplicate_location()
    await session.refresh(marker)
    return VenueMarkerRead.model_validate(marker)


@router.delete("/venue-markers/{marker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_venue_marker(
    marker_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    marker = await _load_marker(session, marker_id)
    plan = await _load_plan(session, marker.plan_id)
    await _admin_event(current_user, session, plan.event_id)
    await session.delete(marker)
    await session.flush()
