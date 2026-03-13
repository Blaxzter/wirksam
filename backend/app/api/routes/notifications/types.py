from fastapi import APIRouter

from app.api.deps import CurrentUser, DBDep
from app.crud.notification_type import notification_type as crud_type
from app.models.notification import NotificationType
from app.schemas.notification import NotificationTypeRead

router = APIRouter()


@router.get("/types", response_model=list[NotificationTypeRead])
async def list_notification_types(
    session: DBDep,
    current_user: CurrentUser,
) -> list[NotificationType]:
    """List all active notification types. Non-admin users only see non-admin types."""
    types = await crud_type.get_all_active(
        session, include_admin_only=current_user.is_admin
    )
    return list(types)
