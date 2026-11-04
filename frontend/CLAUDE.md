# Frontend CI gates

These are the checks that fail *after* the obvious ones pass, so they are easy
to miss locally and cost a full CI round trip each. Run them before pushing.

## New files under src/lib, src/composables, src/stores need tests

`vitest.config.ts` sets `perFile: true` coverage thresholds — 90% for
`src/lib/**` and friends. A brand-new helper with no spec sits at 0% and fails
the build with:

```
ERROR: Coverage for lines (0%) does not meet "src/lib/**" threshold (90%) for src/lib/<file>.ts
```

Existing untested files are carved out by name in the config's `!(…)`
exceptions; new ones are not, and should not be added there without a reason.

```bash
pnpm test:unit:coverage   # this is the gate, not `pnpm test:unit`
```

## Generated files are committed and diffed

Three artefacts are produced by scripts and verified in CI. Regenerate and
commit them whenever their inputs change:

| File | Regenerate with | Changes when |
|------|-----------------|--------------|
| `e2e/COVERAGE.md` | `pnpm generate-e2e-coverage` | any E2E test is added, renamed or removed |
| `src/client/**` | `just generate-client` (repo root) | the backend OpenAPI schema changes |
| `src/changelog/generated/` | `pnpm generate-changelog` | a changelog entry is added (gitignored, but needed for type-check) |

`src/client/**` is the one that bites: **regenerate it after the backend change
is final**, not partway through. Deleting a router later leaves stale types
behind, and the `Generate Client` workflow will notice and push a correction
commit onto your branch — which you then have to rebase onto.

## The whole job, locally

```bash
pnpm exec eslint .                             # not `pnpm lint` — that auto-fixes
node ../scripts/pre-commit/check_locale_parity.js
pnpm generate-e2e-coverage && git diff --exit-code e2e/COVERAGE.md
pnpm generate-changelog
pnpm type-check                                # app, then e2e/ (tsc -p e2e/tsconfig.json)
pnpm type-check:unit                           # separate config; specs are type-checked too
pnpm test:unit:coverage
pnpm build-only
```

ESLint reports 4 pre-existing warnings (`playwright/no-conditional-in-test`).
CI does not pass `--max-warnings`, so warnings are tolerated; errors are not.

## Not a gate: where focus goes when a dialog closes

A dialog hands focus back to whatever had it when it opened. If that element is
gone, focus drops to `<body>` and a keyboard user starts over at the top of the
page.

**A `DropdownMenuItem` that opens a dialog** goes through `useMenuAction()`
(`src/composables/useMenuAction.ts`). An item that is a component of its own uses
`useMenuItemAction()`.

```vue
const menu = useMenuAction()

<DropdownMenuContent @close-auto-focus="menu.onCloseAutoFocus">
  <DropdownMenuItem @select="menu.after(() => (open = true))">
```

Opened straight from `@select`, or after `await nextTick()`, the dialog remembers
the vanished item: the menu plays its exit animation first and focuses its button
only after that.

**A row in a bottom sheet that opens a dialog** closes the sheet, does `await
nextTick()`, focuses the sheet's opener and only then opens the dialog
(`TaskActionSheet.vue`), or the dialog remembers the row. `DrawerContent.vue` gives
focus back when any sheet closes (`useFocusReturn`), because reka's Drawer only
does that for a `DrawerTrigger`. It leaves focus alone if focus has moved into
another dialog or the sheet's `@close-auto-focus` called `preventDefault()`. That
file is not stock shadcn, so re-adding it through the CLI loses this.
