import vue from '@vitejs/plugin-vue'
import { URL, fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

/**
 * Standalone config — deliberately NOT `mergeConfig(viteConfig, …)`.
 *
 * `vite.config.ts` registers a `buildStart` plugin that shells out to
 * `pnpm generate-changelog`, and a `getGitVersion()` that shells out to `git`.
 * Neither is wanted on every unit-test run, so the two pieces the tests
 * actually need — the `@` alias and the `__APP_VERSION__` defines — are
 * restated here instead.
 */
export default defineConfig({
  plugins: [vue()],
  define: {
    __APP_VERSION__: JSON.stringify('0.0.0-test'),
    __APP_VERSION_DATE__: JSON.stringify('2026-01-01'),
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    // Vitest owns `src/**/__tests__/`, Playwright owns `e2e/` (its `testDir`).
    // The two globs cannot overlap, so neither runner can pick up the other's
    // files. `tsconfig.app.json` already excluded `src/**/__tests__/*` before
    // this config existed, which is why that location was chosen.
    include: ['src/**/__tests__/**/*.spec.ts'],
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
    // Node by default; the few DOM-bound suites opt in per file with
    // `// @vitest-environment jsdom`.
    environment: 'node',
    // Node 25+ ships its own `localStorage`, which stays undefined without
    // `--localstorage-file` and shadows the one jsdom provides. Turn it off so
    // the jsdom suites get theirs back. The `experimental` spelling is the one
    // Node 24 also accepts; 26 keeps it as an alias of `--no-webstorage`.
    execArgv: ['--no-experimental-webstorage'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/lib/**', 'src/composables/**', 'src/stores/**'],
      exclude: [
        // Generated from the OpenAPI schema — never hand-written, never tested.
        'src/client/**',
        // The tests themselves, and the golden fixtures they assert against.
        'src/**/__tests__/**',
      ],
      /**
       * Per-file, not aggregate — and deliberately not a number fitted to
       * today's total (#135).
       *
       * The distribution here is bimodal, not a bell curve: every file that has
       * a spec is at 100% (717/717 statements), and three have no spec at all.
       * Averaging those into one aggregate number would describe an accident of
       * history rather than any file, let a PR pay for deleting one store's
       * tests by covering something else, and only move when someone remembers
       * to raise it. A per-file floor answers the two questions a PR actually
       * raises: did this file get worse, and is this new file tested?
       *
       * 90 rather than 100 because the covered set is at 100% today — ten points
       * is headroom for a branch that is genuinely awkward to reach, not slack
       * for shipping untested code. Raise it when that stops being true.
       *
       * ── Why the globs look like this ──────────────────────────────────────
       * The three modules below have no spec yet. They cannot be given their
       * own `0` threshold entry as an exception, because vitest checks a
       * glob-matched file against the *global* thresholds as well ("Global
       * threshold is for all files, even if they are included by glob
       * patterns"). So there is no global entry at all; each covered area
       * carries the floor and names its own exceptions with `!(…)`.
       *
       * The exceptions are subtractions from a rule, so they stay inside the
       * coverage `include` and keep showing up at 0% in the report — the debt
       * stays visible instead of being excluded into silence. And because the
       * patterns are `**`-rooted, a *newly added* file anywhere under these
       * directories is matched, reported at 0% and fails. Deleting a name from
       * a `!(…)` list is the ratchet; the lists should only ever shrink.
       */
      thresholds: {
        perFile: true,

        'src/lib/**': { statements: 90, branches: 90, functions: 90, lines: 90 },

        // Exceptions:
        //  useAuthenticatedClient — wraps the generated client with token
        //    injection; needs the axios client and the auth store faked together.
        //  useAdaptiveCarouselHeight — measures real element heights through a
        //    ResizeObserver, which means nothing in jsdom's zero-height layout.
        'src/composables/**/!(useAuthenticatedClient|useAdaptiveCarouselHeight).ts': {
          statements: 90,
          branches: 90,
          functions: 90,
          lines: 90,
        },

        // Exception: auth — the roles, selected-event and profile store. The
        // largest single gap; it constructs `useAuthenticatedClient`, `useI18n`
        // and `useRouter` at setup time, so covering it means standing all
        // three up together — a mocking decision rather than just a spec file.
        // (The session half it used to wrap now lives in `src/lib/auth-session`
        // and `src/composables/useAuth`, both covered.)
        'src/stores/**/!(auth).ts': {
          statements: 90,
          branches: 90,
          functions: 90,
          lines: 90,
        },
      },
    },
  },
})
