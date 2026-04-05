"""Auth0 mock claims fixtures for testing."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_auth0_claims() -> dict[str, str]:
    """Create mock Auth0 claims."""
    return {
        "sub": "auth0|test123",
        "email": "test@example.com",
        "name": "Test User",
    }


@pytest.fixture
def mock_auth0_admin_claims() -> dict[str, str]:
    """Create mock Auth0 admin claims."""
    return {
        "sub": "auth0|admin123",
        "email": "admin@example.com",
        "name": "Admin User",
    }


@pytest.fixture
def mock_auth0_new_user_claims() -> dict[str, str]:
    """Create mock Auth0 claims for a new user."""
    return {
        "sub": "auth0|newuser456",
        "email": "newuser@example.com",
        "name": "New User",
        "nickname": "newuser",
    }


@pytest.fixture
def mock_auth0_claims_no_sub() -> dict[str, str]:
    """Create mock Auth0 claims without sub."""
    return {
        "email": "test@example.com",
        "name": "Test User",
    }


@pytest.fixture
def mock_request() -> MagicMock:
    """Create a mock Request with no X-Test-User-Email header."""
    request = MagicMock()
    request.headers.get.return_value = None
    return request
