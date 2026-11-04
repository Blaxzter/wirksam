from fastapi import APIRouter

from app.api.routes.tasks.batches import router as batches_router
from app.api.routes.tasks.crud import router as crud_router
from app.api.routes.tasks.feed import router as feed_router
from app.api.routes.tasks.managers import router as managers_router
from app.api.routes.tasks.shifts import router as shifts_router

router = APIRouter(prefix="/tasks", tags=["tasks"])

router.include_router(feed_router)
router.include_router(crud_router)
router.include_router(shifts_router)
router.include_router(batches_router)
router.include_router(managers_router)
