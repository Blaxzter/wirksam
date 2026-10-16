"""Taking a demo away again — the half of the feature that keeps the promise.

Read this before changing anything here: **the deletion order is load-bearing**,
and getting it wrong does not raise. It leaves rows behind that no longer belong
to any event, and a row with a NULL ``event_id`` slips through every scope
filter in the application, because those filters are all built from
``event_id IN (...)`` and a NULL matches no ``IN`` list. The failure mode is not
a crash; it is a stranger's demo shift showing up in a real user's search
results, permanently, with no owner who could delete it.

Two foreign keys cause that:

* ``tasks.event_id`` is ``ON DELETE SET NULL`` (``models/task.py``) and
  ``Event.tasks`` carries no ``delete-orphan`` cascade. Deleting the event on
  its own therefore *orphans* its tasks rather than removing them, and with the
  tasks go their shifts and everyone's bookings on them.
* ``events.created_by_id`` is ``ON DELETE CASCADE`` (``models/event.py``).
  Deleting the guest first therefore deletes the event underneath us at the
  database level, which fires the SET NULL above before any Python runs.

Hence: children first, the event next, the guest accounts **last**. And hence
``Task.is_sandbox`` exists as a denormalised column — belt and braces, so that
an orphan produced some other way is still excluded from every listing.

Nothing here commits. ``api.deps.get_db`` owns the transaction boundary, so a
purge that fails half way rolls back whole rather than leaving the very mess
this module exists to prevent.
"""

import datetime as dt
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.logger import get_logger
from app.models.auth_session import AuthSession
from app.models.booking import Booking
from app.models.booking_reminder import BookingReminder
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.location import Location
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User
from app.models.user_availability import UserAvailability
from app.models.venue_plan import VenueMarker, VenuePlan, VenuePlanImage, VenueShape
from app.models.venue_template import VenueTemplate, VenueTemplateImage

logger = get_logger(__name__)


