# E2E Testing

## Overview

E2E tests use [Playwright](https://playwright.dev/). There is one mode: test
users are seeded straight into the database and the browser is handed a session
instead of signing in. There used to be a second mode behind `USE_AUTH0_E2E`
that drove the hosted Auth0 login; it went with Auth0 itself.

The four screens that *do* sign in for real — `/login`, `/register`,
`/forgot-password` and what they link to — are covered by the `auth` project
under `tests/auth/`, which runs anonymously against the real endpoints.

## How the sign-in bypass works

It survived the move off Auth0 on purpose. In CI the Playwright browser runs in
a container where the page origin and `VITE_API_URL=http://backend:8787` are
genuinely cross-site, so the `SameSite=Lax` refresh cookie a real login depends
on is silently dropped — and `SameSite=None` needs `Secure` needs HTTPS. A suite
built on real logins would pass on a developer's machine and fail in CI.

Three layers, and no two of them work without the third:

### 1. Frontend: a session installed rather than earned

When `VITE_E2E_AUTH_BYPASS=true` **and** the run sets an `e2e_bypass=1` cookie,
`main.ts` calls `installFakeSession()` from `src/testing/fake-session.ts`
instead of restoring a session from the refresh cookie. That reads the
impersonated user out of the `wirksam-e2e-user` localStorage entry the fixtures
plant, hands `lib/auth-session.ts` a session containing the string
`fake-test-token`, and stubs out `bootstrap()` so the app's own
`POST /auth/refresh` cannot 401 the planted session away again.

`router/index.ts` stands the real navigation guard down under the same two
gates.

### 2. Backend: the `X-Test-User-Email` header

When `TESTING=true` (which it is whenever `ENVIRONMENT=local`), the backend:

- resolves the caller from an `X-Test-User-Email` header when one is present,
  **before** it looks at `Authorization` — which is why the fake token above
  never has to be a real one
- exposes `POST /testing/seed` and `POST /testing/reset` for user management

### 3. Playwright fixtures (`e2e/fixtures.ts`)

The custom fixtures are the glue:

- **`adminUser` / `memberUser`** (worker-scoped): seed a test user per parallel
  worker via `POST /testing/seed`. Each worker gets its own addresses, like
  `admin-worker-0@test.example.com`.
- **`adminPage` / `memberPage` / `disposablePage`** (test-scoped): a fresh
  browser context with
  - the `e2e_bypass=1` cookie
  - an `addInitScript` planting `wirksam-e2e-user`, the locale and the
    last-seen-changelog version
  - a `page.route()` interception adding `X-Test-User-Email` to every API request
  - a warm-up navigation to `/app/home` so the profile is loaded before the test
    body runs

```
Playwright Worker                    Frontend (Vite)                 Backend (FastAPI)
─────────────────                    ───────────────                 ─────────────────
seed user via POST /testing/seed ──────────────────────────────────► Create user in DB
                                                                    (subject = "test|email")
create browser context
├─ cookie: e2e_bypass=1
├─ addInitScript: wirksam-e2e-user, locale, changelog
├─ page.route: add X-Test-User-Email header
└─ goto /app/home (warm-up)
                                     main.ts sees both gates open
                                     ├─ installFakeSession()
                                     ├─ authGuard = no-op
                                     └─ access token = "fake-test-token"

                                     GET /users/me ───────────────► X-Test-User-Email header
                                     (token ignored)                 → look up user by email
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

# Run a specific project (chromium, member, multi-user, public, auth, guest, a11y, mobile)
pnpm exec playwright test --project=chromium

# The sign-in / registration flows, which use no bypass
pnpm exec playwright test e2e/tests/auth --reporter=list
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

// Wrong — won't have the fixtures
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

### Tests under `tests/auth/` sign in for real

The `auth` project is the one place the bypass is deliberately switched off, so
that the screens a first-time visitor actually meets are exercised somewhere.
They get away with it in CI, where the page origin and `VITE_API_URL` are
cross-site, because login and registration answer with the access token in the
body — only a page *reload* would need the refresh cookie, and these specs never
reload. Three rules follow:

- `test.use({ storageState: { cookies: [], origins: [] } })` at the top of the
  file. An authenticated visitor is redirected straight off `/login` and
  `/register` by the router guard, and the test would then fail on a redirect
  rather than on what it meant to check.
- Pin the browser preferences by hand with `pinBrowserPreferences(page)` from
  `helpers/auth.js` before the first `goto`. There is no fixture planting the
  locale and the changelog version on these pages.
- Delete the accounts you create. An account that registered with a password has
  a `local|…` subject, and `POST /testing/reset` only removes `test|…` ones.
  `authTestEmail(testInfo)` gives a per-test address that a later run can delete
  again if a crash ever stops the teardown happening.

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
│   ├── api.ts               # API helpers (createEvent, bookSlot, etc.)
│   ├── a11y.ts              # axe-core scans, keyboard/focus helpers
│   ├── auth.ts              # helpers for the specs that sign in for real
│   ├── guest.ts             # a shared list in an event of its own, signed up to anonymously
│   └── shared-list-seed.ts  # an event with tasks to share, for the management specs
├── setup/
│   └── test-reset.setup.ts  # Reset test data before the test projects run
├── tests/
│   ├── a11y/                # Accessibility scans
│   ├── auth/                # Sign-in, registration, password recovery (no bypass)
│   ├── authenticated/       # Admin user tests
│   ├── guest/               # Shared-list public page and guest manage page (anonymous, no bypass)
│   ├── member/              # Member (non-admin) tests
│   ├── mobile/              # Phone viewport (Pixel 7): bottom drawers, card lists
│   ├── multi-user/          # Cross-user interaction tests
│   └── public/              # Pre-auth public page tests
├── COVERAGE.md              # Test coverage summary
└── README.md                # This file
```

## Environment Variables

| Variable               | Where                | Purpose                                                                                   |
| ---------------------- | -------------------- | ----------------------------------------------------------------------------------------- |
| `VITE_E2E_AUTH_BYPASS` | `frontend/.env`      | `true` lets a run install a session instead of signing in (requires a Vite restart)        |
| `TESTING`              | Backend env / `.env` | `true` enables `/testing/*` and the `X-Test-User-Email` header (auto-true when `ENVIRONMENT=local`) |

`VITE_E2E_AUTH_BYPASS` alone does nothing: the run also has to set an
`e2e_bypass=1` cookie, which the fixtures do and the `auth` project deliberately
does not.

## Troubleshooting

**Tests redirect to `/login`**: `VITE_E2E_AUTH_BYPASS` is not `true`, or the Vite dev server wasn't restarted after adding it. (Expected under `tests/auth/`, which signs in for real.)

**Tests hang on `networkidle`**: The SSE `/notifications/stream` endpoint keeps a connection open. Don't use `waitUntil: 'networkidle'` in test fixtures or tests.

**`Test user not found` errors from backend**: The seed endpoint wasn't called or the reset endpoint deleted the user. Check that `test-reset.setup.ts` runs before the test project.

**Two Chrome windows open**: Playwright's `webServer` config may launch a second dev server. If your dev server is already running, this is harmless — it detects the existing server and reuses it.
