from fastapi import APIRouter

from app.api.routes.events.batches import router as batches_router
from app.api.routes.events.crud import router as crud_router
from app.api.routes.events.slots import router as slots_router

router = APIRouter(prefix="/events", tags=["events"])

router.include_router(crud_router)
router.include_router(slots_router)
router.include_router(batches_router)
