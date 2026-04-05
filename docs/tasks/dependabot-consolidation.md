# Task: Consolidate Dependabot PRs & Fix Vulnerability Alerts

## Overview

Periodically, Dependabot opens many small PRs and flags vulnerability alerts. Instead of merging each PR individually, we consolidate all dependency updates into a single branch, resolve conflicts, verify the build, and merge once.

## 1. Audit Current State

Check open Dependabot PRs and vulnerability alerts:

```bash
# List open Dependabot PRs
gh pr list --author "app/dependabot" --state open

# Count and list open vulnerability alerts
gh api repos/Blaxzter/wirksam/dependabot/alerts \
  --jq '[.[] | select(.state == "open")] | length'

gh api repos/Blaxzter/wirksam/dependabot/alerts \
  --jq '[.[] | select(.state == "open")] | sort_by(.security_advisory.severity) | .[] | "\(.security_advisory.severity) | \(.dependency.package.name) | \(.security_advisory.summary)"'
```

## 2. Update Dependencies Locally

### Frontend (npm packages)

Most alerts and PRs target the frontend. Update everything at once:

```bash
cd frontend

# Update all dependencies to latest compatible versions
pnpm update

# For major version bumps (review breaking changes first)
pnpm update --latest

# Check for remaining outdated packages
pnpm outdated
```

### Backend (Python packages)

```bash
cd backend

# Update all dependencies
uv lock --upgrade

# Or update a specific package
uv lock --upgrade-package <package-name>
```

### GitHub Actions

Update action versions in `.github/workflows/*.yml` manually based on the open Dependabot PRs. Match the versions Dependabot suggests.

### Docker base images

Update base image tags in Dockerfiles (`frontend/Dockerfile`, `backend/Dockerfile`) based on open Dependabot PRs.

## 3. Verify the Build

```bash
# Backend
just lint-backend
just test-backend

# Frontend
just lint-frontend
cd frontend && pnpm build

# E2E (optional but recommended)
just test-e2e
```

## 4. Commit with Consistent Message

Use this commit message format for all dependabot consolidation commits:
We dont use coauthor commits.

```
chore(deps): consolidate dependency updates

- Updated frontend npm packages
- Updated backend Python packages
- Updated GitHub Actions versions
- Updated Docker base images
- Resolved X Dependabot alerts
```

Adjust the bullet points to reflect what was actually updated. Keep the `chore(deps):` prefix consistent.

## 5. Push & Let PRs Auto-Close

Push to `dev` (or your working branch). Once merged to `main`, Dependabot PRs whose changes are already included will auto-close.

```bash
git push origin dev
```

After merging to `main`, verify PRs closed:

```bash
gh pr list --author "app/dependabot" --state open
```

Any remaining open PRs were not covered by the bulk update and need individual attention.

## 6. Dismiss Remaining Alerts

If any alerts persist after the update (e.g., transitive dependencies you can't control), review and dismiss with a reason:

```bash
gh api --method PATCH repos/Blaxzter/wirksam/dependabot/alerts/<alert_number> \
  -f state=dismissed -f dismissed_reason="tolerable_risk" \
  -f dismissed_comment="Transitive dep, no direct exposure"
```
