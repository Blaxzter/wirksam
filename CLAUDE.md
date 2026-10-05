# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Package Managers

- **Backend:** `uv` only — never pip/pip3
- **Frontend:** `pnpm` only — never npm/yarn

## Common Commands

Use `just <command>` (see `justfile`) for most tasks.

### Development

Two modes, controlled by `dev_mode` at the top of `justfile` (default: `"local"`):

```bash
just dev               # Uses dev_mode default
just dev docker        # Full stack via Docker Compose watch (hot reload)
just dev local         # Starts DB+Adminer in Docker; run backend/frontend manually:
just dev-backend       #   terminal 1
just dev-frontend      #   terminal 2
```

`just test-e2e` also respects `dev_mode`: docker runs Playwright in a container, local runs `pnpm test:e2e` directly.

Local URLs: frontend `http://localhost:5555`, backend `http://localhost:8787`, OpenAPI docs `http://localhost:8787/docs`

### Linting & Formatting

```bash
just lint                     # Both backend + frontend
just lint-backend             # ruff + basedpyright
just lint-frontend            # ESLint
just format                   # Both
```

### Testing

```bash
just test-backend             # pytest with coverage (runs inside backend/)
bash ./backend/scripts/test.sh
pnpm --prefix frontend test:e2e   # Playwright E2E
```

Run a single backend test:
```bash
cd backend && uv run pytest tests/api/test_users.py::test_read_user -v
```

### Database Migrations

```bash
# Inside backend/ venv or container:
alembic revision --autogenerate -m "Add <feature>"
alembic upgrade head

# Or via just:
just migration "Add <feature>"
just migrate
just check-migrations   # fails if models and migrations have diverged
```

`alembic check` also runs in the *Test Backend* CI job, so a model change without
a matching migration fails the PR rather than surfacing at deploy time.

### API Client Generation

Run after any backend OpenAPI schema change:
```bash
just generate-client          # or: cd frontend && pnpm run generate-client
```

## Architecture Overview

### Stack

- **Backend:** FastAPI + SQLModel (async SQLAlchemy) + PostgreSQL + local JWT auth (bcrypt + PyJWT)
- **Frontend:** Vue 3 + TypeScript + Vite + Pinia + Vue Router + Tailwind CSS v4 + shadcn-vue
- **Infra:** Docker Compose + Traefik reverse proxy + GitHub Actions

### Backend Pattern (Model → Schema → CRUD → Route → Register)

```
backend/app/
├── models/        # SQLModel table definitions
├── schemas/       # Pydantic create/read/update schemas
├── crud/          # CRUDBase + per-model classes
├── api/routes/    # FastAPI routers (one file per domain)
├── api/api.py     # Router registration
├── logic/         # Business logic / services
└── core/          # config.py, db.py, security.py, rate_limit.py, errors.py
```

When adding a feature: model → schema → CRUD → route → register in `api/api.py` → Alembic migration.

### Auth Pattern

