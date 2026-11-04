# Task: Run E2E Tests Against a Full Docker Stack

## Overview

Instead of running Playwright inside a Docker container (`docker compose run --rm playwright`), we spin up the full backend stack in Docker and run Playwright tests from the **host machine**. This gives us:

- A reproducible, isolated backend (fresh DB every run, no leftover state)
- RAM-backed PostgreSQL (tmpfs) for faster test execution
- Full debugging capabilities (--headed, traces, DevTools) since Playwright runs on the host
- Log collection on teardown
- A separate Docker project (`wirksam-e2e`) that doesn't interfere with the dev stack

## Architecture

```
Host machine                         Docker (wirksam-e2e)
┌──────────────────┐                ┌────────────────────────┐
│  Playwright       │───:5555──────▶│  frontend (Vite dev)   │
│  (npx playwright) │               │  VITE_E2E_AUTH_BYPASS  │
│                   │               └────────────────────────┘
│  Fixtures call    │               ┌────────────────────────┐
│  /testing/seed    │───:8787──────▶│  backend (FastAPI)     │
│  /testing/reset   │               │  TESTING=true          │
│                   │               └───────────┬────────────┘
│                   │               ┌───────────▼────────────┐
│                   │               │  db (Postgres, tmpfs)  │
│                   │               └────────────────────────┘
│                   │               ┌────────────────────────┐
│                   │───:1080──────▶│  mailcatcher           │
└──────────────────┘               └────────────────────────┘
```

The browser (launched by Playwright on the host) loads `http://localhost:5555` (Docker frontend), which makes API calls to `http://localhost:8787/api/v1` (Docker backend). Playwright's `reuseExistingServer: true` detects the Docker frontend on port 5555 and skips starting its own dev server.

## Files

| File | Purpose |
|---|---|
| `docker-compose.e2e.yml` | Standalone compose file — db, prestart, backend, frontend, mailcatcher |
| `scripts/run-e2e-docker.mjs` | Orchestrator: build, start, health-check, test, collect logs, teardown |
| `justfile` (e2e-* recipes) | Shorthand commands |
| `e2e-logs/` | Container logs collected on each run (gitignored) |

## Quick Reference

```bash
# Full run: build images, start stack, run all tests, teardown
just e2e

# Start stack only (for manual exploration or repeated test runs)
just e2e-up

# Re-run tests against a running stack (no rebuild, no teardown)
just e2e-rerun
just e2e-rerun --grep "settings"

# Stop the stack
just e2e-down

# Pass any Playwright flags through
just e2e --grep "login"

# Tail live logs for a service
just e2e-logs backend
just e2e-logs backend --follow
```

## Typical Workflows

### One-shot CI-style run

```bash
just e2e
```

Builds images, starts everything, runs all Playwright tests, collects container logs to `e2e-logs/`, and tears down. Exit code reflects test results.

### Iterative development

```bash
# Start the stack once
just e2e-up

# Make changes, then re-run specific tests (fast — no build/teardown)
just e2e-rerun --grep "bookings"

# Check backend logs if something looks wrong
just e2e-logs backend --tail 50

# Done for the day
just e2e-down
```

### Debugging a flaky test

```bash
just e2e-up

# Run headed so you can watch the browser
cd frontend && VITE_E2E_AUTH_BYPASS=true VITE_API_URL=http://localhost:8787/api/v1 \
  npx playwright test tests/authenticated/flaky.spec.ts --headed --retries=0

just e2e-down
```

## How It Works (script internals)

`scripts/run-e2e-docker.mjs` does the following:

1. **Pre-flight**: Checks `.env` exists (needed for Auth0 credentials)
2. **Build**: `docker compose build` (skipped with `--no-build`)
3. **Start**: `docker compose up -d`
4. **Health checks**:
   - PostgreSQL: polls `docker compose ps db` until health status is "healthy"
   - Backend: polls `GET http://localhost:8787/api/v1/healthz` (up to 40 attempts, 10s apart)
   - Frontend: polls `GET http://localhost:5555` (up to 20 attempts, 5s apart)
5. **Tests**: Runs `npx playwright test` from `frontend/` with env vars:
   - `VITE_API_URL=http://localhost:8787/api/v1`
   - `VITE_E2E_AUTH_BYPASS=true`
   - `PLAYWRIGHT_HTML_OPEN=never`
6. **Log collection**: Saves each service's logs to `e2e-logs/<timestamp>/`
7. **Teardown**: `docker compose down --remove-orphans -v` (skipped with `--no-teardown`)

## Docker Compose Details

The `docker-compose.e2e.yml` file is **standalone** — it does not layer on top of `docker-compose.yml` or `docker-compose.override.yml`. It uses `env_file: .env` to pull in Auth0 credentials and Postgres config, then overrides networking-specific values:

- `POSTGRES_SERVER=db` (Docker hostname, not localhost)
- `SMTP_HOST=mailcatcher` (Docker hostname), with `SMTP_USER` / `SMTP_PASSWORD`
  blanked: mailcatcher offers no login, so a real mail account in `.env` would
  make every mail fail with "Failed to send"
- `TESTING=true` (enables `/testing/*` endpoints and `X-Test-User-Email` bypass)
- `VITE_E2E_AUTH_BYPASS=true` (frontend skips real Auth0)

The database uses `tmpfs` instead of a named volume — data lives in RAM and is discarded on container stop. This makes tests faster and guarantees a clean slate every run.

Only the ports Playwright and you need are published on the host: 5555 (frontend),
8787 (backend) and 1080 (mailcatcher's inbox). Mailcatcher's SMTP port 1025 stays
inside the compose network, where the backend reaches it, so another project's
mail server on host port 1025 does not stop the stack from starting.

## Troubleshooting

| Problem | Fix |
|---|---|
| `.env file not found` | Copy `.env.example` to `.env` and fill in Auth0 values |
| Port 8787/5555 already in use | Stop your local dev servers or the dev Docker stack first |
| Port 1080 already in use | Another mailcatcher (the dev stack's, or another project's) holds the inbox port; stop it first |
| Backend never becomes healthy | Check `just e2e-logs backend` and `just e2e-logs prestart` for migration errors |
| Tests pass locally but fail in Docker | Check if tests depend on local filesystem state or non-deterministic ordering |
| Stale images after code changes | Run `just e2e` (builds by default) or `just e2e-down` then `just e2e` |
