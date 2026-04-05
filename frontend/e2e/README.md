# E2E Testing

## Overview

E2E tests use [Playwright](https://playwright.dev/) and run in two modes:

- **Isolated mode** (default): No Auth0 dependency. Tests use a fake Auth0 plugin and seed test users directly in the database via backend API. This is what runs locally and in CI.
- **Auth0 mode**: Uses real Auth0 login. Set `USE_AUTH0_E2E=true` in `frontend/.env` to enable. Only needed if you want to test the actual Auth0 login flow.

## How the Auth0 Bypass Works

The bypass has three layers:

### 1. Frontend: Fake Auth0 Plugin

When `VITE_E2E_AUTH_BYPASS=true` is set in `frontend/.env`, `main.ts` provides a fake Auth0 plugin instead of the real SDK. This fake plugin:

- Reports `isAuthenticated: true` and `isLoading: false`
- Returns `'fake-test-token'` from `getAccessTokenSilently()`

The `authGuard` in `router/index.ts` is replaced with a no-op in bypass mode since the real guard reads from an internal Auth0 SDK singleton that can't be mocked externally.

### 2. Backend: Test Auth Middleware

When `TESTING=true` (defaults to `true` when `ENVIRONMENT=local`), the backend:

- Monkey-patches `auth0.require_auth()` to a no-op that returns dummy JWT claims
- Checks for `X-Test-User-Email` header in every authenticated endpoint. If present, looks up the user by email instead of validating a JWT
- Exposes `POST /testing/seed` and `POST /testing/reset` endpoints for user management

### 3. Playwright Fixtures (`e2e/fixtures.ts`)

The custom fixtures handle the glue:

- **`adminUser` / `memberUser`** (worker-scoped): Seed a test user per parallel worker via `POST /testing/seed`. Each worker gets unique users like `admin-worker-0@test.example.com`.
- **`adminPage` / `memberPage`** (test-scoped): Create a fresh browser context with:
  - `addInitScript` that pre-seeds localStorage (Auth0 SDK cache, locale, changelog)
  - `page.route()` interception that adds `X-Test-User-Email` header to all API requests
  - A warm-up navigation to `/app/home` to ensure the profile loads before the test starts

```
Playwright Worker                    Frontend (Vite)                 Backend (FastAPI)
─────────────────                    ───────────────                 ─────────────────
seed user via POST /testing/seed ──────────────────────────────────► Create user in DB
                                                                    (auth0_sub = "test|email")
create browser context
├─ addInitScript: pre-seed localStorage
├─ page.route: add X-Test-User-Email header
└─ goto /app/home (warm-up)
                                     main.ts sees VITE_E2E_AUTH_BYPASS
                                     ├─ Provides fake Auth0 plugin
                                     ├─ authGuard = no-op
                                     └─ getAccessTokenSilently → "fake-test-token"

                                     POST /users/me ──────────────► X-Test-User-Email header
                                     (with fake token)               → look up user by email
                                                                     → return profile
                                     ◄─ UserProfile (admin, active)

                                     App renders dashboard ✓
```

## Running Tests

### Local Development

Prerequisites: backend running with `ENVIRONMENT=local` and `VITE_E2E_AUTH_BYPASS=true` in `frontend/.env`.

```bash
# Run all tests
pnpm test:e2e

# Run a specific test file
pnpm exec playwright test admin-user-actions.spec.ts

# Run a specific test by name
pnpm exec playwright test -g "approval password section is visible"

# Run with visible browser
HEADED=true pnpm test:e2e

# Run a specific project (authenticated, member, multi-user, public)
pnpm exec playwright test --project=chromium
```

### CI (GitHub Actions)

The workflow in `.github/workflows/playwright.yml` runs tests via Docker Compose with 4 shards. The `docker-compose.yml` sets `TESTING=true` and `VITE_E2E_AUTH_BYPASS=true` for the backend and frontend containers respectively.

Key CI differences:

- Uses `preview` server (port 4173) instead of dev server
- Retries failed tests up to 2 times
- Runs with 1 worker per shard (no parallelism within a shard)
- Reports are merged across shards and uploaded as artifacts

## Writing Tests

### Import from fixtures, not `@playwright/test`

```typescript
// Correct
import { test, expect } from '../../fixtures.js'

// Wrong — won't have auth bypass
import { test, expect } from '@playwright/test'
```

### Use `adminPage` or `memberPage`

```typescript
// Admin test
test('admin can see users', async ({ adminPage: page }) => {
  await page.goto('/app/admin/users')
  await expect(page.getByTestId('users-table')).toBeVisible()
})

// Member test
test('member cannot see admin link', async ({ memberPage: member }) => {
  await member.goto('/app/home')
  await expect(member.getByTestId('sidebar-link-admin-users')).toBeHidden()
})

// Multi-user test
test('admin sees member data', async ({ adminPage, memberPage }) => {
  // member does something
  await memberPage.goto('/app/events')
  // admin sees the result
  await adminPage.goto('/app/admin/users')
})
```

### Public tests don't need fixtures

Tests under `tests/public/` don't require auth and can import directly from `@playwright/test`.

### Test data isolation

Each test should create its own data and clean up after:

```typescript
import { createEventWithSlots, deleteEvent } from '../../helpers/api.js'

let created: EventWithSlots

test.beforeEach(async ({ adminPage: page }) => {
  created = await createEventWithSlots(page, { name: 'My Test Event' })
})

test.afterEach(async ({ adminPage: page }) => {
  await deleteEvent(page, created.event.id).catch(() => {})
})
```

Never assert on global state like "there is exactly 1 event". Each parallel worker has its own users, but they share the same database, so other workers' data may be visible.

## Project Structure

```
e2e/
├── fixtures.ts              # Test fixtures (adminPage, memberPage, user seeding)
├── helpers/
│   └── api.ts               # API helpers (createEvent, bookSlot, etc.)
├── setup/
│   ├── auth.setup.ts        # Auth0 login setup (Auth0 mode only)
│   ├── auth-member.setup.ts # Auth0 member login (Auth0 mode only)
│   └── test-reset.setup.ts  # Reset test data (isolated mode)
├── tests/
│   ├── authenticated/       # Admin user tests
│   ├── member/              # Member (non-admin) tests
│   ├── multi-user/          # Cross-user interaction tests
│   └── public/              # Pre-auth public page tests
├── COVERAGE.md              # Test coverage summary
└── README.md                # This file
```

## Environment Variables

| Variable                    | Where                | Purpose                                                                                    |
| --------------------------- | -------------------- | ------------------------------------------------------------------------------------------ |
| `VITE_E2E_AUTH_BYPASS`      | `frontend/.env`      | `true` enables fake Auth0 plugin (requires Vite restart)                                   |
| `USE_AUTH0_E2E`             | `frontend/.env`      | `true` uses real Auth0 login in Playwright config                                          |
| `TESTING`                   | Backend env / `.env` | `true` enables `/testing/*` endpoints and auth bypass (auto-true when `ENVIRONMENT=local`) |
| `E2E_AUTH0_USERNAME`        | `frontend/.env`      | Admin email for Auth0 mode                                                                 |
| `E2E_AUTH0_PASSWORD`        | `frontend/.env`      | Admin password for Auth0 mode                                                              |
| `E2E_AUTH0_USERNAME_MEMBER` | `frontend/.env`      | Member email for Auth0 mode                                                                |
| `E2E_AUTH0_PASSWORD_MEMBER` | `frontend/.env`      | Member password for Auth0 mode                                                             |

## Troubleshooting

**Tests redirect to Auth0 login**: `VITE_E2E_AUTH_BYPASS` is not `true` or the Vite dev server wasn't restarted after adding it.

**Tests hang on `networkidle`**: The SSE `/notifications/stream` endpoint keeps a connection open. Don't use `waitUntil: 'networkidle'` in test fixtures or tests.

**`Test user not found` errors from backend**: The seed endpoint wasn't called or the reset endpoint deleted the user. Check that `test-reset.setup.ts` runs before the test project.

**Two Chrome windows open**: Playwright's `webServer` config may launch a second dev server. If your dev server is already running, this is harmless — it detects the existing server and reuses it.
