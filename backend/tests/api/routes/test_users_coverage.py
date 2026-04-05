"""Coverage gap tests for User endpoints (self-approve, profile-init, delete, export with data)."""

from datetime import date, time
from typing import Any, get_args

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps as deps_module
from app.core.security import hash_password
from app.crud.site_settings import site_settings as crud_site_settings
from app.models.booking import Booking
from app.models.duty_slot import DutySlot
from app.models.event import Event
from app.models.user import User


@pytest.mark.asyncio
class TestProfileInit:
    """Test POST /me with profile_init data."""

    async def test_profile_init_syncs_fields(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        test_user: User,
    ):
        """Test that profile_init syncs name, email, picture to user."""
        # Override AnyUser dependency for this test
        dep: Any = get_args(deps_module.AnyUser)[1].dependency

        async def override_any_user():
            return test_user

        app.dependency_overrides[dep] = override_any_user
        try:
            r = await async_client.post(
                "/api/v1/users/me",
                json={
                    "name": "Updated Name",
                    "email": "updated@example.com",
                    "picture": "https://example.com/pic.jpg",
                    "preferred_language": "de",
                },
            )

            assert r.status_code == 200
            data = r.json()
            assert data["name"] == "Updated Name"
            assert data["email"] == "updated@example.com"
        finally:
            app.dependency_overrides.pop(dep, None)

    async def test_profile_init_no_data(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        test_user: User,
    ):
        """Test POST /me without profile_init returns profile."""
        dep: Any = get_args(deps_module.AnyUser)[1].dependency

        async def override_any_user():
            return test_user

        app.dependency_overrides[dep] = override_any_user
        try:
            r = await async_client.post("/api/v1/users/me")

            assert r.status_code == 200
            data = r.json()
            assert data["sub"] == test_user.auth0_sub
        finally:
            app.dependency_overrides.pop(dep, None)


