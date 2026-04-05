"""Shared fixtures for unit tests.

This module imports all fixtures from the fixtures/ subdirectory.
Fixtures are organized by domain for better maintainability:
- database.py: Database setup and session fixtures
- users.py: User fixtures (test_user, test_admin_user, etc.)
- auth.py: Auth0 mock claims fixtures
- client.py: FastAPI app and HTTP client fixtures
"""

# Import all fixtures so they are available to tests
# ruff: noqa: F401
# pyright: reportUnusedImport=false
from tests.fixtures.auth import (
    mock_auth0_admin_claims,
    mock_auth0_claims,
    mock_auth0_claims_no_sub,
    mock_auth0_new_user_claims,
    mock_request,
)
from tests.fixtures.bookings import test_booking
from tests.fixtures.client import app, as_admin, async_client
from tests.fixtures.database import db_session, test_db_setup, test_engine
from tests.fixtures.duty_slots import test_duty_slot
from tests.fixtures.event_groups import (
    test_draft_event_group,
    test_event_group,
    test_user_availability,
    test_user_availability_with_dates,
)
from tests.fixtures.events import test_draft_event, test_event
from tests.fixtures.users import test_admin_user, test_inactive_user, test_user
