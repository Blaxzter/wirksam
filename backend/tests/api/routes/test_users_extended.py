"""Extended route tests for User endpoints (admin management, export, auth0 URL)."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@pytest.mark.asyncio
class TestUserAdminRoutes:
    """Test suite for admin user management routes."""

    async def test_list_users(self, async_client: AsyncClient, as_admin: None):
        """Test listing all users (admin only)."""
        r = await async_client.get("/api/v1/users/")

        assert r.status_code == 200
        data: list[dict[str, Any]] = r.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # test_user + test_admin_user

    async def test_get_user_by_id(
        self, async_client: AsyncClient, as_admin: None, test_user: User
    ):
        """Test getting a user by ID (admin only)."""
        r = await async_client.get(f"/api/v1/users/{test_user.id}")

        assert r.status_code == 200
        assert r.json()["id"] == str(test_user.id)

    async def test_get_nonexistent_user(
        self, async_client: AsyncClient, as_admin: None
    ):
        """Test getting a nonexistent user returns 404."""
        fake_id = uuid.uuid4()
        r = await async_client.get(f"/api/v1/users/{fake_id}")
        assert r.status_code == 404

    async def test_create_user(self, async_client: AsyncClient, as_admin: None):
        """Test creating a user (admin only)."""
        r = await async_client.post(
            "/api/v1/users/",
            json={
                "auth0_sub": "auth0|created_by_admin",
                "email": "created@example.com",
                "name": "Created User",
                "is_active": True,
            },
        )

        assert r.status_code == 201
        assert r.json()["email"] == "created@example.com"

    async def test_update_user(
        self, async_client: AsyncClient, as_admin: None, db_session: AsyncSession
    ):
        """Test updating a user (admin only)."""
        user = User(
            auth0_sub="auth0|update_target",
            email="updatetarget@example.com",
            name="Update Target",
            is_active=False,
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)

        r = await async_client.patch(
            f"/api/v1/users/{user.id}",
            json={"is_active": True},
        )

        assert r.status_code == 200
        assert r.json()["is_active"] is True

    async def test_update_user_reject(
        self, async_client: AsyncClient, as_admin: None, db_session: AsyncSession
    ):
        """Test rejecting a user by setting rejection_reason."""
        user = User(
            auth0_sub="auth0|reject_target",
            email="reject@example.com",
            name="Reject Target",
            is_active=False,
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)

        r = await async_client.patch(
            f"/api/v1/users/{user.id}",
            json={"rejection_reason": "Not eligible"},
        )

        assert r.status_code == 200
        assert r.json()["rejection_reason"] == "Not eligible"


@pytest.mark.asyncio
class TestUserProfileRoutes:
    """Test suite for user profile routes."""

    async def test_export_user_data(self, async_client: AsyncClient):
        """Test GDPR data export endpoint."""
        r = await async_client.get("/api/v1/users/me/export")

        assert r.status_code == 200
        data = r.json()
        assert "profile" in data
        assert "bookings" in data
        assert "notification_preferences" in data
        assert "availabilities" in data
        assert "exported_at" in data

    async def test_export_user_data_profile_fields(self, async_client: AsyncClient):
        """Test that export includes expected profile fields."""
        r = await async_client.get("/api/v1/users/me/export")

        profile = r.json()["profile"]
        assert "name" in profile
        assert "email" in profile
        assert "roles" in profile
        assert "is_active" in profile
        assert "created_at" in profile

    async def test_auth0_management_url(self, async_client: AsyncClient):
        """Test getting the Auth0 management URL."""
        r = await async_client.get("/api/v1/users/auth0-management-url")

        assert r.status_code == 200
        data = r.json()
        assert "management_url" in data
        assert "note" in data
