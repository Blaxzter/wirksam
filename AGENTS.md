# AI README

This document is for AI agents and contributors who need fast, accurate context and best practices for this repo. It combines the key points from the project READMEs and adds extra guidance that would be too long for the main docs.

## Quick Start (local)

Option A: Docker Compose (recommended for full stack)

```bash
docker compose watch
```

Option B: Run services locally

```bash
# Backend
cd backend
uv sync
fastapi dev app/main.py

# Frontend (separate terminal)
cd frontend
pnpm install
pnpm dev
```

Useful local URLs:

- Frontend: http://localhost:5555
- Backend API: http://localhost:8787
- OpenAPI docs: http://localhost:8787/docs

## Tech Stack (source of truth)

Backend

- FastAPI + Pydantic v2
- SQLModel (async SQLAlchemy) + Alembic
- PostgreSQL (psycopg + asyncpg)
- Local, database-backed authentication: bcrypt password hashing + HS256 JWTs (pyjwt)
- httpx for outbound HTTP
- Tooling: uv, Ruff, basedpyright, Pytest, pre-commit

Frontend

- Vue 3 + TypeScript + Vite
- Tailwind CSS v4
- shadcn-vue patterns (reka-ui components)
- Pinia + Vue Router
- Vee-Validate + Zod
- Vue I18n, VueUse
- OpenAPI client via @hey-api/openapi-ts
- Playwright, ESLint, Prettier
- pnpm

Infra

- Docker Compose, Traefik, GitHub Actions

## Repo Map

- `backend/` FastAPI app
- `backend/app/api/routes/` API endpoints (one file per domain)
- `backend/app/crud/` CRUD helpers (CRUDBase + per-model classes)
- `backend/app/models/` SQLModel models and base classes
- `backend/app/schemas/` Pydantic schemas (create/read/update)
- `backend/app/logic/` business logic/services
- `backend/app/core/` config, security, and infrastructure
- `frontend/src/components/ui/` shadcn-vue components (add via CLI, see below)
- `frontend/src/client/` auto-generated API client (do not hand-edit)
- `frontend/src/locales/{en,de}/` i18n translation JSON files

## Key Rules

- **Package managers:** Always use `pnpm` for frontend, `uv` for backend. Never use npm/yarn/pip.
- **shadcn-vue:** Add new UI components via `npx shadcn-vue@latest add <component>` from `frontend/`. Do not manually create files in `src/components/ui/`.
- **Tailwind CSS v4:** Config is CSS-based (`src/index.css`), not `tailwind.config.js`. Do not create a JS/TS config file.
- **i18n:** All user-facing strings must be translated. Add keys to both `src/locales/en/` and `src/locales/de/`.
- **Task runner:** Use `just <command>` (see `justfile` in repo root) for common tasks.
- **E2E tests:** Playwright tests live in `frontend/e2e/tests/` (split into `public/` and `authenticated/`).

## Environment Configuration

- Root `.env` is used by Docker Compose. See `.env.example` for required keys.
- Frontend uses `frontend/.env` (see `frontend/.env.example`).
- Authentication is built in; no identity-provider account is needed to run the stack.

Auth-related backend variables (root `.env`) — all have defaults, so a copied
`.env.example` boots:

- `SECRET_KEY` — signs the HS256 access tokens. Ships as `changethis`, which
  warns locally and **refuses to boot** in any other environment.
- `SUPERADMIN_EMAILS` — addresses that receive the platform `admin` role on
  register or sign-in. This is the only way the first administrator exists.
- `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`,
  `PASSWORD_MIN_LENGTH`, `REFRESH_COOKIE_*`, `EMAIL_*_TOKEN_EXPIRE_HOURS` —
  optional overrides, documented in `docs/AUTH.md`.

Frontend (`frontend/.env`):

- `VITE_API_URL`
- `VITE_E2E_AUTH_BYPASS` — enables the `X-Test-User-Email` impersonation the
  Playwright suite uses; the backend half is gated on `TESTING`.

## Backend Development Patterns

When adding a new feature:

1. Model: add a SQLModel in `backend/app/models/`.
2. Schemas: add create/read/update Pydantic schemas in `backend/app/schemas/`.
3. CRUD: extend `CRUDBase` in `backend/app/crud/`.
4. Routes: add a new router in `backend/app/api/routes/`.
5. Register the router in `backend/app/api/main.py`.
6. (Optional) Add service functions in `backend/app/logic/`.
7. Create Alembic migrations and commit them.

Auth pattern (per routes README):

- Use `CurrentUser` (from `app.api.deps`) for database-related endpoints that need:
    - User validation (exists in database, is active)
    - Role-based access control
    - Database user object access
- Use `CurrentSuperuser` for admin-only endpoints (e.g., delete, create users)
- Use `AnyUser` when a suspended account must still be served (`GET`/`DELETE /users/me`)
- Use `QueryTokenUser` for SSE endpoints only — `EventSource` cannot send headers
- There is no separate claims object: `CurrentUser` is the full `User` row, because
  the access token carries only the user id and the session id

Authentication endpoints (register, login, refresh, logout, password reset, email
verification, session management) live in `backend/app/api/routes/auth.py` over
`backend/app/logic/auth/`. Read `docs/AUTH.md` before touching any of it.

Database migrations:

```bash
# inside backend container or backend venv
alembic revision --autogenerate -m "Add <feature>"
alembic upgrade head
```

Testing:

```bash
bash ./scripts/test.sh
```

Linting:

```bash
uv run ruff check .
uv run basedpyright .
```

## Frontend Development Patterns

- Use existing shadcn-vue components from `src/components/ui/`; add missing ones via CLI.
- Keep routes in `src/router/` and feature views in `src/views/`.
- Use Pinia stores in `src/stores/` for app state.
- Add Zod schemas + Vee-Validate for forms.

Regenerate the API client when backend OpenAPI changes:

```bash
cd frontend
pnpm run generate-client
```

Testing and linting:

```bash
pnpm test:e2e
pnpm lint
pnpm format
```

## Cross-Cutting Conventions

- API base path is `/api/v1` (see `backend/app/core/config.py`).
- Keep schemas, CRUD, routes aligned; avoid logic in routers when it belongs in services.
- Use typed Pydantic schemas for all request/response bodies.
- Do not edit generated client code in `frontend/src/client/`.
- Prefer small, focused route modules with clear tags and prefixes.

## Gotchas

- Root `.env` values power Docker Compose services. Restart the stack after changes.
- The frontend expects `VITE_API_SERVER_URL` to include `/api/v1`.
- If you change models, create and apply Alembic migrations.

## Where to Read More

- `README.md` (root)
- `backend/README.md`
- `frontend/README.md`
- `docs/AUTH.md` (authentication: tokens, cookie, rotation, email flows, settings)
- `development.md`
- `deployment.md`
