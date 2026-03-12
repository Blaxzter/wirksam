"""Demo data endpoints for creating/deleting test data.

All demo entities are tagged with a '[DEMO]' prefix so they can be
reliably identified and cleaned up.
"""

import datetime as dt
import random
import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentSuperuser, DBDep
from app.models.booking import Booking
from app.models.duty_slot import DutySlot
from app.models.event import Event
from app.models.event_group import EventGroup
from app.models.user import User
from app.schemas.demo_data import (
    DEMO_PREFIX,
    DemoDataCreatedResponse,
    DemoDataDeletedResponse,
    DemoDataParams,
)

router = APIRouter(prefix="/demo-data", tags=["demo-data"])

DEMO_EVENT_NAMES = [
    "Morning Shift",
    "Afternoon Shift",
    "Night Watch",
    "Weekend Duty",
    "Holiday Coverage",
    "Emergency Standby",
    "Reception Desk",
    "Parking Lot",
    "Main Entrance",
    "VIP Lounge",
    "Info Booth",
    "First Aid Station",
    "Stage Setup",
    "Sound Check",
    "Cleanup Crew",
]

DEMO_GROUP_NAMES = [
    "Summer Festival",
    "Winter Gala",
    "Spring Conference",
    "Autumn Fair",
    "Tech Summit",
    "Community Day",
]

DEMO_LOCATIONS = [
    "Hall A",
    "Hall B",
    "Main Stage",
    "Entrance Gate",
    "Parking Area",
    "VIP Area",
    "Conference Room 1",
    "Conference Room 2",
    "Outdoor Tent",
    "Cafeteria",
]

DEMO_FIRST_NAMES = [
    "Alex",
    "Jordan",
    "Casey",
    "Morgan",
    "Taylor",
    "Riley",
    "Quinn",
    "Avery",
    "Cameron",
    "Dakota",
    "Emery",
    "Finley",
    "Harper",
    "Kendall",
    "Logan",
    "Parker",
    "Reese",
    "Skyler",
    "Sage",
    "Rowan",
]

DEMO_LAST_NAMES = [
    "Mueller",
    "Schmidt",
    "Weber",
    "Fischer",
    "Wagner",
]


