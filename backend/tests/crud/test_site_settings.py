"""Unit tests for SiteSettings CRUD operations."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.site_settings import site_settings as crud_site_settings
from app.schemas.site_settings import SiteSettingsUpdate


@pytest.mark.asyncio
class TestCRUDSiteSettings:
    """Test suite for SiteSettings CRUD operations."""

    async def test_get_creates_singleton(self, db_session: AsyncSession):
        """Test that get() creates the settings row if it doesn't exist."""
        settings = await crud_site_settings.get(db_session)

        assert settings is not None
        assert settings.approval_password is None

    async def test_get_returns_same_instance(self, db_session: AsyncSession):
        """Test that get() returns the same singleton row."""
        s1 = await crud_site_settings.get(db_session)
        s2 = await crud_site_settings.get(db_session)

        assert s1.id == s2.id

    async def test_update_approval_password(self, db_session: AsyncSession):
        """Test updating the approval password."""
        updated = await crud_site_settings.update(
            db_session,
            obj_in=SiteSettingsUpdate(approval_password="secret123"),
        )

        assert updated.approval_password == "secret123"

    async def test_clear_approval_password(self, db_session: AsyncSession):
        """Test clearing the approval password."""
        await crud_site_settings.update(
            db_session,
            obj_in=SiteSettingsUpdate(approval_password="secret"),
        )
        updated = await crud_site_settings.update(
            db_session,
            obj_in=SiteSettingsUpdate(approval_password=None),
        )

        assert updated.approval_password is None