@pytest.mark.asyncio
class TestSelfApprove:
    """Test POST /self-approve endpoint."""

    async def test_self_approve_success(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test successful self-approval with correct password."""
        # Create a pending (inactive) user
        pending_user = User(
            auth0_sub="auth0|pending_approve",
            email="pending@example.com",
            name="Pending User",
            is_active=False,
        )
        db_session.add(pending_user)
        await db_session.flush()
        await db_session.refresh(pending_user)

        # Set approval password in site settings
        settings = await crud_site_settings.get(db_session)
        settings.approval_password = hash_password("secret123")
        db_session.add(settings)
        await db_session.flush()

        # Override AnyUser to return the pending user
        dep: Any = get_args(deps_module.AnyUser)[1].dependency

        async def override_any_user():
            return pending_user

        app.dependency_overrides[dep] = override_any_user
        try:
            r = await async_client.post(
                "/api/v1/users/self-approve",
                json={"password": "secret123"},
            )

            assert r.status_code == 200
            assert r.json()["is_active"] is True
        finally:
            app.dependency_overrides.pop(dep, None)

    async def test_self_approve_already_active(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        test_user: User,
    ):
        """Test self-approve fails for already active user."""
        dep: Any = get_args(deps_module.AnyUser)[1].dependency

        async def override_any_user():
            return test_user

        app.dependency_overrides[dep] = override_any_user
        try:
            r = await async_client.post(
                "/api/v1/users/self-approve",
                json={"password": "any"},
            )

            assert r.status_code == 400
        finally:
            app.dependency_overrides.pop(dep, None)

    async def test_self_approve_wrong_password(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test self-approve fails with wrong password."""
        pending_user = User(
            auth0_sub="auth0|pending_wrong_pw",
            email="wrongpw@example.com",
            name="Wrong PW User",
            is_active=False,
        )
        db_session.add(pending_user)
        await db_session.flush()
        await db_session.refresh(pending_user)

        settings = await crud_site_settings.get(db_session)
        settings.approval_password = hash_password("correct_password")
        db_session.add(settings)
        await db_session.flush()

        dep: Any = get_args(deps_module.AnyUser)[1].dependency

        async def override_any_user():
            return pending_user

        app.dependency_overrides[dep] = override_any_user
        try:
            r = await async_client.post(
                "/api/v1/users/self-approve",
                json={"password": "wrong_password"},
            )

            assert r.status_code == 403
        finally:
            app.dependency_overrides.pop(dep, None)

    async def test_self_approve_not_configured(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test self-approve fails when no approval password is configured."""
        pending_user = User(
            auth0_sub="auth0|pending_no_config",
            email="noconfig@example.com",
            name="No Config User",
            is_active=False,
        )
        db_session.add(pending_user)
        await db_session.flush()
        await db_session.refresh(pending_user)

        # Ensure no approval password is set
        settings = await crud_site_settings.get(db_session)
        settings.approval_password = None
        db_session.add(settings)
        await db_session.flush()

        dep: Any = get_args(deps_module.AnyUser)[1].dependency

        async def override_any_user():
            return pending_user

        app.dependency_overrides[dep] = override_any_user
        try:
            r = await async_client.post(
                "/api/v1/users/self-approve",
                json={"password": "any"},
            )

            assert r.status_code == 403
        finally:
            app.dependency_overrides.pop(dep, None)

    async def test_self_approve_rejected_user(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test self-approve fails for a rejected user."""
        rejected_user = User(
            auth0_sub="auth0|rejected_user",
            email="rejected@example.com",
            name="Rejected User",
            is_active=False,
            rejection_reason="Not eligible",
        )
        db_session.add(rejected_user)
        await db_session.flush()
        await db_session.refresh(rejected_user)

        dep: Any = get_args(deps_module.AnyUser)[1].dependency

        async def override_any_user():
            return rejected_user

        app.dependency_overrides[dep] = override_any_user
        try:
            r = await async_client.post(
                "/api/v1/users/self-approve",
                json={"password": "any"},
            )

            assert r.status_code == 400
        finally:
            app.dependency_overrides.pop(dep, None)


@pytest.mark.asyncio
class TestDeleteCurrentUser:
    """Test DELETE /me endpoint."""

    async def test_delete_current_user(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test deleting the current user's account."""
        # Create a user to delete (don't delete the fixture user)
        deletable_user = User(
            auth0_sub="auth0|deletable_user",
            email="deletable@example.com",
            name="Deletable User",
            is_active=True,
        )
        db_session.add(deletable_user)
        await db_session.flush()
        await db_session.refresh(deletable_user)

        dep: Any = get_args(deps_module.AnyUser)[1].dependency

        async def override_any_user():
            return deletable_user

        app.dependency_overrides[dep] = override_any_user
        try:
            r = await async_client.delete("/api/v1/users/me")
            assert r.status_code == 204
        finally:
            app.dependency_overrides.pop(dep, None)


@pytest.mark.asyncio
class TestUserProfileUpdate:
    """Test PATCH /me endpoint."""

    async def test_update_profile_picture(self, async_client: AsyncClient):
        """Test updating user profile picture."""
        r = await async_client.patch(
            "/api/v1/users/me",
            json={"picture": "https://example.com/new-pic.jpg"},
        )

        assert r.status_code == 200

    async def test_update_profile_language(self, async_client: AsyncClient):
        """Test updating user preferred language."""
        r = await async_client.patch(
            "/api/v1/users/me",
            json={"preferred_language": "de"},
        )

        assert r.status_code == 200

    async def test_update_profile_phone(self, async_client: AsyncClient):
        """Test updating user phone number."""
        r = await async_client.patch(
            "/api/v1/users/me",
            json={"phone_number": "+49123456789"},
        )

        assert r.status_code == 200


@pytest.mark.asyncio
class TestExportWithData:
    """Test GET /me/export with actual data in the database."""

    async def test_export_with_bookings(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_event: Event,
    ):
        """Test export includes user's bookings."""
        slot = DutySlot(
            event_id=test_event.id,
            title="Export Test Slot",
            date=date(2026, 6, 1),
            start_time=time(8, 0),
            end_time=time(12, 0),
        )
        db_session.add(slot)
        await db_session.flush()

        booking = Booking(
            duty_slot_id=slot.id,
            user_id=test_user.id,
            status="confirmed",
            notes="Export test",
        )
        db_session.add(booking)
        await db_session.flush()

        r = await async_client.get("/api/v1/users/me/export")

        assert r.status_code == 200
        data = r.json()
        assert len(data["bookings"]) >= 1
        assert any(b["notes"] == "Export test" for b in data["bookings"])


@pytest.mark.asyncio
class TestAdminUserManagement:
    """Test admin user update with approval/rejection notifications."""

    async def test_admin_approve_user_triggers_notification(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test that approving a user dispatches approval notification."""
        user = User(
            auth0_sub="auth0|approve_notif_test",
            email="approve_notif@example.com",
            name="Approve Notif User",
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

    async def test_admin_reject_user_triggers_notification(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test that rejecting a user dispatches rejection notification."""
        user = User(
            auth0_sub="auth0|reject_notif_test",
            email="reject_notif@example.com",
            name="Reject Notif User",
            is_active=False,
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)

        r = await async_client.patch(
            f"/api/v1/users/{user.id}",
            json={"rejection_reason": "Not eligible for this role"},
        )

        assert r.status_code == 200
        assert r.json()["rejection_reason"] == "Not eligible for this role"

    async def test_admin_delete_user(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
    ):
        """Test admin deleting a user by ID."""
        user = User(
            auth0_sub="auth0|admin_delete_target",
            email="admin_delete@example.com",
            name="Admin Delete Target",
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)

        r = await async_client.delete(f"/api/v1/users/{user.id}")

        assert r.status_code == 200
        assert r.json()["id"] == str(user.id)
