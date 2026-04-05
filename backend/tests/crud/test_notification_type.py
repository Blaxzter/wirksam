"""Unit tests for NotificationType CRUD operations."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.notification_type import notification_type as crud_notif_type
from app.logic.notifications.registry import NotificationTypeDict
from app.models.notification import NotificationType


@pytest.mark.asyncio
class TestCRUDNotificationType:
    """Test suite for NotificationType CRUD operations."""

    async def _create_type(
        self,
        db_session: AsyncSession,
        code: str = "test.code",
        *,
        is_active: bool = True,
        is_admin_only: bool = False,
    ) -> NotificationType:
        nt = NotificationType(
            code=code,
            name=f"Test {code}",
            description=f"Description for {code}",
            category="test",
            is_admin_only=is_admin_only,
            default_channels=["email"],
            is_active=is_active,
        )
        db_session.add(nt)
        await db_session.flush()
        await db_session.refresh(nt)
        return nt

    async def test_get_by_code(self, db_session: AsyncSession):
        """Test finding a notification type by code."""
        nt = await self._create_type(db_session, "booking.confirmed")

        found = await crud_notif_type.get_by_code(db_session, "booking.confirmed")

        assert found is not None
        assert found.id == nt.id
        assert found.code == "booking.confirmed"

    async def test_get_by_code_not_found(self, db_session: AsyncSession):
        """Test that a missing code returns None."""
        found = await crud_notif_type.get_by_code(db_session, "nonexistent.code")
        assert found is None

    async def test_get_all_active(self, db_session: AsyncSession):
        """Test fetching all active notification types."""
        await self._create_type(db_session, "active.one")
        await self._create_type(db_session, "active.two")
        await self._create_type(db_session, "inactive.one", is_active=False)

        active = await crud_notif_type.get_all_active(db_session)

        codes = [nt.code for nt in active]
        assert "active.one" in codes
        assert "active.two" in codes
        assert "inactive.one" not in codes

    async def test_get_all_active_excludes_admin_only(self, db_session: AsyncSession):
        """Test that admin-only types are excluded by default."""
        await self._create_type(db_session, "user.type")
        await self._create_type(db_session, "admin.type", is_admin_only=True)

        active = await crud_notif_type.get_all_active(db_session)

        codes = [nt.code for nt in active]
        assert "user.type" in codes
        assert "admin.type" not in codes

    async def test_get_all_active_includes_admin_only(self, db_session: AsyncSession):
        """Test that admin-only types are included when requested."""
        await self._create_type(db_session, "user.type2")
        await self._create_type(db_session, "admin.type2", is_admin_only=True)

        active = await crud_notif_type.get_all_active(
            db_session, include_admin_only=True
        )

        codes = [nt.code for nt in active]
        assert "user.type2" in codes
        assert "admin.type2" in codes

    async def test_upsert_from_registry_creates_new(self, db_session: AsyncSession):
        """Test upserting creates new notification types."""
        types: list[NotificationTypeDict] = [
            {
                "code": "new.type",
                "name": "New Type",
                "description": "Desc",
                "category": "test",
                "is_admin_only": False,
                "default_channels": ["email"],
                "is_user_configurable": True,
            }
        ]
        count = await crud_notif_type.upsert_from_registry(db_session, types=types)

        assert count == 1
        found = await crud_notif_type.get_by_code(db_session, "new.type")
        assert found is not None
        assert found.name == "New Type"

    async def test_upsert_from_registry_updates_existing(
        self, db_session: AsyncSession
    ):
        """Test upserting updates existing notification types."""
        await self._create_type(db_session, "existing.type")

        types: list[NotificationTypeDict] = [
            {
                "code": "existing.type",
                "name": "Updated Name",
                "description": "Updated desc",
                "category": "updated",
                "is_admin_only": True,
                "default_channels": ["push"],
                "is_user_configurable": False,
            }
        ]
        count = await crud_notif_type.upsert_from_registry(db_session, types=types)

        assert count == 1
        found = await crud_notif_type.get_by_code(db_session, "existing.type")
        assert found is not None
        assert found.name == "Updated Name"
        assert found.category == "updated"
        assert found.is_admin_only is True
