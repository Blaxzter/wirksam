from fastapi import APIRouter

from app.api.deps import CurrentSuperuser, DBDep
from app.core.security import hash_password
from app.crud.site_settings import site_settings as crud_site_settings
from app.schemas.site_settings import SiteSettingsRead, SiteSettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/", response_model=SiteSettingsRead)
async def get_site_settings(
    session: DBDep,
    _: CurrentSuperuser,
) -> SiteSettingsRead:
    """Admin-only: Get current site settings."""
    settings = await crud_site_settings.get(session)
    return SiteSettingsRead(has_approval_password=settings.approval_password is not None)


@router.patch("/", response_model=SiteSettingsRead)
async def update_site_settings(
    settings_in: SiteSettingsUpdate,
    session: DBDep,
    _: CurrentSuperuser,
) -> SiteSettingsRead:
    """Admin-only: Update site settings."""
    # Hash the password before storing, or clear it if None
    if settings_in.approval_password is not None:
        settings_in.approval_password = hash_password(settings_in.approval_password)
    settings = await crud_site_settings.update(session, obj_in=settings_in)
    return SiteSettingsRead(has_approval_password=settings.approval_password is not None)
