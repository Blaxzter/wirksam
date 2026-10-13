# Test Fixtures

This directory contains organized test fixtures for the FastAPI application.

## Structure

Fixtures are organized by domain for better maintainability and easier navigation:

### `database.py`

Database setup and session fixtures:

- `test_db_setup` - Drops and recreates `app_test`, then runs `alembic upgrade head` (session scope)
- `test_engine` - Creates a test database engine
- `db_session` - Creates a test database session with transaction rollback

### `users.py`

User-related fixtures. All of them are ordinary local accounts — a `local|`
subject, a verified address and a real bcrypt hash of `TEST_USER_PASSWORD`, so
they can be signed in as and not merely read:

- `test_user` - Regular test user (non-admin)
- `test_admin_user` - Platform superadmin (`roles=["admin"]`)
- `test_event_admin_user` - Runs the fixture events, holds no global role
- `test_outsider_user` - Belongs to no event at all
- `test_inactive_user` - Suspended account; keeps its password
- `test_passwordless_user` - `password_hash` is NULL (demo/legacy shape)
- `TEST_USER_PASSWORD` / `TEST_USER_PASSWORD_HASH` - module constants, not fixtures

The hash is computed once at import. bcrypt costs about a quarter of a second
per call and `test_user` is pulled in by almost every test in the suite, so
hashing per fixture call would add minutes of CPU to every run.

### `events.py`

Event-related fixtures (each seeds the memberships its tests rely on):

- `test_event` - Published, public event
- `test_draft_event` - Unpublished event
- `test_private_event` - Invitation-only event
- `test_user_availability` / `test_user_availability_with_dates`

### `tasks.py` / `shifts.py` / `bookings.py`

- `test_task`, `test_draft_task`
- `test_shift`
- `test_booking`

### `locations.py`

Locations (#182) and the venue map (#185), all on `test_event`:

- `test_location` - "Foyer", with a markdown description, address, map link and contact
- `test_venue_plan` - "Ground floor", with an 800x600 image row stored and
  `image_etag` / `image_width` / `image_height` set on the plan
- `test_location_marker` - `test_location` placed on `test_venue_plan`
- `test_venue_shapes` - one shape of each kind on `test_venue_plan`, in drawing
  order: a rect linked to `test_location`, a polygon, a path and a text label
  (the plan's `shapes_revision` is set to 1)
- `blank_plan` - "Garden", a second plan with no image (a 1600x1000 blank canvas)
- `make_png(width, height, color=...)` - module helper (not a fixture) that
  builds a PNG in-process; import it from `tests.fixtures.locations`

### `sandbox.py`

The throwaway demo behind the "try a test event" button, minted through
`logic.sandbox.service` — the same call `POST /auth/sandbox` makes:

- `make_sandbox(*, role="helper", language="en")` - factory; several tests need
  two demos side by side
- `test_sandbox` - one helper-role demo, already seeded
- `SandboxSetup` - what comes back: `.event`, `.guest`, `.session`

Deliberately no manager-role fixture. Seeding `role="manager"` currently raises
(see the xfails in `tests/logic/test_sandbox_seed.py`), and a fixture that
raises is a setup *error* that no `xfail` marker can absorb — the tests that
need that variant call the factory in their own body.

### `auth.py`

Factories for the hand-rolled authentication stack. These mint **real** HS256
tokens through `app.core.security`, so a test using them exercises exactly the
code path a browser's token takes:

- `make_access_token(user, *, session_id=None)` - a valid access token
- `auth_headers(user, *, session_id=None)` - `{"Authorization": "Bearer …"}`
- `make_expired_access_token(user)` - correctly signed, `exp` in the past
- `make_tampered_access_token(user)` - correct claims, wrong signing key

### `client.py`

FastAPI app and HTTP client fixtures:

- `app` - FastAPI app with `get_db` + identity dependency overrides
- `async_client` - HTTP client that is always signed in as `test_user`
- `unauthenticated_app` / `unauthenticated_client` - the app with **no** identity
  override, so `deps.py` runs for real
- `as_admin` / `as_event_admin` / `as_outsider` - temporarily swap the identity

Pick the right client. `async_client` pins `CurrentUser`, which is what makes
route tests about the route rather than about authentication — but it also means
a request it sends is *already signed in*, so a login or register test written
against it would pass while the whole credential path was broken. Use
`unauthenticated_client` (with `auth_headers` when a credential is wanted) for
anything under `/auth`.

## Usage

All fixtures are automatically imported via `conftest.py` and are available to any test file in the `tests/` directory.

Example:

```python
async def test_something(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    # Test code here
    pass
```

Signing in for real:

```python
async def test_authenticated_route(
    unauthenticated_client: AsyncClient,
    auth_headers: AuthHeadersFactory,
    test_user: User,
):
    r = await unauthenticated_client.get(
        "/api/v1/users/me", headers=auth_headers(test_user)
    )
    assert r.status_code == 200
```

## Adding New Fixtures

When adding new fixtures:

1. Add them to the appropriate domain file (or create a new one if needed)
2. Import them in `conftest.py` to make them available to tests — fixtures never
   live in `conftest.py` itself, which only re-exports
3. Update this README with the new fixture name and description
