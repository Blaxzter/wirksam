"""Seeds notification types from the code registry into the database."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.crud.notification_type import notification_type as crud_notification_type
from app.logic.notifications.registry import ALL_NOTIFICATION_TYPES

logger = get_logger(__name__)


async def seed_notification_types(db: AsyncSession) -> int:
    """Upsert all notification types from the registry.

    Called on application startup via lifespan.
    Returns the number of types upserted.
    """
    type_dicts = [t.to_dict() for t in ALL_NOTIFICATION_TYPES]
    count = await crud_notification_type.upsert_from_registry(db, types=type_dicts)
    await db.commit()
    logger.info(f"Seeded {count} notification types")
    return count