async def purge_sandbox(db: AsyncSession, *, event_id: uuid.UUID) -> None:
    """Hard-delete one sandbox event and every guest account that lived in it.

    Safe to call on an id that is not a sandbox — it does nothing rather than
    deleting a real event, because the lookup below is filtered on
    ``is_sandbox``. That check is not paranoia: this function is reachable from
    an HTTP route, and the id it acts on comes from a session.
    """
    event = (
        await db.execute(
            select(Event).where(
                col(Event.id) == event_id, col(Event.is_sandbox).is_(True)
            )
        )
    ).scalar_one_or_none()
    if event is None:
        return

    task_ids = list(
        (
            await db.execute(select(col(Task.id)).where(col(Task.event_id) == event_id))
        ).scalars()
    )
    shift_ids: list[uuid.UUID] = []
    if task_ids:
        shift_ids = list(
            (
                await db.execute(
                    select(col(Shift.id)).where(col(Shift.task_id).in_(task_ids))
                )
            ).scalars()
        )

    # Every account that only ever existed inside this demo: the guest who
    # started it, plus the fake teammates the seeder gave them. Filtered on
    # is_sandbox so a real account that somehow joined cannot be deleted.
    guest_ids = list(
        (
            await db.execute(
                select(col(User.id))
                .join(EventMembership, col(EventMembership.user_id) == col(User.id))
                .where(
                    col(EventMembership.event_id) == event_id,
                    col(User.is_sandbox).is_(True),
                )
            )
        ).scalars()
    )
    if event.created_by_id is not None and event.created_by_id not in guest_ids:
        creator_id = (
            await db.execute(
                select(col(User.id)).where(
                    col(User.id) == event.created_by_id,
                    col(User.is_sandbox).is_(True),
                )
            )
        ).scalar_one_or_none()
        if creator_id is not None:
            guest_ids.append(creator_id)

    # 1. Bookings before shifts. ``bookings.shift_id`` is SET NULL, so removing
    #    a shift first would strand the booking instead of removing it — and a
    #    booking with no shift is unreachable from every screen that could
    #    delete it afterwards.
    if shift_ids:
        await db.execute(
            delete(BookingReminder).where(col(BookingReminder.shift_id).in_(shift_ids))
        )
        await db.execute(delete(Booking).where(col(Booking.shift_id).in_(shift_ids)))
        await db.execute(delete(Shift).where(col(Shift.id).in_(shift_ids)))

    # 2. Tasks explicitly, never by cascade from the event — see the module
    #    docstring. Batches would cascade from the task; being explicit keeps
    #    the order readable and survives someone loosening that cascade later.
    if task_ids:
        await db.execute(
            delete(ShiftBatch).where(col(ShiftBatch.task_id).in_(task_ids))
        )
        await db.execute(delete(Task).where(col(Task.id).in_(task_ids)))

    # 3. Anything else hanging off the event. All of it would cascade, but the
    #    availabilities carry child rows of their own and the memberships are
    #    what step 5 read, so they go here where the order stays visible.
    await db.execute(
        delete(UserAvailability).where(col(UserAvailability.event_id) == event_id)
    )
    await db.execute(
        delete(EventMembership).where(col(EventMembership.event_id) == event_id)
    )
    #    The venue map: markers, shapes, image bytes, plans, then the
    #    locations. All of it cascades from the event too; spelled out so the
    #    largest rows a demo owns (the drawing, an image if any) visibly go,
    #    and so the locations are gone before the event rather than in the
    #    middle of its cascade. Markers are matched by plan *and* by location,
    #    so none can outlive either parent; shapes only point at a location
    #    with SET NULL, so going by plan is enough.
    plan_ids = select(col(VenuePlan.id)).where(col(VenuePlan.event_id) == event_id)
    location_ids = select(col(Location.id)).where(col(Location.event_id) == event_id)
    await db.execute(delete(VenueMarker).where(col(VenueMarker.plan_id).in_(plan_ids)))
    await db.execute(
        delete(VenueMarker).where(col(VenueMarker.location_id).in_(location_ids))
    )
    await db.execute(delete(VenueShape).where(col(VenueShape.plan_id).in_(plan_ids)))
    await db.execute(
        delete(VenuePlanImage).where(col(VenuePlanImage.plan_id).in_(plan_ids))
    )
    await db.execute(delete(VenuePlan).where(col(VenuePlan.event_id) == event_id))
    await db.execute(delete(Location).where(col(Location.event_id) == event_id))

    # 4. The event itself. Invitations and join requests cascade from here.
    await db.execute(delete(Event).where(col(Event.id) == event_id))

    # 5. The guests, last. This cascades their notifications, avatars and
    #    tokens. Deleting their sessions explicitly first means a guest whose
    #    demo is purged mid-request stops being authenticated immediately
    #    rather than at the end of their fifteen-minute access token.
    #    Venue templates hang off the account, not the event, so steps 1-4
    #    never reach them: they go here, image bytes first, before the users
    #    (their FK cascades too; spelled out like the venue map above so the
    #    largest rows a guest can own visibly go).
    if guest_ids:
        template_ids = select(col(VenueTemplate.id)).where(
            col(VenueTemplate.user_id).in_(guest_ids)
        )
        await db.execute(
            delete(VenueTemplateImage).where(
                col(VenueTemplateImage.template_id).in_(template_ids)
            )
        )
        await db.execute(
            delete(VenueTemplate).where(col(VenueTemplate.user_id).in_(guest_ids))
        )
        await db.execute(
            delete(AuthSession).where(col(AuthSession.user_id).in_(guest_ids))
        )
        await db.execute(delete(User).where(col(User.id).in_(guest_ids)))

    logger.info(
        "sandbox purged",
        extra={
            "event_id": str(event_id),
            "tasks": len(task_ids),
            "shifts": len(shift_ids),
            "guests": len(guest_ids),
        },
    )


async def sweep_expired(db: AsyncSession, *, now: dt.datetime, limit: int = 20) -> int:
    """Purge every sandbox whose TTL has run out. Returns how many went.

    Called at the top of each new sandbox, which is what makes the feature
    self-cleaning without a scheduler: the only way to accumulate sandboxes is
    to keep creating them, and creating one is exactly when this runs.

    ``limit`` bounds the work so a long-idle deployment does not turn one
    visitor's click into a hundred cascading deletes; the next click takes the
    next batch.
    """
    expired = list(
        (
            await db.execute(
                select(col(Event.id))
                .where(
                    col(Event.is_sandbox).is_(True),
                    col(Event.sandbox_expires_at).isnot(None),
                    col(Event.sandbox_expires_at) <= now,
                )
                .order_by(col(Event.sandbox_expires_at))
                .limit(limit)
            )
        ).scalars()
    )
    for event_id in expired:
        await purge_sandbox(db, event_id=event_id)
    return len(expired)


async def count_active(db: AsyncSession, *, now: dt.datetime) -> int:
    """How many sandboxes are still live.

    This is the real concurrency ceiling. The rate limiter cannot be, because
    its counters are per worker process and it returns immediately under
    ``TESTING`` — see ``core.rate_limit``.
    """
    result = await db.execute(
        select(col(Event.id)).where(
            col(Event.is_sandbox).is_(True),
            col(Event.sandbox_expires_at) > now,
        )
    )
    return len(list(result.scalars()))
