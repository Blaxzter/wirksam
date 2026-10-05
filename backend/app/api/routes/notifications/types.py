from fastapi import APIRouter

from app.api.deps import CurrentUser, DBDep
from app.core.config import settings
from app.crud.notification_type import notification_type as crud_type
from app.logic.notifications.registry import APPROVAL_TYPE_CODES
from app.models.notification import NotificationType
from app.schemas.notification import NotificationTypeRead

router = APIRouter()


@router.get("/types", response_model=list[NotificationTypeRead])
async def list_notification_types(
    session: DBDep,
    current_user: CurrentUser,
) -> list[NotificationType]:
    """List all active notification types. Non-admin users only see non-admin types.

    The registration-approval types are left out unless the deployment runs
    the approval queue: elsewhere nothing sends them, and a setting for a
    message that never arrives only raises the question of when it would.
    """
    types = await crud_type.get_all_active(
        session, include_admin_only=current_user.is_admin
    )
    if settings.REGISTRATION_MODE != "approval":
        return [t for t in types if t.code not in APPROVAL_TYPE_CODES]
    return list(types)
