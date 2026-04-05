"""Unit tests for User CRUD operations."""

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.user import user as crud_user
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


@pytest.mark.asyncio
class TestUserCRUD:
    """Test suite for User CRUD operations."""

    async def test_create_user(self, db_session: AsyncSession):
        """Test creating a new user."""
        user_in = UserCreate(
            auth0_sub="auth0|newuser789",
            email="newuser@example.com",
            name="New User",
            roles=["user"],
            is_active=True,
        )
        user = await crud_user.create(db_session, obj_in=user_in)

        assert user.auth0_sub == "auth0|newuser789"
        assert user.email == "newuser@example.com"
        assert user.name == "New User"
        assert user.roles == ["user"]
        assert user.is_active is True
        assert user.id is not None

    async def test_get_user(self, db_session: AsyncSession, test_user: User):
        """Test getting a user by ID."""
        user = await crud_user.get(db_session, id=test_user.id)

        assert user is not None
        assert user.id == test_user.id
        assert user.email == test_user.email

    async def test_get_user_not_found(self, db_session: AsyncSession):
        """Test getting a non-existent user without raising error."""
        import uuid

        fake_id = uuid.uuid4()
        user = await crud_user.get(db_session, id=fake_id)

        assert user is None

    async def test_get_user_not_found_with_error(self, db_session: AsyncSession):
        """Test getting a non-existent user with raise_404_error=True."""
        import uuid

        fake_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc_info:
            await crud_user.get(db_session, id=fake_id, raise_404_error=True)

        assert exc_info.value.status_code == 404
        assert "User not found" in str(exc_info.value.detail)

    async def test_get_user_by_auth0_sub(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test getting a user by Auth0 sub."""
        user = await crud_user.get_by_auth0_sub(
            db_session, auth0_sub=test_user.auth0_sub
        )

        assert user is not None
        assert user.id == test_user.id
        assert user.auth0_sub == test_user.auth0_sub

    async def test_get_user_by_auth0_sub_not_found(self, db_session: AsyncSession):
        """Test getting a user by non-existent Auth0 sub."""
        user = await crud_user.get_by_auth0_sub(
            db_session, auth0_sub="auth0|nonexistent"
        )

        assert user is None

    async def test_get_user_by_email(self, db_session: AsyncSession, test_user: User):
        """Test getting a user by email."""
        assert test_user.email is not None
        user = await crud_user.get_by_email(db_session, email=test_user.email)

        assert user is not None
        assert user.id == test_user.id
        assert user.email == test_user.email

    async def test_get_user_by_email_not_found(self, db_session: AsyncSession):
        """Test getting a user by non-existent email."""
        user = await crud_user.get_by_email(db_session, email="nonexistent@example.com")

        assert user is None

    async def test_get_multi_users(
        self, db_session: AsyncSession, test_user: User, test_admin_user: User
    ):
        """Test getting multiple users."""
        users = await crud_user.get_multi(db_session, skip=0, limit=10)

        assert len(users) == 2
        user_ids = [user.id for user in users]
        assert test_user.id in user_ids
        assert test_admin_user.id in user_ids

    async def test_get_multi_with_pagination(
        self, db_session: AsyncSession, test_user: User, test_admin_user: User
    ):
        """Test pagination in get_multi."""
        # Get first page
        users_page1 = await crud_user.get_multi(db_session, skip=0, limit=1)
        assert len(users_page1) == 1

        # Get second page
        users_page2 = await crud_user.get_multi(db_session, skip=1, limit=1)
        assert len(users_page2) == 1

        # Ensure different users
        assert users_page1[0].id != users_page2[0].id

    async def test_update_user(self, db_session: AsyncSession, test_user: User):
        """Test updating a user."""
        user_update = UserUpdate(
            name="Updated Name",
            email="updated@example.com",
        )
        updated_user = await crud_user.update(
            db_session, db_obj=test_user, obj_in=user_update
        )

        assert updated_user.id == test_user.id
        assert updated_user.name == "Updated Name"
        assert updated_user.email == "updated@example.com"
        assert updated_user.auth0_sub == test_user.auth0_sub  # Unchanged

    async def test_update_user_roles(self, db_session: AsyncSession, test_user: User):
        """Test updating user roles."""
        user_update = UserUpdate(roles=["admin", "moderator"])
        updated_user = await crud_user.update(
            db_session, db_obj=test_user, obj_in=user_update
        )

        assert updated_user.roles == ["admin", "moderator"]

    async def test_update_user_is_active(
        self, db_session: AsyncSession, test_user: User
    ):
        """Test deactivating a user."""
        user_update = UserUpdate(is_active=False)
        updated_user = await crud_user.update(
            db_session, db_obj=test_user, obj_in=user_update
        )

        assert updated_user.is_active is False

    async def test_update_user_partial(self, db_session: AsyncSession, test_user: User):
        """Test partial update (only specified fields)."""
        original_email = test_user.email
        user_update = UserUpdate(name="New Name Only")
        updated_user = await crud_user.update(
            db_session, db_obj=test_user, obj_in=user_update
        )

        assert updated_user.name == "New Name Only"
        assert updated_user.email == original_email  # Unchanged

    async def test_remove_user(self, db_session: AsyncSession, test_user: User):
        """Test removing a user."""
        user_id = test_user.id
        removed_user = await crud_user.remove(db_session, id=user_id)

        assert removed_user is not None
        assert removed_user.id == user_id

        # Verify user is deleted
        user = await crud_user.get(db_session, id=user_id)
        assert user is None

    async def test_remove_user_not_found(self, db_session: AsyncSession):
        """Test removing a non-existent user."""
        import uuid

        fake_id = uuid.uuid4()
        removed_user = await crud_user.remove(db_session, id=fake_id)

        assert removed_user is None

    async def test_get_count(
        self, db_session: AsyncSession, test_user: User, test_admin_user: User
    ):
        """Test getting total count of users."""
        count = await crud_user.get_count(db_session)
        assert count == 2

    async def test_user_is_admin_property(
        self, db_session: AsyncSession, test_user: User, test_admin_user: User
    ):
        """Test the is_admin property."""
        assert test_user.is_admin is False
        assert test_admin_user.is_admin is True
