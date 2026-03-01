from fastapi import APIRouter

from app.api.routes import bookings, duty_slots, events, health, users

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(users.router)
api_router.include_router(events.router)
api_router.include_router(duty_slots.router)
api_router.include_router(bookings.router)
