import { defineConfig, devices } from '@playwright/test'
import process from 'node:process'

/**
 * Read environment variables from file.
 * https://github.com/motdotla/dotenv
 */
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import dotenv from 'dotenv'

// Always load frontend/.env regardless of CWD (VS Code may run from workspace root)
const __dirname = dirname(fileURLToPath(import.meta.url))
dotenv.config({ path: resolve(__dirname, '.env') })

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: './e2e',
  /* Maximum time one test can run for. */
  timeout: 30 * 1000,
  expect: {
    /**
     * Maximum time expect() should wait for the condition to be met.
     * For example in `await expect(locator).toHaveText();`
     */
    timeout: 5000,
  },
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,
  /* Opt out of parallel tests on CI. */
  workers: process.env.CI ? 1 : undefined,
  /* Run tests within each file in parallel. */
  fullyParallel: true,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: process.env.CI ? 'blob' : 'html',
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Maximum time each action such as `click()` can take. Defaults to 0 (no limit). */
    actionTimeout: 5000,
    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL: process.env.CI ? 'http://localhost:4173' : 'http://localhost:5173',

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: 'on-first-retry',

    /* Run headless by default; set HEADED=true for visual debugging */
    headless: !process.env.HEADED,

    // slowMo only when running headed
    launchOptions: process.env.HEADED ? { slowMo: 500 } : {},
  },

  // Default to isolated mode (no Auth0). Set USE_AUTH0_E2E=true to use real Auth0 login.
  projects: process.env.USE_AUTH0_E2E?.toLowerCase() !== 'true'
    ? [
        // ── Isolated mode (TESTING=true): no Auth0 dependency ────────────
        // Reset test data before all tests
        { name: 'test-reset', testMatch: '**/setup/test-reset.setup.ts' },

        // Public tests — no auth needed
        { name: 'public', testMatch: '**/tests/public/**/*.spec.ts' },

        // Authenticated tests (admin context)
        {
          name: 'chromium',
          use: { ...devices['Desktop Chrome'] },
          dependencies: ['test-reset'],
          testMatch: '**/tests/authenticated/**/*.spec.ts',
        },

        // Member tests
        {
          name: 'member',
          use: { ...devices['Desktop Chrome'] },
          dependencies: ['test-reset'],
          testMatch: '**/tests/member/**/*.spec.ts',
        },

        // Multi-user tests
        {
          name: 'multi-user',
          use: { ...devices['Desktop Chrome'] },
          dependencies: ['test-reset'],
          testMatch: '**/tests/multi-user/**/*.spec.ts',
        },
      ]
    : [
        // ── Auth0 mode (default): real Auth0 login ───────────────────────
        // Auth setup — split so member failure doesn't block admin tests
        { name: 'auth-admin', testMatch: '**/setup/auth.setup.ts' },
        { name: 'auth-member', testMatch: '**/setup/auth-member.setup.ts' },

        // Public tests — no auth needed
        { name: 'public', testMatch: '**/tests/public/**/*.spec.ts' },

        // Authenticated tests (admin context) — only depends on admin auth
        {
          name: 'chromium',
          use: { ...devices['Desktop Chrome'], storageState: 'e2e/.auth/user.json' },
          dependencies: ['auth-admin'],
          testMatch: '**/tests/authenticated/**/*.spec.ts',
        },

        // Member tests — depends on member auth
        {
          name: 'member',
          use: { ...devices['Desktop Chrome'], storageState: 'e2e/.auth/member.json' },
          dependencies: ['auth-member'],
          testMatch: '**/tests/member/**/*.spec.ts',
        },

        // Multi-user tests — depends on both
        {
          name: 'multi-user',
          use: { ...devices['Desktop Chrome'], storageState: 'e2e/.auth/user.json' },
          dependencies: ['auth-admin', 'auth-member'],
          testMatch: '**/tests/multi-user/**/*.spec.ts',
        },
      ],

  /* Folder for test artifacts such as screenshots, videos, traces, etc. */
  // outputDir: 'test-results/',

  /* Run your local dev server before starting the tests */
  webServer: {
    /**
     * Use the dev server by default for faster feedback loop.
     * Use the preview server on CI for more realistic testing.
     * Playwright will re-use the local server if there is already a dev-server running.
     */
    command: process.env.CI ? 'pnpm run preview' : 'pnpm run dev',
    port: process.env.CI ? 4173 : 5173,
    reuseExistingServer: !process.env.CI,
  },
})
