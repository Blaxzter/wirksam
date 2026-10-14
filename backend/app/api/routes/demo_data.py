"""Demo data endpoints for creating/deleting test data.

All demo entities are tagged with a '[DEMO]' prefix so they can be
reliably identified and cleaned up. The generator itself lives in
``app.logic.demo_data`` so ``just seed`` can use it too.
"""

from fastapi import APIRouter
from sqlalchemy import select
from sqlmodel import col

from app.api.deps import CurrentSuperuser, DBDep
from app.logic import demo_data as demo_data_logic
from app.models.booking import Booking
from app.models.event import Event
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.demo_data import (
    DEMO_PREFIX,
    DemoDataCreatedResponse,
    DemoDataDeletedResponse,
    DemoDataParams,
)

router = APIRouter(prefix="/demo-data", tags=["demo-data"])


@router.post(
    "/",
    response_model=DemoDataCreatedResponse,
)
async def create_demo_data(
    params: DemoDataParams,
    db: DBDep,
    _current_user: CurrentSuperuser,
) -> DemoDataCreatedResponse:
    """Create demo events, tasks, users, and duty shifts."""
    return await demo_data_logic.create_demo_data(
        db, owner=_current_user, params=params
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

    # Find demo tasks
    demo_tasks = (
        (await db.execute(select(Task).where(col(Task.name).startswith(DEMO_PREFIX))))
        .scalars()
        .all()
    )

    # Find demo shifts
    demo_shifts = (
        (
            await db.execute(
                select(Shift).where(col(Shift.title).startswith(DEMO_PREFIX))
            )
        )
        .scalars()
        .all()
    )
    demo_shift_ids = [s.id for s in demo_shifts]

    # Delete bookings on demo shifts
    bookings_deleted = 0
    if demo_shift_ids:
        bookings = (
            (
                await db.execute(
                    select(Booking).where(col(Booking.shift_id).in_(demo_shift_ids))
                )
            )
            .scalars()
            .all()
        )
        bookings_deleted = len(bookings)
        for b in bookings:
            await db.delete(b)

    # Delete demo shifts
    for s in demo_shifts:
        await db.delete(s)

    # Delete demo tasks
    for e in demo_tasks:
        await db.delete(e)

    # Delete demo events
    demo_groups = (
        (await db.execute(select(Event).where(col(Event.name).startswith(DEMO_PREFIX))))
        .scalars()
        .all()
    )
    groups_deleted = len(demo_groups)
    for g in demo_groups:
        await db.delete(g)

    # Delete demo users (subject starts with 'demo|')
    demo_users = (
        (await db.execute(select(User).where(col(User.subject).startswith("demo|"))))
        .scalars()
        .all()
    )
    users_deleted = len(demo_users)
    for u in demo_users:
        await db.delete(u)

    return DemoDataDeletedResponse(
        tasks_deleted=len(demo_tasks),
        events_deleted=groups_deleted,
        users_deleted=users_deleted,
        shifts_deleted=len(demo_shifts),
        bookings_deleted=bookings_deleted,
    )
