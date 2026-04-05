# Task: Write Tests for New Features

## Overview

When a new backend feature is added, it needs tests covering CRUD, routes, and logic layers. This doc explains the test infrastructure and how to write tests that follow the established patterns.

## Test Infrastructure

Tests live in `backend/tests/` and use **pytest** + **pytest-asyncio**.

### Running Tests

```bash
just test-backend                          # all tests
cd backend && uv run pytest tests/crud/ -q # just CRUD tests
cd backend && uv run pytest tests/api/routes/test_bookings.py::TestBookingsRoutes::test_create_booking -v  # single test

# Coverage
cd backend && uv run coverage run -m pytest -q && uv run coverage report --show-missing
```

### Key Fixtures

| Fixture              | File                       | Description                                                                             |
| -------------------- | -------------------------- | --------------------------------------------------------------------------------------- |
| `db_session`         | `fixtures/database.py`     | Per-test async session with savepoint rollback. No cleanup needed.                      |
| `async_client`       | `fixtures/client.py`       | httpx client with `CurrentUser` → `test_user`, `CurrentSuperuser` → `test_admin_user`.  |
| `as_admin`           | `fixtures/client.py`       | Context manager — elevates `CurrentUser` to `test_admin_user` for admin-only endpoints. |
| `test_user`          | `fixtures/users.py`        | Active user, no roles.                                                                  |
| `test_admin_user`    | `fixtures/users.py`        | Active admin user (`roles=["admin"]`).                                                  |
| `test_inactive_user` | `fixtures/users.py`        | Inactive user.                                                                          |
| `test_event`         | `fixtures/events.py`       | Published event with dates in the future.                                               |
| `test_duty_slot`     | `fixtures/duty_slots.py`   | Duty slot linked to `test_event`.                                                       |
| `test_booking`       | `fixtures/bookings.py`     | Confirmed booking by `test_user` on `test_duty_slot`.                                   |
| `test_event_group`   | `fixtures/event_groups.py` | Published event group.                                                                  |

To add a new fixture, create or edit the relevant file in `tests/fixtures/` and import it in `tests/conftest.py`.

## Writing Tests for a New Feature

Follow the backend pattern: **Model → Schema → CRUD → Route → Register**.

### 1. CRUD Tests (`tests/crud/test_<model>.py`)

Test each custom method on the CRUD class. Use `db_session` directly.

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.widget import widget as crud_widget
from app.schemas.widget import WidgetCreate

@pytest.mark.asyncio
class TestCRUDWidget:
    async def test_create_widget(self, db_session: AsyncSession, test_user):
        widget_in = WidgetCreate(name="My Widget", owner_id=test_user.id)
        widget = await crud_widget.create(db_session, obj_in=widget_in)
        assert widget.name == "My Widget"
        assert widget.id is not None

    async def test_get_by_owner(self, db_session: AsyncSession, test_user):
        # ... create widget first, then test the query method
```

### 2. Route Tests (`tests/api/routes/test_<domain>.py`)

Use `async_client` for HTTP requests. Auth is already overridden.

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
class TestWidgetRoutes:
    async def test_create_widget(self, async_client: AsyncClient):
        r = await async_client.post("/api/v1/widgets/", json={"name": "W1"})
        assert r.status_code == 201
        assert r.json()["name"] == "W1"

    async def test_admin_only_endpoint(self, async_client: AsyncClient, as_admin):
        # `as_admin` makes CurrentUser return test_admin_user
        r = await async_client.delete("/api/v1/widgets/some-id")
        assert r.status_code == 204
```

### 3. Logic Tests (`tests/logic/test_<module>.py`)

For pure functions, test directly. For functions calling external services, use `unittest.mock.patch`.

```python
from unittest.mock import AsyncMock, patch
from app.logic.widget_service import process_widget

class TestWidgetService:
    @patch("app.logic.widget_service.external_api", new_callable=AsyncMock)
    async def test_process_widget(self, mock_api):
        mock_api.return_value = {"status": "ok"}
        result = await process_widget("widget-123")
        assert result.status == "ok"
```

## What to Cover

For each new feature, test at minimum:

- **CRUD**: Create, get, get_multi (with filters if any), update, delete, and any custom query methods
- **Routes**: Happy path for each endpoint, 404 for missing resources, 403 for unauthorized access, input validation (422)
- **Logic**: Core business logic, edge cases, error handling

## Conventions

- All test classes use `@pytest.mark.asyncio` (auto mode is on but class-level is explicit)
- Test method names: `test_<what_it_does>` (e.g., `test_create_booking`, `test_get_nonexistent_returns_404`)
- All URLs prefixed with `/api/v1/`
- Use `db_session` for setup data in route tests when needed (e.g., creating a notification before testing mark-as-read)