Signup is open by default: anyone who registers gets an active account, and
that account grants nothing on its own. A self-hosted deployment can restrict it
with `REGISTRATION_MODE` (`open` / `approval` / `invite`),
`REGISTRATION_ALLOWED_DOMAINS` and `REGISTRATION_INVITE_BYPASS`; the rules live
in `app/logic/auth/registration.py` and are described in
[`docs/AUTH.md`](docs/AUTH.md#who-may-register). **Authorisation lives on the event**, not on
the user — every event is its own tenancy with an `EventMembership` row per
participant (`owner` > `admin` > `member`). The single remaining global role is
`admin`, the platform superadmin, who passes every check.

Identity, from `backend/app/api/deps.py`:

- `CurrentUser` — validates the bearer JWT, loads the DB user, requires `is_active` and an approved registration; use for all protected endpoints
- `CurrentSuperuser` — platform superadmin only (user management, featuring events)
- `AnyUser` — same, minus those two checks, so a suspended or still-pending account can still read or delete its own profile
- `QueryTokenUser` — SSE only (`EventSource` cannot send headers, so the token arrives as `?token=…`)
- `AccessClaimsDep` — token claims without a DB hit, for the rare case where the *session* matters and the user row does not

`CurrentUser` **is** the full `User` row. There is no separate claims object and
no remote profile: the access token carries the user id (`sub`) and the session
id (`jti`) and nothing else, so identity is one primary-key lookup.

Per-event permission, from `backend/app/logic/permissions.py` — these two are
the *only* gates, so grepping for them finds every check:

- `require_event_role(user, session, event_id, minimum=...)` — for mutations; raises 403
- `require_event_visible(user, session, event)` — for reads; raises **404** (not 403) so a private event cannot be probed by id

For queries, `backend/app/logic/event_scope.py` returns the id list to filter
by. `None` means unrestricted (superadmin only); an **empty list means "nothing"
and must never be collapsed to `None`** — that would hand a new account the
whole database.

A visitor can also skip all of this: **`POST /auth/sandbox`** mints a throwaway
guest account plus one seeded event dated around today, opens the app straight
on the dashboard with the event preselected, and hard-deletes the lot on a TTL
sweep. Sandbox rows are invisible to every other account *including the
superadmin*, and the deletion order in `app/logic/sandbox/cleanup.py` is
load-bearing — read [`docs/SANDBOX.md`](docs/SANDBOX.md) before touching it.

Authentication itself lives under `/auth` (`backend/app/api/routes/auth.py` →
`app/logic/auth/`): register, login, refresh, logout, password reset, email
verification, session list. Access tokens are HS256, 15 minutes, held in memory
by the client; refresh tokens are opaque, 30 days, rotated on every use, stored
hashed in `auth_sessions`, and carried in an httpOnly cookie scoped to
`/api/v1/auth`. `GET /users/me` is a plain read — registration supplies the
profile, so there is no upsert on first login. Full description in
[`docs/AUTH.md`](docs/AUTH.md).

`app/logic/auth/service.py::sync_superadmin_role` is the only mechanism that
grants the platform `admin` role (from `SUPERADMIN_EMAILS`, on register **and**
sign-in). Without it a fresh deployment has no administrator.

Getting into an event: its admins invite by email or share a link
(`/events/{id}/invitations` → `/invitations/{token}/accept`), or someone asks
to join a **public** event and an event admin decides
(`/events/{id}/join-request` → `.../join-requests/{id}/decide`). Private events
are invitation-only. `is_featured` (superadmin-only) curates the home screen.

### Frontend Structure

```
frontend/src/
├── client/        # AUTO-GENERATED from OpenAPI — never hand-edit
├── stores/        # Pinia (auth.ts, breadcrumb.ts, dialog.ts)
├── router/        # Vue Router (PreAuth / PostAuth layouts + authGuard)
├── views/         # Page components (preauth/ and authenticated)
├── components/ui/ # shadcn-vue components — add via CLI only
├── locales/{en,de}/ # i18n JSON — both locales required
└── composables/   # Vue composables
```

Two layouts: `PreAuthLayout` (public pages) and `PostAuthLayout` (authenticated pages, wraps with `authGuard`).

### Frontend–Backend Connection

- API base path: `/api/v1`
- Frontend reads `VITE_API_URL` (set to `http://localhost:8787/api/v1` locally)
- Auto-generated client in `src/client/` handles auth tokens and typed requests

## Shell Commands

- **Never use `cd <dir> && <command>`** — this triggers an extra permission prompt. Instead use `--prefix`, `--cwd`, or run the command with an absolute/relative path directly (e.g., `pnpm --prefix frontend generate-changelog`, `uv run --directory backend pytest`).

## Key Rules

- **Tailwind CSS v4:** Config is CSS-only in `src/index.css` — do not create `tailwind.config.js`
- **shadcn-vue:** Add components via `npx shadcn-vue@latest add <component>` from `frontend/` — do not manually create files in `src/components/ui/`
- **i18n:** All user-facing strings must have keys in both `src/locales/en/` and `src/locales/de/`
- **Generated client:** Never edit `frontend/src/client/` — regenerate with `just generate-client` instead
- **API path:** `API_V1_STR = "/api/v1"` in `backend/app/core/config.py`
- **basedpyright:** Run `uv run basedpyright` (no arguments) inside `backend/` — never pass `.` as it bypasses the `include` config and crawls `.venv`

## Environment

- Root `.env` — used by Docker Compose (copy from `.env.example`); restart stack after changes
- `frontend/.env` — Vite env vars (copy from `frontend/.env.example`)
- `SECRET_KEY` in root `.env` signs the access tokens. It defaults to `changethis`, which is fine locally (a warning) and refuses to boot in every other environment. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- `SUPERADMIN_EMAILS` in root `.env` decides who gets the platform `admin` role on register or sign-in — set it before you expect to reach the admin screens
- `REGISTRATION_MODE` (`open`, `approval`, `invite`), `REGISTRATION_ALLOWED_DOMAINS` and `REGISTRATION_INVITE_BYPASS` in root `.env` decide who may sign up. `SUPERADMIN_EMAILS` always get in, so set those first before closing signup
- `TURNSTILE_SECRET_KEY` in root `.env` turns on the Cloudflare Turnstile bot check in front of
  registration; unset (the default) disables it, which is what local dev and the E2E suite run with.
  The matching public site key is `TURNSTILE_SITE_KEY`, served to the browser as runtime config —
  see [`docs/AUTH.md`](docs/AUTH.md) for the test keys that let you exercise it locally
- `SANDBOX_ENABLED` (default on), `SANDBOX_TTL_MINUTES` (60) and
  `SANDBOX_MAX_ACTIVE` (25) tune the "check out a test event" demo. The first is
  also served to the browser as runtime config, so the landing page never shows
  a button the backend would refuse — see [`docs/SANDBOX.md`](docs/SANDBOX.md)
- Local mail (verification, password reset) goes to the mailcatcher container on port 1025; its inbox is at `http://localhost:1080`. With no SMTP configured at all, the link is written to the backend log instead
- E2E tests authenticate through the `X-Test-User-Email` bypass, enabled by `VITE_E2E_AUTH_BYPASS` in `frontend/.env` and gated server-side on `TESTING`

## Template Cleanup (when starting a new project)

```bash
just remove-examples     # Remove demo views and example routes
just remove-domain       # Remove sample Projects/Tasks domain
just clean-template      # Both + regenerate client
```
