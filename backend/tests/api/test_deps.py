"""Unit tests for authentication dependencies."""

from typing import Any, get_args
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_or_create_user
from app.crud.user import user as crud_user
from app.models.user import User


@pytest.mark.asyncio
class TestGetOrCreateUser:
    """Test suite for get_or_create_user helper function."""

    async def test_get_existing_user(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_auth0_claims: dict[str, Any],
    ):
        """Test getting an existing user."""
        user = await get_or_create_user(db_session, mock_auth0_claims)

        assert user.id == test_user.id
        assert user.auth0_sub == test_user.auth0_sub
        assert user.email == test_user.email

    async def test_create_new_user_from_claims(
        self,
        db_session: AsyncSession,
        mock_auth0_new_user_claims: dict[str, Any],
    ):
        """Test creating a new user from Auth0 claims."""
        user = await get_or_create_user(db_session, mock_auth0_new_user_claims)

        assert user.auth0_sub == "auth0|newuser456"
        assert user.email == "newuser@example.com"
        assert user.name == "New User"
        assert user.is_active is False  # non-superadmin users start inactive
        assert user.roles == []

        # Verify user was persisted
        persisted_user = await crud_user.get_by_auth0_sub(
            db_session, auth0_sub="auth0|newuser456"
        )
        assert persisted_user is not None
        assert persisted_user.id == user.id

    async def test_create_new_user_with_profile_data(
        self,
        db_session: AsyncSession,
        mock_auth0_new_user_claims: dict[str, Any],
    ):
        """Test creating a new user with profile data from frontend."""
        profile_data = {
            "email": "frontend@example.com",
            "name": "Frontend User",
        }

        user = await get_or_create_user(
            db_session, mock_auth0_new_user_claims, profile_data
        )

        # Should use profile_data over claims
        assert user.email == "frontend@example.com"
        assert user.name == "Frontend User"

    async def test_create_new_user_with_nickname(
        self,
        db_session: AsyncSession,
    ):
        """Test creating a new user using nickname when name is absent."""
        claims = {
            "sub": "auth0|nickname123",
            "email": "nickname@example.com",
            "nickname": "nicknameuser",
        }

        user = await get_or_create_user(db_session, claims)

        assert user.name == "nicknameuser"

    async def test_missing_sub_raises_error(
        self,
        db_session: AsyncSession,
        mock_auth0_claims_no_sub: dict[str, Any],
    ):
        """Test that missing 'sub' in claims raises HTTPException."""
        with pytest.raises(HTTPException) as exc_info:
            await get_or_create_user(db_session, mock_auth0_claims_no_sub)

        assert exc_info.value.status_code == 401
        assert "Invalid authentication payload" in str(exc_info.value.detail)


@pytest.mark.asyncio
class TestCurrentUserDependency:
    """Test suite for current_user dependency."""

    async def test_current_user_success(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_auth0_claims: dict[str, Any],
        mock_request: MagicMock,
    ):
        """Test successful user authentication."""
        # Create the dependency function
        dependency = current_user()

        # Call the dependency with mocked claims
        user = await dependency(
            request=mock_request, session=db_session, claims=mock_auth0_claims
        )

        assert user.id == test_user.id
        assert user.is_active is True

    async def test_current_user_inactive_raises_error(
        self,
        db_session: AsyncSession,
        test_inactive_user: User,
        mock_request: MagicMock,
    ):
        """Test that inactive user raises 403 error."""
        claims = {
            "sub": test_inactive_user.auth0_sub,
            "email": test_inactive_user.email,
        }

        dependency = current_user()

        with pytest.raises(HTTPException) as exc_info:
            await dependency(request=mock_request, session=db_session, claims=claims)

        assert exc_info.value.status_code == 403
        assert "Inactive user" in str(exc_info.value.detail)

    async def test_current_user_with_role_check_success(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
        mock_request: MagicMock,
    ):
        """Test role-based access control with valid role."""
        claims = {
            "sub": test_admin_user.auth0_sub,
            "email": test_admin_user.email,
        }

        # Require admin role
        dependency = current_user(required_roles="admin")

        user = await dependency(request=mock_request, session=db_session, claims=claims)

        assert user.id == test_admin_user.id
        assert "admin" in user.roles

    async def test_current_user_with_role_check_failure(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_request: MagicMock,
    ):
        """Test role-based access control with missing role."""
        claims = {
            "sub": test_user.auth0_sub,
            "email": test_user.email,
        }

        # Require admin role (test_user doesn't have it)
        dependency = current_user(required_roles="admin")

        with pytest.raises(HTTPException) as exc_info:
            await dependency(request=mock_request, session=db_session, claims=claims)

        assert exc_info.value.status_code == 403
        assert "Not enough permissions" in str(exc_info.value.detail)

    async def test_current_user_with_multiple_roles(
        self,
        db_session: AsyncSession,
        mock_request: MagicMock,
    ):
        """Test role check with multiple required roles."""
        # Create user with multiple roles
        user = User(
            auth0_sub="auth0|multirole123",
            email="multirole@example.com",
            name="Multi Role User",
            roles=["admin", "moderator"],
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)

        claims = {
            "sub": user.auth0_sub,
            "email": user.email,
        }

        # Require admin role (user has it)
        dependency = current_user(required_roles=["admin", "moderator"])

        result_user = await dependency(
            request=mock_request, session=db_session, claims=claims
        )

        assert result_user.id == user.id

    async def test_current_user_with_multiple_roles_missing_one(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
        mock_request: MagicMock,
    ):
        """Test role check when user is missing one of the required roles."""
        claims = {
            "sub": test_admin_user.auth0_sub,
            "email": test_admin_user.email,
        }

        # Require both admin and moderator (user only has admin)
        dependency = current_user(required_roles=["admin", "moderator"])

        with pytest.raises(HTTPException) as exc_info:
            await dependency(request=mock_request, session=db_session, claims=claims)

        assert exc_info.value.status_code == 403
        assert "Not enough permissions" in str(exc_info.value.detail)

    async def test_current_user_rejects_new_inactive_user(
        self,
        db_session: AsyncSession,
        mock_auth0_new_user_claims: dict[str, Any],
        mock_request: MagicMock,
    ):
        """Test that a new non-superadmin user is created inactive and rejected."""
        # Ensure user doesn't exist
        existing_user = await crud_user.get_by_auth0_sub(
            db_session, auth0_sub=mock_auth0_new_user_claims["sub"]
        )
        assert existing_user is None

        dependency = current_user()

        with pytest.raises(HTTPException) as exc_info:
            await dependency(
                request=mock_request,
                session=db_session,
                claims=mock_auth0_new_user_claims,
            )

        assert exc_info.value.status_code == 403
        assert "Inactive user" in str(exc_info.value.detail)

        # Verify user was still persisted in the database
        created_user = await crud_user.get_by_auth0_sub(
            db_session, auth0_sub=mock_auth0_new_user_claims["sub"]
        )
        assert created_user is not None
        assert created_user.is_active is False

    async def test_current_user_rejects_inactive_new_user(
        self,
        db_session: AsyncSession,
        mock_auth0_new_user_claims: dict[str, Any],
        mock_request: MagicMock,
    ):
        """Test current_user creates user from claims but rejects inactive."""
        dependency = current_user()

        with pytest.raises(HTTPException) as exc_info:
            await dependency(
                request=mock_request,
                session=db_session,
                claims=mock_auth0_new_user_claims,
            )

        assert exc_info.value.status_code == 403

        # Verify user was created from claims
        created_user = await crud_user.get_by_auth0_sub(
            db_session, auth0_sub=mock_auth0_new_user_claims["sub"]
        )
        assert created_user is not None
        assert created_user.is_active is False


