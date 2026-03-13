from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel import col

from app.api.deps import CurrentSuperuser, DBDep
from app.core.errors import raise_problem
from app.crud.duty_slot import duty_slot as crud_duty_slot
from app.crud.event import event as crud_event
from app.crud.event_group import event_group as crud_event_group
from app.crud.slot_batch import slot_batch as crud_slot_batch
from app.logic.slot_generator import generate_duty_slots
from app.models.duty_slot import DutySlot
from app.models.slot_batch import SlotBatch
from app.schemas.duty_slot import DutySlotCreate
from app.schemas.event import (
    AddSlotsResponse,
    AddSlotsToEvent,
    AffectedBookingInfo,
    EventCreate,
    EventCreateWithSlots,
    EventCreateWithSlotsResponse,
    EventRead,
    EventUpdateWithSlots,
    SlotRegenerationResult,
)
from app.schemas.event_group import EventGroupRead
from app.schemas.slot_batch import SlotBatchCreate

router = APIRouter()


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

    # Store generation config on the event (kept for backwards compat)
    db_event.slot_duration_minutes = payload.schedule.slot_duration_minutes
    db_event.default_start_time = payload.schedule.default_start_time
    db_event.default_end_time = payload.schedule.default_end_time
    db_event.people_per_slot = payload.schedule.people_per_slot
    db_event.schedule_overrides = [o.model_dump(mode="json") for o in payload.schedule.overrides]
    session.add(db_event)
    await session.flush()

    # 3. Create a SlotBatch to store the generation config
    batch_in = SlotBatchCreate(
        event_id=db_event.id,
        label=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        location=payload.location,
        category=payload.category,
        default_start_time=payload.schedule.default_start_time,
        default_end_time=payload.schedule.default_end_time,
        slot_duration_minutes=payload.schedule.slot_duration_minutes,
        people_per_slot=payload.schedule.people_per_slot,
        remainder_mode=payload.schedule.remainder_mode,
        schedule_overrides=[o.model_dump(mode="json") for o in payload.schedule.overrides],
    )
    db_batch = await crud_slot_batch.create(session, obj_in=batch_in)

    # 4. Generate and bulk-insert duty slots linked to the batch
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
        slot_in.batch_id = db_batch.id
        await crud_duty_slot.create(session, obj_in=slot_in)

    await session.flush()
    await session.refresh(db_event)

    return EventCreateWithSlotsResponse(
        event=EventRead.model_validate(db_event),
        duty_slots_created=len(slot_creates),
        event_group=event_group_read,
    )


