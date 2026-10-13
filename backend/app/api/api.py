from fastapi import APIRouter

from app.api.routes import (
    auth,
    avatars,
    booking_reminders,
    bookings,
    calendar_feed,
    dashboard,
    demo_data,
    events,
    health,
    invitations,
    notifications,
    reporting,
    shifts,
    tasks,
    users,
    work_hours,
)
from app.core.config import settings

api_router = APIRouter()

api_router.include_router(health.router)
# Under its own /auth prefix, so it never competes with the catch-all
# `GET /users/{user_id}` — a literal path registered under /users after that
# route would be shadowed by it, silently.
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(avatars.router)
api_router.include_router(tasks.router)
api_router.include_router(shifts.router)
api_router.include_router(bookings.router)
api_router.include_router(booking_reminders.router)
api_router.include_router(calendar_feed.router)
api_router.include_router(events.router)
api_router.include_router(work_hours.router)
api_router.include_router(invitations.router)
api_router.include_router(notifications.router)
api_router.include_router(dashboard.router)
api_router.include_router(reporting.router)
api_router.include_router(demo_data.router)

if settings.ENVIRONMENT != "production":
    from app.api.routes import debug

    api_router.include_router(debug.router)

if settings.TESTING:
    from app.api.routes import testing

    api_router.include_router(testing.router)