@pytest.mark.asyncio
class TestCurrentUserAnnotated:
    """Test suite for CurrentUser and CurrentSuperuser typed dependencies."""

    async def test_current_user_annotated(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_auth0_claims: dict[str, Any],
        mock_request: MagicMock,
    ):
        """Test CurrentUser typed dependency."""
        from app.api.deps import CurrentUser

        # Extract the dependency function from the Annotated type
        # In practice, FastAPI does this automatically
        dependency_metadata = get_args(CurrentUser)[1]
        dependency = dependency_metadata.dependency

        user = await dependency(
            request=mock_request, session=db_session, claims=mock_auth0_claims
        )

        assert user.id == test_user.id
        assert isinstance(user, User)

    async def test_current_superuser_annotated(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
        mock_request: MagicMock,
    ):
        """Test CurrentSuperuser typed dependency."""
        from app.api.deps import CurrentSuperuser

        claims = {
            "sub": test_admin_user.auth0_sub,
            "email": test_admin_user.email,
        }

        dependency_metadata = get_args(CurrentSuperuser)[1]
        dependency = dependency_metadata.dependency

        user = await dependency(request=mock_request, session=db_session, claims=claims)

        assert user.id == test_admin_user.id
        assert user.is_admin is True

    async def test_current_superuser_with_non_admin_fails(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_request: MagicMock,
    ):
        """Test CurrentSuperuser rejects non-admin users."""
        from app.api.deps import CurrentSuperuser

        claims = {
            "sub": test_user.auth0_sub,
            "email": test_user.email,
        }

        dependency_metadata = get_args(CurrentSuperuser)[1]
        dependency = dependency_metadata.dependency

        with pytest.raises(HTTPException) as exc_info:
            await dependency(request=mock_request, session=db_session, claims=claims)

        assert exc_info.value.status_code == 403
        assert "Not enough permissions" in str(exc_info.value.detail)


class TestRoleNormalization:
    """Test suite for _normalize_required_roles helper."""

    def test_normalize_none(self):
        """Test normalizing None to empty list."""
        from app.api.deps import (
            _normalize_required_roles,  # type: ignore[reportPrivateUsage]
        )

        result = _normalize_required_roles(None)
        assert result == []

    def test_normalize_string(self):
        """Test normalizing single string to list."""
        from app.api.deps import (
            _normalize_required_roles,  # type: ignore[reportPrivateUsage]
        )

        result = _normalize_required_roles("admin")
        assert result == ["admin"]

    def test_normalize_list(self):
        """Test normalizing list of strings."""
        from app.api.deps import (
            _normalize_required_roles,  # type: ignore[reportPrivateUsage]
        )

        result = _normalize_required_roles(["admin", "moderator"])
        assert result == ["admin", "moderator"]

    def test_normalize_iterable(self):
        """Test normalizing tuple to list."""
        from app.api.deps import (
            _normalize_required_roles,  # type: ignore[reportPrivateUsage]
        )

        result = _normalize_required_roles(("admin", "user"))
        assert result == ["admin", "user"]
