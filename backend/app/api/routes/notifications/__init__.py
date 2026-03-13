from fastapi import APIRouter

from app.api.routes.notifications.feed import router as feed_router
from app.api.routes.notifications.preferences import router as preferences_router
from app.api.routes.notifications.push import router as push_router
from app.api.routes.notifications.telegram import router as telegram_router
from app.api.routes.notifications.types import router as types_router

router = APIRouter(prefix="/notifications", tags=["notifications"])

router.include_router(types_router)
router.include_router(feed_router)
router.include_router(preferences_router)
router.include_router(push_router)
router.include_router(telegram_router)