@router.post(
    "/",
    response_model=DemoDataCreatedResponse,
)
async def create_demo_data(
    params: DemoDataParams,
    db: DBDep,
    _current_user: CurrentSuperuser,
) -> DemoDataCreatedResponse:
    """Create demo event groups, events, users, and duty slots."""
    rng = random.Random()  # noqa: S311
    today = dt.date.today()
    created_groups: list[EventGroup] = []
    created_events: list[Event] = []
    created_users: list[User] = []
    created_slots: list[DutySlot] = []
    total_bookings = 0

    # --- Event groups ---
    for i in range(params.num_event_groups):
        name = DEMO_GROUP_NAMES[i % len(DEMO_GROUP_NAMES)]
        group_start = today + dt.timedelta(days=rng.randint(0, 2))
        group_end = group_start + dt.timedelta(days=rng.randint(5, 9))
        group = EventGroup(
            name=f"{DEMO_PREFIX} {name}",
            description=f"Auto-generated demo event group #{i + 1}",
            start_date=group_start,
            end_date=group_end,
            status="published" if params.publish_events else "draft",
            created_by_id=_current_user.id,
        )
        db.add(group)
        created_groups.append(group)

    # Flush to get group IDs
    if created_groups:
        await db.flush()

    # --- Events — distribute roughly equally across groups ---
    for i in range(params.num_events):
        event_name = rng.choice(DEMO_EVENT_NAMES)
        day_offset = rng.randint(0, 7)
        event_start = today + dt.timedelta(days=day_offset)

        # Weighted random duration: 1d (50%), 2d (25%), 3d (15%), 4d (10%)
        duration_days = rng.choices([1, 2, 3, 4], weights=[50, 25, 15, 10])[0]
        event_end = event_start + dt.timedelta(days=duration_days - 1)

        # Round-robin group assignment (equal distribution)
        group = created_groups[i % len(created_groups)] if created_groups else None

        event = Event(
            name=f"{DEMO_PREFIX} {event_name}",
            description=f"Auto-generated demo event #{i + 1}",
            start_date=event_start,
            end_date=event_end,
            status="published" if params.publish_events else "draft",
            created_by_id=_current_user.id,
            event_group_id=group.id if group else None,
            location=rng.choice(DEMO_LOCATIONS),
            category="demo",
        )
        db.add(event)
        created_events.append(event)

    # Flush to get event IDs
    if created_events:
        await db.flush()

    # --- Duty slots for each event (randomised count per day) ---
    for event in created_events:
        # Iterate each day of the event
        num_days = (event.end_date - event.start_date).days + 1
        for d in range(num_days):
            slot_date = event.start_date + dt.timedelta(days=d)
            # Random number of slots around the target, ±50 %
            lo = max(1, params.num_slots_per_event // 2)
            hi = max(lo + 1, int(params.num_slots_per_event * 1.5))
            day_slots = rng.randint(lo, hi)
            start_hour = rng.randint(7, 10)
            for s in range(day_slots):
                hour = (start_hour + s) % 23
                slot_start = dt.time(hour=hour)
                slot_end = dt.time(hour=(hour + 1) % 23)
                slot = DutySlot(
                    event_id=event.id,
                    title=f"{DEMO_PREFIX} Slot {s + 1}",
                    description=f"Demo slot {s + 1} for {event.name}",
                    date=slot_date,
                    start_time=slot_start,
                    end_time=slot_end,
                    location=event.location,
                    category="demo",
                    max_bookings=rng.choice([1, 2, 2, 3]),
                )
                db.add(slot)
                created_slots.append(slot)

    # --- Demo users (use example.com — RFC 2606 reserved, always valid) ---
    for i in range(params.num_users):
        first = DEMO_FIRST_NAMES[i % len(DEMO_FIRST_NAMES)]
        last = rng.choice(DEMO_LAST_NAMES)
        user = User(
            auth0_sub=f"demo|{uuid.uuid4().hex[:16]}",
            email=f"{first.lower()}.{last.lower()}.{i}@demo.example.com",
            name=f"{DEMO_PREFIX} {first} {last}",
            is_active=True,
            roles=[],
        )
        db.add(user)
        created_users.append(user)

    # Flush to get user + slot IDs for bookings
    if created_users or created_slots:
        await db.flush()

    # --- Bookings: each demo user books a random subset of slots ---
    if created_users and created_slots:
        # Track confirmed bookings per slot to respect max_bookings
        slot_booking_counts: dict[uuid.UUID, int] = {s.id: 0 for s in created_slots}
        booked_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()

        for user in created_users:
            # Each user books 20-60 % of available slots
            num_to_book = rng.randint(
                max(1, len(created_slots) // 5),
                max(1, len(created_slots) * 3 // 5),
            )
            candidates = rng.sample(
                created_slots, min(num_to_book, len(created_slots))
            )
            for slot in candidates:
                pair = (slot.id, user.id)
                if pair in booked_pairs:
                    continue
                if slot_booking_counts[slot.id] >= slot.max_bookings:
                    continue
                booked_pairs.add(pair)
                slot_booking_counts[slot.id] += 1
                booking = Booking(
                    duty_slot_id=slot.id,
                    user_id=user.id,
                    status="confirmed",
                )
                db.add(booking)
                total_bookings += 1

    return DemoDataCreatedResponse(
        event_groups_created=len(created_groups),
        events_created=len(created_events),
        users_created=len(created_users),
        duty_slots_created=len(created_slots),
        bookings_created=total_bookings,
    )


@router.delete(
    "/",
    response_model=DemoDataDeletedResponse,
)
async def delete_demo_data(
    db: DBDep,
    _current_user: CurrentSuperuser,
) -> DemoDataDeletedResponse:
    """Delete all entities whose name starts with the demo prefix."""

    # Find demo events
    demo_events = (
        await db.execute(select(Event).where(Event.name.startswith(DEMO_PREFIX)))
    ).scalars().all()

    # Find demo slots
    demo_slots = (
        await db.execute(
            select(DutySlot).where(DutySlot.title.startswith(DEMO_PREFIX))
        )
    ).scalars().all()
    demo_slot_ids = [s.id for s in demo_slots]

    # Delete bookings on demo slots
    bookings_deleted = 0
    if demo_slot_ids:
        bookings = (
            await db.execute(
                select(Booking).where(Booking.duty_slot_id.in_(demo_slot_ids))
            )
        ).scalars().all()
        bookings_deleted = len(bookings)
        for b in bookings:
            await db.delete(b)

    # Delete demo slots
    for s in demo_slots:
        await db.delete(s)

    # Delete demo events
    for e in demo_events:
        await db.delete(e)

    # Delete demo event groups
    demo_groups = (
        await db.execute(
            select(EventGroup).where(EventGroup.name.startswith(DEMO_PREFIX))
        )
    ).scalars().all()
    groups_deleted = len(demo_groups)
    for g in demo_groups:
        await db.delete(g)

    # Delete demo users (auth0_sub starts with 'demo|')
    demo_users = (
        await db.execute(select(User).where(User.auth0_sub.startswith("demo|")))
    ).scalars().all()
    users_deleted = len(demo_users)
    for u in demo_users:
        await db.delete(u)

    return DemoDataDeletedResponse(
        events_deleted=len(demo_events),
        event_groups_deleted=groups_deleted,
        users_deleted=users_deleted,
        duty_slots_deleted=len(demo_slots),
        bookings_deleted=bookings_deleted,
    )