---

## E2E Tests (Playwright)

E2E tests live in `frontend/e2e/` and use Playwright with Chromium.

### Running E2E Tests

```bash
just test-e2e                                              # all E2E tests
cd frontend && pnpm exec playwright test tests/authenticated/bookings.spec.ts  # single file
cd frontend && pnpm exec playwright test --headed          # see browser
```

Requires `E2E_AUTH0_USERNAME`, `E2E_AUTH0_PASSWORD` (and `_MEMBER` variants) in `frontend/.env`.

### Infrastructure

| File                             | Purpose                                                   |
| -------------------------------- | --------------------------------------------------------- |
| `e2e/setup/auth.setup.ts`        | Logs in as admin, saves state to `e2e/.auth/user.json`    |
| `e2e/setup/auth-member.setup.ts` | Logs in as member, saves state to `e2e/.auth/member.json` |
| `e2e/helpers/api.ts`             | `api()`, `createEventWithSlots()`, `bookSlot()`, etc.     |
| `e2e/helpers/log-capture.ts`     | Captures backend logs on test failure                     |

### Test Organization

| Directory              | Auth context | Purpose                                |
| ---------------------- | ------------ | -------------------------------------- |
| `tests/public/`        | None         | Pre-auth pages (landing, about, etc.)  |
| `tests/authenticated/` | Admin        | Authenticated views and admin features |
| `tests/member/`        | Member       | Member-only RBAC and flows             |
| `tests/multi-user/`    | Both         | Cross-user scenarios                   |

### `data-testid` Convention

All E2E selectors use `data-testid` attributes instead of text or role-based selectors. This makes tests **locale-independent** — they work regardless of the user's language.

**Naming pattern:** `{context}-{element}` in kebab-case.

| Pattern        | Examples                                                               |
| -------------- | ---------------------------------------------------------------------- |
| Page heading   | `page-heading` (every view's h1)                                       |
| Sidebar links  | `sidebar-link-home`, `sidebar-link-events`, `sidebar-link-admin-users` |
| Action buttons | `btn-create-event`, `btn-cancel-booking`, `btn-back`, `btn-submit`     |
| Sections       | `section-duty-slots`, `section-reminders`, `section-stats`             |
| Stat cards     | `stat-card-events`, `stat-active`, `stat-pending`                      |
| Form inputs    | `input-search`, `input-event-name`, `input-approval-code`              |
| Channel cards  | `channel-email`, `channel-push`, `channel-telegram`                    |

**When adding a new view:** Add `data-testid="page-heading"` to the h1 and testids to all interactive elements. Then use `page.getByTestId()` in specs.

**When to use `getByText()` instead:** Only for dynamic data from test fixtures (event names, user names) — never for translated UI labels.

### Writing E2E Tests for a New View

Every new view should have at minimum a **smoke test** that verifies:

1. The page loads at its URL
2. The page heading is visible (`data-testid="page-heading"`)
3. Key interactive elements are present (via their `data-testid`)

```typescript
import { expect, test } from "@playwright/test";

test.describe("MyFeature – smoke", () => {
    test("page loads", async ({ page }) => {
        await page.goto("/app/my-feature");
        await expect(page).toHaveURL(/\/app\/my-feature/);
    });

    test("shows heading", async ({ page }) => {
        await page.goto("/app/my-feature");
        await expect(page.getByTestId("page-heading")).toBeVisible();
    });

    test("shows create button", async ({ page }) => {
        await page.goto("/app/my-feature");
        await expect(page.getByTestId("btn-create-widget")).toBeVisible();
    });
});
```

For features requiring test data, use the API helpers in `beforeEach`/`afterEach`:

```typescript
import {
    createEventWithSlots,
    deleteEvent,
    publishEvent,
} from "../../helpers/api.js";

let created: EventWithSlots;

test.beforeEach(async ({ page }) => {
    await page.goto("/app/events"); // need page context for API helpers
    created = await createEventWithSlots(page, { name: "Test Event" });
    await publishEvent(page, created.event.id);
});

test.afterEach(async ({ page }) => {
    await deleteEvent(page, created.event.id).catch(() => {});
});
```

For admin-only pages, add an RBAC test using the member auth state:

```typescript
test("member cannot access", async ({ browser }) => {
    const ctx = await browser.newContext({
        storageState: "e2e/.auth/member.json",
    });
    const member = await ctx.newPage();
    try {
        await member.goto("/app/admin/my-feature");
        await expect(member).not.toHaveURL(/\/app\/admin\/my-feature/, {
            timeout: 5000,
        });
    } finally {
        await ctx.close();
    }
});
```
