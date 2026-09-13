set shell := ["bash", "-cu"]
set windows-shell := ["C:/Program Files/Git/bin/bash.exe", "-cu"]

# Dev mode: "docker" (full stack via Docker Compose watch) or "local" (direct processes).
# Change this value to switch the default for all dev/test recipes.
dev_mode := "local"

# Default: list available recipes
default:
    @just --list

# ── Development ───────────────────────────────────────────────

# Start dev environment (respects DEV_MODE env var, default: "docker")
dev mode=dev_mode:
    if [ "{{mode}}" = "docker" ]; then docker compose watch; elif [ "{{mode}}" = "local" ]; then docker compose up db adminer -d && echo "" && echo "DB + Adminer started. Open two terminals and run:" && echo "  just dev-backend" && echo "  just dev-frontend"; else echo "Unknown mode '{{mode}}'. Use 'docker' or 'local'." && exit 1; fi

# Start backend dev server directly (no Docker)
dev-backend:
    cd backend && uv run fastapi dev app/main.py --port 8787 --reload-exclude .venv

# Start frontend dev server directly (no Docker)
dev-frontend:
    cd frontend && pnpm dev

# ── Linting & Formatting ─────────────────────────────────────

# Lint backend (ruff + basedpyright)
lint-backend:
    cd backend && uv run ruff check app && uv run ruff format app --check && uv run basedpyright app

# Format backend (ruff)
format-backend:
    cd backend && uv run ruff check app scripts --fix && uv run ruff format app scripts

# Lint frontend (eslint)
lint-frontend:
    cd frontend && pnpm lint

# Format frontend (prettier)
format-frontend:
    cd frontend && pnpm format

# Fail if the en/de locale trees have drifted apart
check-locales:
    node scripts/pre-commit/check_locale_parity.js

# Lint everything
lint: lint-backend lint-frontend check-locales

# Format everything
format: format-backend format-frontend

# ── Testing ───────────────────────────────────────────────────

# Run backend tests with coverage (delegates to the same script CI runs, so the
# reported total cannot diverge from the CI number)
test-backend:
    cd backend && uv run bash scripts/test.sh

# Run frontend unit tests (Vitest)
test-frontend:
    cd frontend && pnpm test:unit

# Run frontend unit tests with coverage
test-frontend-coverage:
    cd frontend && pnpm test:unit:coverage

# Run frontend type check (app sources, then the unit tests)
type-check:
    cd frontend && pnpm type-check && pnpm type-check:unit

# Regenerate the golden fixtures the useShiftPreview parity tests assert against.
# Run this whenever app/logic/shift_generator.py changes.
dump-shift-fixtures:
    cd backend && uv run python scripts/dump_shift_generator_fixtures.py

# Run Playwright e2e tests. Extra playwright flags are passed through.
# e.g.: just test-e2e --headed --project=chromium
test-e2e *args:
    if [ "{{dev_mode}}" = "docker" ]; then docker compose run --rm playwright npx playwright test {{args}}; else cd frontend && pnpm exec playwright test {{args}}; fi

# ── Docker E2E (full stack) ──────────────────────────────────────

# Run E2E tests against full Docker stack. Any extra args (test paths, --grep,
# --headed, --project=...) are forwarded to Playwright.
#   just e2e tests/authenticated/tasks.spec.ts
#   just e2e --grep "tasks" --headed
e2e *args:
    node scripts/run-e2e-docker.mjs {{args}}

# Start Docker E2E stack without running tests
e2e-up:
    node scripts/run-e2e-docker.mjs --up-only

# Stop Docker E2E stack
e2e-down:
    node scripts/run-e2e-docker.mjs --down

# Re-run E2E tests against an already-running stack (started via `just e2e-up`).
# Extra args are forwarded to Playwright — pass a spec path to run one test:
#   just e2e-rerun tests/authenticated/tasks.spec.ts
#   just e2e-rerun --grep "bookings"
e2e-rerun *args:
    node scripts/run-e2e-docker.mjs --no-build --no-teardown {{args}}

