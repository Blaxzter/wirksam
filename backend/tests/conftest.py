"""Shared fixtures for unit tests.

This module imports all fixtures from the fixtures/ subdirectory.
Fixtures are organized by domain for better maintainability:
- database.py: Database setup and session fixtures
- users.py: User fixtures (test_user, test_admin_user, etc.)
- auth.py: Access-token and Authorization-header factories
- client.py: FastAPI app and HTTP client fixtures
- sandbox.py: Seeded "try a test event" demos
- locations.py: Locations, venue plans and markers
"""

# Import all fixtures so they are available to tests
# ruff: noqa: F401
# pyright: reportUnusedImport=false
from tests.fixtures.auth import (
    auth_headers,
    make_access_token,
    make_expired_access_token,
    make_tampered_access_token,
)
from tests.fixtures.bookings import test_booking
from tests.fixtures.client import (
    app,
    as_admin,
    as_event_admin,
    as_outsider,
    async_client,
    unauthenticated_app,
    unauthenticated_client,
)
from tests.fixtures.database import db_session, test_db_setup, test_engine
from tests.fixtures.events import (
    test_draft_event,
    test_event,
    test_private_event,
    test_user_availability,
    test_user_availability_with_dates,
)
from tests.fixtures.locations import (
    test_location,
    test_location_marker,
    test_venue_plan,
)
from tests.fixtures.sandbox import (
    SandboxFactory,
    SandboxSetup,
    make_sandbox,
    test_sandbox,
)
from tests.fixtures.shifts import test_shift
from tests.fixtures.tasks import test_draft_task, test_task
from tests.fixtures.users import (
    test_admin_user,
    test_event_admin_user,
    test_inactive_user,
    test_outsider_user,
    test_passwordless_user,
    test_user,
)
