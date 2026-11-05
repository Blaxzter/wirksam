"""Generate iCalendar (.ics) feeds from user bookings."""
# pyright: reportUnknownMemberType=false

import datetime as dt
from collections.abc import Sequence
from zoneinfo import ZoneInfo

from icalendar import Alarm, Calendar, Event  # type: ignore[import-untyped]

from app.core.config import settings
from app.logic.work_hours import shift_ends_at
from app.models.booking import Booking


def build_calendar(
    bookings: Sequence[Booking],
    reminder_offsets: Sequence[int] | None = None,
) -> bytes:
    """Convert confirmed bookings into an iCalendar byte string.

    Each booking with a linked shift becomes a VEVENT.
    Shifts without times become all-day events.

    Times are written in the zone of the shift's event, with a VTIMEZONE saying
    what that zone is, so a calendar app in another zone shows the real moment.
    Floating times would put a 10:00 shift in Lisbon at 10:00 wherever the phone
    happens to be. A task without an event uses the setting.
    """
    cal = Calendar()
    cal.add("prodid", "-//WirkSam//Duty Bookings//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", "WirkSam Bookings")

    timed_dates: list[dt.date] = []

    for booking in bookings:
        if booking.status != "confirmed":
            continue

        shift = booking.shift
        if shift is None:
            continue

        event = Event()
        event.add("uid", f"booking-{booking.id}@wirksam")

        # Build summary: "Task Name: Shift Title" or just "Shift Title"
        task_name = getattr(shift, "task", None) and shift.task.name
        summary = f"{task_name}: {shift.title}" if task_name else shift.title
        event.add("summary", summary)

        # Date/time handling
        if shift.start_time is not None:
            db_event = getattr(getattr(shift, "task", None), "event", None)
            zone = ZoneInfo(db_event.timezone if db_event else settings.EVENT_TIMEZONE)
            dtstart = dt.datetime.combine(shift.date, shift.start_time, tzinfo=zone)
            event.add("dtstart", dtstart)
            if shift.end_time is not None:
                # An end before the start is the next morning, as hours count it.
                dtend = shift_ends_at(shift.date, shift.start_time, shift.end_time)
                event.add("dtend", dtend.replace(tzinfo=zone))
            else:
                # Default 1-hour duration when only start time is set
                event.add("dtend", dtstart + dt.timedelta(hours=1))
            timed_dates.append(shift.date)
        else:
            # All-day event (DATE value type)
            event.add("dtstart", shift.date)
            event.add("dtend", shift.date + dt.timedelta(days=1))

        if shift.location:
            event.add("location", shift.location)

        # Description
        desc_parts: list[str] = []
        if task_name:
            desc_parts.append(task_name)
        if shift.category:
            desc_parts.append(shift.category)
        if booking.notes:
            desc_parts.append(booking.notes)
        desc_parts.append("Booked via WirkSam")
        event.add("description", "\n".join(desc_parts))

        event.add("status", "CONFIRMED")
        event.add("dtstamp", booking.created_at or dt.datetime.now(dt.timezone.utc))
        if booking.updated_at:
            event.add("last-modified", booking.updated_at)

        # Reminders from user's default offsets (or 1-hour fallback)
        offsets = reminder_offsets if reminder_offsets else [60]
        for offset in offsets:
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", summary)
            alarm.add("trigger", dt.timedelta(minutes=-offset))
            event.add_component(alarm)

        cal.add_component(event)

    if timed_dates:
        # Only the stretch these shifts need: the default spans 1970 to 2038,
        # which a phone would download again on every refresh.
        cal.add_missing_timezones(
            first_date=min(timed_dates) - dt.timedelta(days=1),
            last_date=max(timed_dates) + dt.timedelta(days=2),
        )

    return cal.to_ical()
