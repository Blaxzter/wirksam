"""Generate duty slots from a schedule configuration."""

import uuid
from datetime import date, time, timedelta

from app.schemas.duty_slot import DutySlotCreate
from app.schemas.event import ExcludedSlot, ScheduleOverride


def generate_duty_slots(
    *,
    event_id: uuid.UUID,
    event_name: str,
    start_date: date,
    end_date: date,
    default_start_time: time,
    default_end_time: time,
    slot_duration_minutes: int,
    people_per_slot: int = 1,
    remainder_mode: str = "drop",
    location: str | None = None,
    category: str | None = None,
    overrides: list[ScheduleOverride] | None = None,
    excluded_slots: list[ExcludedSlot] | None = None,
) -> list[DutySlotCreate]:
    """Generate a list of DutySlotCreate objects for each time slot.

    Iterates each date in [start_date, end_date], splits each day's time range
    into slots of slot_duration_minutes, and returns the full list.
    Per-date overrides can specify different start/end times for specific dates.
    """
    override_map: dict[date, ScheduleOverride] = {}
    if overrides:
        for o in overrides:
            override_map[o.date] = o

    # Build exclusion set for fast lookup
    exclusion_set: set[tuple[date, time, time]] = set()
    if excluded_slots:
        for ex in excluded_slots:
            exclusion_set.add((ex.date, ex.start_time, ex.end_time))

    slots: list[DutySlotCreate] = []
    current_date = start_date
    duration = timedelta(minutes=slot_duration_minutes)

    while current_date <= end_date:
        override = override_map.get(current_date)
        day_start = override.start_time if override else default_start_time
        day_end = override.end_time if override else default_end_time

        slots.extend(
            _generate_slots_for_day(
                event_id=event_id,
                event_name=event_name,
                slot_date=current_date,
                day_start=day_start,
                day_end=day_end,
                duration=duration,
                people_per_slot=people_per_slot,
                remainder_mode=remainder_mode,
                location=location,
                category=category,
            )
        )
        current_date += timedelta(days=1)

    # Filter out excluded slots
    if exclusion_set:
        slots = [
            s
            for s in slots
            if (s.date, s.start_time, s.end_time) not in exclusion_set
        ]

    return slots


def _generate_slots_for_day(
    *,
    event_id: uuid.UUID,
    event_name: str,
    slot_date: date,
    day_start: time,
    day_end: time,
    duration: timedelta,
    people_per_slot: int,
    remainder_mode: str = "drop",
    location: str | None,
    category: str | None,
) -> list[DutySlotCreate]:
    """Generate slots for a single day."""
    # Use a reference date to do time arithmetic
    ref = date(2000, 1, 1)
    start_dt = _combine(ref, day_start)
    end_dt = _combine(ref, day_end)

    slots: list[DutySlotCreate] = []
    current = start_dt

    while current + duration <= end_dt:
        slot_end = current + duration
        slot_start_time = current.time()
        slot_end_time = slot_end.time()

        title = f"{event_name} {slot_start_time.strftime('%H:%M')}-{slot_end_time.strftime('%H:%M')}"

        slots.append(
            DutySlotCreate(
                event_id=event_id,
                title=title,
                date=slot_date,
                start_time=slot_start_time,
                end_time=slot_end_time,
                location=location,
                category=category,
                max_bookings=people_per_slot,
            )
        )
        current = slot_end

    # Handle remaining time that doesn't fill a full slot
    if current < end_dt:
        if remainder_mode == "short":
            # Create a shorter final slot for the remaining time
            slot_start_time = current.time()
            slot_end_time = end_dt.time()
            title = f"{event_name} {slot_start_time.strftime('%H:%M')}-{slot_end_time.strftime('%H:%M')}"
            slots.append(
                DutySlotCreate(
                    event_id=event_id,
                    title=title,
                    date=slot_date,
                    start_time=slot_start_time,
                    end_time=slot_end_time,
                    location=location,
                    category=category,
                    max_bookings=people_per_slot,
                )
            )
        elif remainder_mode == "extend" and slots:
            # Extend the last slot to cover the remaining time
            last = slots[-1]
            last.end_time = end_dt.time()
            last.title = f"{event_name} {last.start_time.strftime('%H:%M')}-{last.end_time.strftime('%H:%M')}"
        # remainder_mode == "drop": do nothing (default)

    return slots


def _combine(d: date, t: time):
    """Combine date and time into a datetime for arithmetic."""
    from datetime import datetime

    return datetime.combine(d, t)
