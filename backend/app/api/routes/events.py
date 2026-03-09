from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentSuperuser, CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.duty_slot import duty_slot as crud_duty_slot
from app.crud.event import event as crud_event
from app.crud.event_group import event_group as crud_event_group
from app.logic.slot_generator import generate_duty_slots
from app.models.duty_slot import DutySlot
from app.models.event import Event
from app.schemas.event import (
    AffectedBookingInfo,
    EventCreate,
    EventCreateWithSlots,
    EventCreateWithSlotsResponse,
    EventListResponse,
    EventRead,
    EventStatus,
    EventUpdate,
    EventUpdateWithSlots,
    SlotRegenerationResult,
)
from app.schemas.event_group import EventGroupRead

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/", response_model=EventListResponse)
async def list_events(
    session: DBDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    search: str | None = None,
    status: EventStatus | None = None,
) -> EventListResponse:
    """List published events (all users) or all events (admin)."""
    effective_status = status
    if not current_user.is_admin and effective_status is None:
        effective_status = "published"

    items = await crud_event.get_multi_filtered(
        session, skip=skip, limit=limit, search=search, status=effective_status
    )
    total = await crud_event.get_count_filtered(
        session, search=search, status=effective_status
    )
    return EventListResponse(
        items=[EventRead.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{event_id}", response_model=EventRead)
async def get_event(
    event_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> Event:
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    if not current_user.is_admin and db_event.status != "published":
        raise_problem(403, code="event.not_published", detail="Event is not published")
    return db_event


@router.post("/", response_model=EventRead, status_code=201)
async def create_event(
    event_in: EventCreate,
    session: DBDep,
    current_user: CurrentSuperuser,
) -> Event:
    event_in.created_by_id = current_user.id
    return await crud_event.create(session, obj_in=event_in)


@router.post("/with-slots", response_model=EventCreateWithSlotsResponse, status_code=201)
async def create_event_with_slots(
    payload: EventCreateWithSlots,
    session: DBDep,
    current_user: CurrentSuperuser,
) -> EventCreateWithSlotsResponse:
    """Create an event with auto-generated duty slots in a single transaction."""
    # 1. Optionally create a new event group
    event_group_read: EventGroupRead | None = None
    event_group_id = payload.event_group_id

    if payload.new_event_group:
        payload.new_event_group.created_by_id = current_user.id
        db_group = await crud_event_group.create(session, obj_in=payload.new_event_group)
        event_group_id = db_group.id
        event_group_read = EventGroupRead.model_validate(db_group)

    # 2. Create the event with generation config stored
    event_in = EventCreate(
        name=payload.name,
        description=payload.description,
        start_date=payload.start_date,
        end_date=payload.end_date,
        location=payload.location,
        category=payload.category,
        event_group_id=event_group_id,
        created_by_id=current_user.id,
    )
    db_event = await crud_event.create(session, obj_in=event_in)

    # Store generation config on the event
    db_event.slot_duration_minutes = payload.schedule.slot_duration_minutes
    db_event.default_start_time = payload.schedule.default_start_time
    db_event.default_end_time = payload.schedule.default_end_time
    db_event.people_per_slot = payload.schedule.people_per_slot
    db_event.schedule_overrides = [o.model_dump(mode="json") for o in payload.schedule.overrides]
    session.add(db_event)
    await session.flush()

    # 3. Generate and bulk-insert duty slots
    slot_creates = generate_duty_slots(
        event_id=db_event.id,
        event_name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        default_start_time=payload.schedule.default_start_time,
        default_end_time=payload.schedule.default_end_time,
        slot_duration_minutes=payload.schedule.slot_duration_minutes,
        people_per_slot=payload.schedule.people_per_slot,
        remainder_mode=payload.schedule.remainder_mode,
        location=payload.location,
        category=payload.category,
        overrides=payload.schedule.overrides,
        excluded_slots=payload.schedule.excluded_slots,
    )

    for slot_in in slot_creates:
        await crud_duty_slot.create(session, obj_in=slot_in)

    await session.flush()
    await session.refresh(db_event)

    return EventCreateWithSlotsResponse(
        event=EventRead.model_validate(db_event),
        duty_slots_created=len(slot_creates),
        event_group=event_group_read,
    )


@router.post(
    "/{event_id}/regenerate-slots",
    response_model=SlotRegenerationResult,
)
async def regenerate_event_slots(
    event_id: str,
    payload: EventUpdateWithSlots,
    session: DBDep,
    current_user: CurrentSuperuser,
    dry_run: bool = Query(default=False),
) -> SlotRegenerationResult:
    """Regenerate duty slots for an event, preserving bookings where slots match.

    When dry_run=True, returns a preview without making changes.
    Slots are matched by (date, start_time, end_time) — matched slots keep their bookings.
    """
    db_event = await crud_event.get(session, event_id, raise_404_error=True)

    # Determine effective event fields (use payload overrides or existing values)
    effective_name = payload.name or db_event.name
    effective_start_date = payload.start_date or db_event.start_date
    effective_end_date = payload.end_date or db_event.end_date
    effective_location = payload.location if payload.location is not None else db_event.location
    effective_category = payload.category if payload.category is not None else db_event.category

    # 1. Generate new slot definitions
    new_slot_defs = generate_duty_slots(
        event_id=db_event.id,
        event_name=effective_name,
        start_date=effective_start_date,
        end_date=effective_end_date,
        default_start_time=payload.schedule.default_start_time,
        default_end_time=payload.schedule.default_end_time,
        slot_duration_minutes=payload.schedule.slot_duration_minutes,
        people_per_slot=payload.schedule.people_per_slot,
        remainder_mode=payload.schedule.remainder_mode,
        location=effective_location,
        category=effective_category,
        overrides=payload.schedule.overrides,
        excluded_slots=payload.schedule.excluded_slots,
    )

    # 2. Load existing slots with their bookings
    stmt = (
        select(DutySlot)
        .where(DutySlot.event_id == db_event.id)
        .options(selectinload(DutySlot.bookings))
    )
    result = await session.execute(stmt)
    existing_slots = list(result.scalars().all())

    # 3. Build lookup of existing slots by (date, start_time, end_time)
    existing_lookup: dict[tuple, DutySlot] = {}
    for slot in existing_slots:
        key = (slot.date, slot.start_time, slot.end_time)
        existing_lookup[key] = slot

    # 4. Match new slots to existing
    matched_keys: set[tuple] = set()
    slots_to_create = []
    for new_slot in new_slot_defs:
        key = (new_slot.date, new_slot.start_time, new_slot.end_time)
        if key in existing_lookup:
            matched_keys.add(key)
            # Update title and max_bookings on matched slots
            existing = existing_lookup[key]
            existing.title = new_slot.title
            existing.max_bookings = new_slot.max_bookings
            existing.location = new_slot.location
            existing.category = new_slot.category
        else:
            slots_to_create.append(new_slot)

    # 5. Find unmatched existing slots (to be deleted) and their confirmed bookings
    affected_bookings: list[AffectedBookingInfo] = []
    slots_to_delete = []
    for key, slot in existing_lookup.items():
        if key not in matched_keys:
            slots_to_delete.append(slot)
            for booking in slot.bookings:
                if booking.status == "confirmed":
                    affected_bookings.append(
                        AffectedBookingInfo(
                            booking_id=booking.id,
                            user_id=booking.user_id,
                            slot_title=slot.title,
                            slot_date=slot.date,
                            slot_start_time=slot.start_time,
                            slot_end_time=slot.end_time,
                        )
                    )

    if not dry_run:
        # 6a. Update event fields
        if payload.name is not None:
            db_event.name = payload.name
        if payload.description is not None:
            db_event.description = payload.description
        if payload.start_date is not None:
            db_event.start_date = payload.start_date
        if payload.end_date is not None:
            db_event.end_date = payload.end_date
        if payload.location is not None:
            db_event.location = payload.location
        if payload.category is not None:
            db_event.category = payload.category

        # Store generation config
        db_event.slot_duration_minutes = payload.schedule.slot_duration_minutes
        db_event.default_start_time = payload.schedule.default_start_time
        db_event.default_end_time = payload.schedule.default_end_time
        db_event.people_per_slot = payload.schedule.people_per_slot
        db_event.schedule_overrides = [
            o.model_dump(mode="json") for o in payload.schedule.overrides
        ]
        session.add(db_event)

        # 6b. Delete unmatched slots (cascade deletes bookings)
        for slot in slots_to_delete:
            await session.delete(slot)

        # 6c. Create new slots
        for slot_in in slots_to_create:
            await crud_duty_slot.create(session, obj_in=slot_in)

        await session.flush()
        await session.refresh(db_event)

    return SlotRegenerationResult(
        event=EventRead.model_validate(db_event),
        slots_added=len(slots_to_create),
        slots_removed=len(slots_to_delete),
        slots_kept=len(matched_keys),
        affected_bookings=affected_bookings,
    )


@router.patch("/{event_id}", response_model=EventRead)
async def update_event(
    event_id: str,
    event_in: EventUpdate,
    session: DBDep,
    _current_user: CurrentSuperuser,
) -> Event:
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    return await crud_event.update(session, db_obj=db_event, obj_in=event_in)


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    session: DBDep,
    _current_user: CurrentSuperuser,
) -> None:
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    await session.delete(db_event)
    await session.commit()
