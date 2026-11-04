"""Generate duty shifts from a schedule configuration."""

import re
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

from app.schemas.shift import ShiftCreate
from app.schemas.task import ExcludedShift, ScheduleOverride

_TIME_RANGE = re.compile(r" \d{2}:\d{2}-\d{2}:\d{2}")


def shift_title(task_name: str, start: time, end: time) -> str:
    """A generated shift's title: the task's name and the shift's times."""
    return f"{task_name} {start.strftime('%H:%M')}-{end.strftime('%H:%M')}"


def renamed_shift_title(title: str, *, old_name: str, new_name: str) -> str | None:
    """The title a shift takes when its task is renamed, or ``None`` to keep it.

    Only a title ``shift_title`` wrote follows the task: the old name and a time
    range. Any other title was typed by someone ("Late shift") and stays. The
    times are not compared with the shift's own, so a generated shift that was
    moved later still follows.
    """
    if not old_name or not title.startswith(old_name):
        return None
    rest = title[len(old_name) :]
    if not _TIME_RANGE.fullmatch(rest):
        return None
    return new_name + rest


def generate_shifts(
    *,
    task_id: uuid.UUID,
    task_name: str,
    start_date: date,
    end_date: date,
    default_start_time: time,
    default_end_time: time,
    shift_duration_minutes: int,
    people_per_shift: int = 1,
    remainder_mode: str = "drop",
    location: str | None = None,
    location_id: uuid.UUID | None = None,
    category: str | None = None,
    overrides: list[ScheduleOverride] | None = None,
    excluded_shifts: list[ExcludedShift] | None = None,
    specific_dates: list[date] | None = None,
) -> list[ShiftCreate]:
    """Generate a list of ShiftCreate objects for each time shift.

    Iterates each date in [start_date, end_date], splits each day's time range
    into shifts of shift_duration_minutes, and returns the full list.
    Per-date overrides can specify different start/end times for specific dates.

    When specific_dates is a non-empty list, only those dates produce shifts and
    every other day in the span is skipped. An empty list or None means no
    restriction, which mirrors the frontend preview in useShiftPreview.ts.
    """
    override_map: dict[date, ScheduleOverride] = {}
    if overrides:
        for o in overrides:
            override_map[o.date] = o

    # Empty means "no filter", not "no days" — see ShiftGenerationConfig.
    date_filter: set[date] | None = set(specific_dates) if specific_dates else None

    # Build exclusion set for fast lookup
    exclusion_set: set[tuple[date, time, time]] = set()
    if excluded_shifts:
        for ex in excluded_shifts:
            exclusion_set.add((ex.date, ex.start_time, ex.end_time))

    shifts: list[ShiftCreate] = []
    current_date = start_date
    duration = timedelta(minutes=shift_duration_minutes)

    while current_date <= end_date:
        if date_filter is not None and current_date not in date_filter:
            current_date += timedelta(days=1)
            continue

        override = override_map.get(current_date)
        day_start = override.start_time if override else default_start_time
        day_end = override.end_time if override else default_end_time

        shifts.extend(
            _generate_shifts_for_day(
                task_id=task_id,
                task_name=task_name,
                slot_date=current_date,
                day_start=day_start,
                day_end=day_end,
                duration=duration,
                people_per_shift=people_per_shift,
                remainder_mode=remainder_mode,
                location=location,
                location_id=location_id,
                category=category,
            )
        )
        current_date += timedelta(days=1)

    # Filter out excluded shifts
    if exclusion_set:
        shifts = [
            s for s in shifts if (s.date, s.start_time, s.end_time) not in exclusion_set
        ]

    return shifts


def _generate_shifts_for_day(
    *,
    task_id: uuid.UUID,
    task_name: str,
    slot_date: date,
    day_start: time,
    day_end: time,
    duration: timedelta,
    people_per_shift: int,
    remainder_mode: str = "drop",
    location: str | None,
    location_id: uuid.UUID | None = None,
    category: str | None,
) -> list[ShiftCreate]:
    """Generate shifts for a single day."""
    # Copied onto every shift of the day, exactly like the task/batch values.
    shared: dict[str, Any] = {
        "task_id": task_id,
        "location": location,
        "location_id": location_id,
        "category": category,
        "max_bookings": people_per_shift,
    }
    # Use a reference date to do time arithmetic
    ref = date(2000, 1, 1)
    start_dt = _combine(ref, day_start)
    end_dt = _combine(ref, day_end)

    shifts: list[ShiftCreate] = []
    current = start_dt

    while current + duration <= end_dt:
        slot_end = current + duration
        slot_start_time = current.time()
        slot_end_time = slot_end.time()

        title = shift_title(task_name, slot_start_time, slot_end_time)

        shifts.append(
            ShiftCreate(
                title=title,
                date=slot_date,
                start_time=slot_start_time,
                end_time=slot_end_time,
                **shared,
            )
        )
        current = slot_end

    # Handle remaining time that doesn't fill a full shift
    if current < end_dt:
        if remainder_mode == "short":
            # Create a shorter final shift for the remaining time
            slot_start_time = current.time()
            slot_end_time = end_dt.time()
            title = shift_title(task_name, slot_start_time, slot_end_time)
            shifts.append(
                ShiftCreate(
                    title=title,
                    date=slot_date,
                    start_time=slot_start_time,
                    end_time=slot_end_time,
                    **shared,
                )
            )
        elif remainder_mode == "extend" and shifts:
            # Extend the last shift to cover the remaining time
            last = shifts[-1]
            last.end_time = end_dt.time()
            if last.start_time and last.end_time:
                last.title = shift_title(task_name, last.start_time, last.end_time)
        # remainder_mode == "drop": do nothing (default)

    return shifts


def _combine(d: date, t: time) -> datetime:
    """Combine date and time into a datetime for arithmetic."""
    return datetime.combine(d, t)
