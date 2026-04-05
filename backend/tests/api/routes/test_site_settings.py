"""Route tests for SiteSettings endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestSiteSettingsRoutes:
    """Test suite for /settings/ routes (admin only)."""

    async def test_get_site_settings(self, async_client: AsyncClient, as_admin: None):
        """Test getting site settings."""
        r = await async_client.get("/api/v1/settings/")

        assert r.status_code == 200
        data = r.json()
        assert "has_approval_password" in data

    async def test_update_site_settings(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test updating site settings."""
        r = await async_client.patch(
            "/api/v1/settings/",
            json={"approval_password": "mysecret"},
        )

        assert r.status_code == 200
        assert r.json()["has_approval_password"] is True

    async def test_clear_approval_password(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test clearing the approval password."""
        # Set it first
        await async_client.patch(
            "/api/v1/settings/",
            json={"approval_password": "temp"},
        )
        # Clear it
        r = await async_client.patch(
            "/api/v1/settings/",
            json={"approval_password": None},
        )

        assert r.status_code == 200
        assert r.json()["has_approval_password"] is False