# Show logs for an e2e service (e.g., just e2e-logs backend)
e2e-logs service *args:
    docker compose -p wirksam-e2e -f docker-compose.e2e.yml logs {{service}} {{args}}

# ── Database ──────────────────────────────────────────────────

# Run Alembic migrations
migrate:
    cd backend && uv run alembic upgrade head

# Create a new Alembic migration (usage: just migration "add users table")
migration message:
    cd backend && uv run alembic revision --autogenerate -m "{{message}}"

# Fail if the SQLModel models and the migration history have diverged.
# Requires a running DB (`just dev` or `docker compose up db -d`).
check-migrations:
    cd backend && uv run alembic upgrade head && uv run alembic check

# Seed the database with demo data
seed:
    cd backend && uv run python -m app.scripts.initial_data

# ── Code Generation ──────────────────────────────────────────

# Regenerate the changelog JSON from markdown files
generate-changelog:
    cd frontend && pnpm generate-changelog

# Regenerate frontend/e2e/COVERAGE.md from `playwright test --list`.
# Collection only — starts no stack and no browser, so it is safe to run anytime.
generate-e2e-coverage:
    cd frontend && pnpm generate-e2e-coverage

# Regenerate the frontend API client from backend OpenAPI spec
generate-client:
    cd backend && uv run python -c "import app.main; import json; print(json.dumps(app.main.app.openapi()))" > ../frontend/openapi.json
    cd frontend && pnpm generate-client
    cd frontend && pnpm exec prettier --write ./src/client
    rm -f frontend/openapi.json

# ── Upstream Sync ─────────────────────────────────────────────

# Add the upstream template remote (run once after forking)
add-upstream url:
    python scripts/sync_upstream.py --add-remote {{url}}

# Fetch and merge upstream template changes into your fork
sync-upstream remote="upstream" branch="main":
    python scripts/sync_upstream.py --remote {{remote}} --branch {{branch}}

# ── Screenshots ─────────────────────────────────────────────

# Take screenshots for landing page and How It Works (usage: just screenshots, just screenshots de)
screenshots lang="en":
    cd frontend && LANG={{lang}} pnpm exec playwright test --config=scripts/screenshots.config.ts

# ── Build & Deploy ────────────────────────────────────────────

# Build frontend for production
build-frontend:
    cd frontend && pnpm build

# Build Docker images
build tag="latest":
    TAG={{tag}} FRONTEND_ENV=production docker compose -f docker-compose.yml build


# ── Release ────────────────────────────────────────────────────

# Create a new release: updates version files, commits, tags, and creates a GitHub release
# Usage: just release 1.2.3
release version:
    echo "{{version}}" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$' || (echo "Error: '{{version}}' is not valid semver (expected: X.Y.Z or X.Y.Z-pre.1)" && exit 1)
    # The bump is committed to whatever branch is checked out, but pushed and
    # tagged as main. Released from anywhere else that combination strands the
    # commit on the wrong branch, prints "Everything up-to-date", and still cuts
    # a release — from a main that never got the bump. Refuse instead.
    test "$(git rev-parse --abbrev-ref HEAD)" = "main" || (echo "Error: release must be run on main (you are on $(git rev-parse --abbrev-ref HEAD))" && exit 1)
    git diff --quiet HEAD -- VERSION || (echo "Error: VERSION has uncommitted changes" && exit 1)
    git fetch origin main --quiet
    test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" || (echo "Error: main is not in sync with origin/main — push or pull first" && exit 1)
    echo "{{version}}" > VERSION
    git add VERSION
    git diff --cached --quiet || git commit -m "release: v{{version}}"
    git push origin main
    gh release create "v{{version}}" --generate-notes --title "v{{version}}" --target main --repo Blaxzter/wirksam

# ── Pre-commit ────────────────────────────────────────────────

# Run all pre-commit hooks
pre-commit:
    cd backend && uv run pre-commit run --all-files
