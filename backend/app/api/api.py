from fastapi import APIRouter

from app.api.routes import (
    booking_reminders,
    bookings,
    calendar_feed,
    dashboard,
    demo_data,
    duty_slots,
    event_groups,
    events,
    health,
    notifications,
    reporting,
    site_settings,
    users,
)
from app.core.config import settings

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(users.router)
api_router.include_router(site_settings.router)
api_router.include_router(events.router)
api_router.include_router(duty_slots.router)
api_router.include_router(bookings.router)
api_router.include_router(booking_reminders.router)
api_router.include_router(calendar_feed.router)
api_router.include_router(event_groups.router)
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