@router.post("/{event_id}/add-slots", response_model=AddSlotsResponse, status_code=201)
async def add_slots_to_event(
    event_id: str,
    payload: AddSlotsToEvent,
    session: DBDep,
    _current_user: CurrentSuperuser,
) -> AddSlotsResponse:
    """Add a new batch of duty slots to an existing event without touching existing slots."""
    db_event = await crud_event.get(session, event_id, raise_404_error=True)

    # Validate dates against event group constraints
    if db_event.event_group_id:
        db_group = await crud_event_group.get(
            session, db_event.event_group_id, raise_404_error=True
        )
        if payload.start_date < db_group.start_date or payload.end_date > db_group.end_date:
            raise_problem(
                400,
                code="dates_outside_event_group",
                detail=(
                    f"Slot dates must fall within the event group date range "
                    f"({db_group.start_date} to {db_group.end_date})"
                ),
            )

    # Create a SlotBatch record
    batch_in = SlotBatchCreate(
        event_id=db_event.id,
        label=payload.location or payload.category or db_event.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        location=payload.location,
        category=payload.category,
        default_start_time=payload.schedule.default_start_time,
        default_end_time=payload.schedule.default_end_time,
        slot_duration_minutes=payload.schedule.slot_duration_minutes,
        people_per_slot=payload.schedule.people_per_slot,
        remainder_mode=payload.schedule.remainder_mode,
        schedule_overrides=[o.model_dump(mode="json") for o in payload.schedule.overrides],
    )
    db_batch = await crud_slot_batch.create(session, obj_in=batch_in)

    slot_creates = generate_duty_slots(
        event_id=db_event.id,
        event_name=db_event.name,
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
        slot_in.batch_id = db_batch.id
        await crud_duty_slot.create(session, obj_in=slot_in)

    await session.flush()
    await session.refresh(db_event)

    return AddSlotsResponse(
        event=EventRead.model_validate(db_event),
        slots_added=len(slot_creates),
    )


@router.post(
    "/{event_id}/regenerate-slots",
    response_model=SlotRegenerationResult,
)
async def regenerate_event_slots(
    event_id: str,
    payload: EventUpdateWithSlots,
    session: DBDep,
    _current_user: CurrentSuperuser,
    dry_run: bool = Query(default=False),
    batch_id: str | None = Query(default=None),
) -> SlotRegenerationResult:
    """Regenerate duty slots for an event, preserving bookings where slots match.

    When dry_run=True, returns a preview without making changes.
    When batch_id is provided, only regenerates slots belonging to that batch.
    Slots are matched by (date, start_time, end_time) — matched slots keep their bookings.
    """
    db_event = await crud_event.get(session, event_id, raise_404_error=True)

    # If batch_id provided, load the batch for defaults
    db_batch: SlotBatch | None = None
    if batch_id:
        db_batch = await crud_slot_batch.get(session, batch_id, raise_404_error=True)
        if str(db_batch.event_id) != str(db_event.id):
            raise_problem(400, code="batch.wrong_event", detail="Batch does not belong to this event")

    # Determine effective event fields (use payload overrides or existing/batch values)
    effective_name = payload.name or db_event.name
    if db_batch:
        effective_start_date = payload.start_date or db_batch.start_date
        effective_end_date = payload.end_date or db_batch.end_date
        effective_location = payload.location if payload.location is not None else db_batch.location
        effective_category = payload.category if payload.category is not None else db_batch.category
    else:
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

    # 2. Load existing slots with their bookings (scoped to batch if provided)
    stmt = (
        select(DutySlot)
        .where(col(DutySlot.event_id) == db_event.id)
        .options(selectinload(DutySlot.bookings))  # type: ignore[arg-type]
    )
    if batch_id:
        stmt = stmt.where(col(DutySlot.batch_id) == batch_id)
    result = await session.execute(stmt)
    existing_slots = list(result.scalars().all())

    # 3. Build lookup of existing slots by (date, start_time, end_time)
    existing_lookup: dict[tuple[Any, ...], DutySlot] = {}
    for slot in existing_slots:
        key = (slot.date, slot.start_time, slot.end_time)
        existing_lookup[key] = slot

    # 4. Match new slots to existing
    matched_keys: set[tuple[Any, ...]] = set()
    slots_to_create: list[DutySlotCreate] = []
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
    slots_to_delete: list[DutySlot] = []
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
        # 6a. Update event fields (only when not scoped to a batch)
        if not batch_id:
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

            # Store generation config on event
            db_event.slot_duration_minutes = payload.schedule.slot_duration_minutes
            db_event.default_start_time = payload.schedule.default_start_time
            db_event.default_end_time = payload.schedule.default_end_time
            db_event.people_per_slot = payload.schedule.people_per_slot
            db_event.schedule_overrides = [
                o.model_dump(mode="json") for o in payload.schedule.overrides
            ]
            session.add(db_event)

        # 6b. Update batch record if scoped
        if db_batch:
            db_batch.start_date = effective_start_date
            db_batch.end_date = effective_end_date
            db_batch.location = effective_location
            db_batch.category = effective_category
            db_batch.default_start_time = payload.schedule.default_start_time
            db_batch.default_end_time = payload.schedule.default_end_time
            db_batch.slot_duration_minutes = payload.schedule.slot_duration_minutes
            db_batch.people_per_slot = payload.schedule.people_per_slot
            db_batch.remainder_mode = payload.schedule.remainder_mode
            db_batch.schedule_overrides = [
                o.model_dump(mode="json") for o in payload.schedule.overrides
            ]
            session.add(db_batch)

        # 6c. Delete unmatched slots (cascade deletes bookings)
        for slot in slots_to_delete:
            await session.delete(slot)

        # 6d. Create new slots (linked to batch if scoped)
        for slot_in in slots_to_create:
            if batch_id and db_batch:
                slot_in.batch_id = db_batch.id
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
