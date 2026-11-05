# Task: Create a New Changelog Entry

## Overview

This describes the full process for writing a new changelog release, from figuring out what changed to publishing the final markdown files and images.

## 1. Determine the Last Released Version

Check which version was last released:

```bash
ls frontend/src/changelog/en/ | sort | tail -1
```

Note the version number (e.g., `v0.3.4`) and date.

## 2. Determine the Next Version

Follow semantic versioning:

- **Patch** (0.3.4 -> 0.3.5): Bug fixes, small UI tweaks
- **Minor** (0.3.4 -> 0.4.0): New features, new pages, significant UX changes
- **Major** (0.3.4 -> 1.0.0): Breaking changes, major redesigns

## 3. Gather Changes Since Last Release

Fetch the latest state from remote and diff against the last release point:

```bash
git fetch origin main
git log --oneline origin/main...HEAD
```

If the last release was tagged:

```bash
git log --oneline <last-release-tag>..origin/main
```

If there are no tags, find the commit of the last release date and diff from there:

```bash
git log --oneline --since="<last-release-date>" origin/main
```

Review the diff for user-facing changes:

```bash
git diff <last-release-commit>..origin/main -- backend/app/ frontend/src/
```

Focus on:

- New features or pages
- Changed UI behavior
- New settings or preferences
- Bug fixes that users would notice
- Backend changes that affect the user experience (new API endpoints, changed behavior)

Ignore:

- Internal refactors with no visible impact
- Dependency updates
- CI/CD changes
- Code style / linting fixes

## 4. Write the Changelog Files

### File naming

Format: `YYYY-MM-DD_vMAJOR.MINOR.PATCH.md`

Example: `2026-03-27_v0.3.5.md`

Create both files:

- `frontend/src/changelog/en/<date>_v<version>.md`
- `frontend/src/changelog/de/<date>_v<version>.md`

### File format

```markdown
---
title: <Short, descriptive release title>
version: <MAJOR.MINOR.PATCH>
date: <YYYY-MM-DDT12:00:00>
---

## <Feature or Section Heading>

<1-3 sentences explaining what changed and why it matters to the user.>

![Alt text describing the screenshot](./images/<image-name>.png)

## <Next Feature or Section Heading>

...
```

### Writing guidelines

- Write from the user's perspective -- what can they do now that they couldn't before?
- Keep it concise: 1-3 sentences per feature
- Use `##` for major sections, `###` for sub-points
- The German version is a proper translation, not a machine dump -- match tone and natural phrasing
- Avoid technical jargon; describe features in terms users understand

## 5. Add Screenshots (When Appropriate)

### When to include images

- New pages or views
- Significantly redesigned UI sections
- New interactive elements (buttons, menus, modals)
- Features that are easier to understand visually

### When to skip images

- Small text changes
- Bug fixes
- Backend-only changes
- Settings that are self-explanatory

### Image conventions

- Place in `frontend/src/changelog/images/en/` and `frontend/src/changelog/images/de/`
- Use kebab-case names: `notification-settings.png`, `calendar-sync.png`
- Both locales need their own screenshot (taken with the app in the respective language)
- If the UI looks identical in both languages, the same image can be used but must exist in both directories
- Keep file sizes reasonable (most existing images are under 200 KB)
- Reference in markdown as: `![Descriptive alt text](./images/<image-name>.png)`

## 6. Generate the Changelog JSON

After writing the markdown files:

```bash
cd frontend && pnpm generate-changelog
```

This processes all markdown files and outputs:

- `frontend/src/changelog/generated/en.json`
- `frontend/src/changelog/generated/de.json`

## 7. Verify

- Check the generated JSON files are valid and contain the new entry at the top (sorted by date, newest first)
- Run the dev server and navigate to `/changelog` to confirm rendering
- Switch between English and German to verify both versions display correctly
- Click any images to confirm the lightbox zoom works
- On mobile viewport, verify the swipeable carousel works with the new entry

## Quick Checklist

- [ ] Identified all user-facing changes since last release
- [ ] Chose correct version number (semver)
- [ ] Created `frontend/src/changelog/en/<date>_v<version>.md`
- [ ] Created `frontend/src/changelog/de/<date>_v<version>.md`
- [ ] Added screenshots to `frontend/src/changelog/images/en/` (if needed)
- [ ] Added screenshots to `frontend/src/changelog/images/de/` (if needed)
- [ ] Ran `pnpm generate-changelog` in `frontend/`
- [ ] Verified in browser (both locales, desktop + mobile)

## Keep the feature pages true

A release that changes how something works usually also changes what a feature page or guide says about it. They are Markdown in `frontend/src/docs/{en,de}/{feature,guide}/`, listed in `DOC_PAGES` in `frontend/src/lib/content-pages.ts`. Update them in the same change, in both languages. `frontend/src/lib/__tests__/docs-content.spec.ts` fails when the two languages drift apart, when a link points nowhere, or when a page names a screenshot that was never taken. New screenshots go into `frontend/scripts/take-screenshots.ts`, so the Screenshots workflow retakes them with every release.
