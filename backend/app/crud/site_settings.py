from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.site_settings import SiteSettings
from app.schemas.site_settings import SiteSettingsUpdate


class CRUDSiteSettings:
    async def get(self, db: AsyncSession) -> SiteSettings:
        """Get the singleton settings row, creating it if it doesn't exist."""
        result = await db.execute(select(SiteSettings).limit(1))
        settings = result.scalars().first()
        if not settings:
            settings = SiteSettings()
            db.add(settings)
            await db.flush()
        return settings

    async def update(
        self, db: AsyncSession, *, obj_in: SiteSettingsUpdate
    ) -> SiteSettings:
        settings = await self.get(db)
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(settings, field, value)
        db.add(settings)
        await db.flush()
        return settings


site_settings = CRUDSiteSettings()
