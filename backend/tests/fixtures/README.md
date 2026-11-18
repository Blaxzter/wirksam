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

### `shared_lists.py`

Shared lists and their guests, written through `crud.shared_list` and
`crud.shared_list_guest.create`, the calls the routes make:

- `make_shared_list(*, event=None, tasks=None, excluded=(), created_by=None, status="live", ...)` -
  factory; defaults to a live list on `test_event` with `test_task`, made by
  `test_event_admin_user`. The other keywords are the list's settings
  (`ends_mode`, `ends_on`, `ask_email`, `ask_phone`, `show_names`, `max_per_person`, `title`)
- `test_shared_list` - that default list
- `make_list_guest(shared_list, *, name="Gast Eins", email=None, phone=None, language="de", shifts=())` -
  factory; a guest chain on the list, booked (confirmed, `shared_list_id` set) on each of `shifts`.
  Each booking carries its sign-up's person as a sign-up writes it: `show_first_name` is the
  list's `show_names == "first"`, `guest_name` and `guest_phone` the chain's name and phone
- `ListGuest` - what comes back: `.user`, `.guest` (the `shared_list_guests` row), `.bookings`

### `guest_signups.py`

Plain helpers (not fixtures) for the shared-list guest tests:

- `NOW_UTC` - 08:00 on 1 June 2026 in Berlin, after `test_shift` and before the
  shifts added here
- `freeze_clocks(monkeypatch, utc=NOW_UTC)` - both clocks at that instant
- `configure_smtp` / `disable_smtp` - guest mail deliverable or not; tests
  replace the sending itself
- `add_shift(db, task, *, day, start, end, max_bookings, location)` - a June shift
- `signup_body(shift, **fields)` - a public sign-up form
- `confirm_address(db, guest)` - "Ja, das bin ich" on the chain's mail link, as the route
  presses it (`guest_tokens.peek`, then `guest_account.confirm`); returns the account's key
- `pooled_family(db, shared_list, make_list_guest, first, second)` - Maria Muster on
  `first` and Tom Muster on `second`, one address and a phone each, Tom confirmed into
  Maria's guest account: one guest user, two people

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
