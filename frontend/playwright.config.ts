import { defineConfig, devices } from '@playwright/test'
import dotenv from 'dotenv'
/**
 * Read environment variables from file.
 * https://github.com/motdotla/dotenv
 */
import { dirname, resolve } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

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
    baseURL: process.env.CI ? 'http://localhost:4173' : 'http://localhost:5555',

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: 'on-first-retry',

    /* Run headless by default; set HEADED=true for visual debugging */
    headless: !process.env.HEADED,

    // slowMo only when running headed
    launchOptions: process.env.HEADED ? { slowMo: 500 } : {},
  },

  /**
   * One mode, always.
   *
   * There used to be a second project list behind `USE_AUTH0_E2E=true` that
   * drove the hosted Auth0 login form and wrote a `storageState` file. It went
   * with Auth0 itself. Identity now comes from the `X-Test-User-Email` header
   * the fixtures inject (see `e2e/fixtures.ts`), against a backend running with
   * `TESTING=true` — no storageState, no shared session between projects.
   */
  projects: [
    // Reset test data before all tests
    { name: 'test-reset', testMatch: '**/setup/test-reset.setup.ts' },

    // Public tests — no auth needed
    { name: 'public', testMatch: '**/tests/public/**/*.spec.ts' },

    // The sign-in, registration and password-recovery screens. These are the
    // one corner of the suite that does *not* use the header bypass: they drive
    // the real forms against the real endpoints, as an anonymous visitor, so
    // the flows a first-time user meets are actually exercised somewhere.
    {
      name: 'auth',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['test-reset'],
      testMatch: '**/tests/auth/**/*.spec.ts',
    },

    // A shared list's public page and a guest's manage page, as the anonymous
    // visitor who opens a link from a group chat: no bypass cookie, no seeded
    // session. Not part of `public`, because the lists, events and guests these
    // specs seed belong to worker users that `test-reset` has to clear first.
    {
      name: 'guest',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['test-reset'],
      testMatch: '**/tests/guest/**/*.spec.ts',
    },

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

    // The bottom-drawer half of every dialog.
    //
    // Every project above runs at a desktop viewport, so all of them exercise
    // `ResponsiveDialog`'s `Dialog` branch and none of them would notice the
    // drawer breaking. This is the only project that renders the other half.
    {
      name: 'mobile',
      use: { ...devices['Pixel 7'] },
      dependencies: ['test-reset'],
      testMatch: '**/tests/mobile/**/*.spec.ts',
    },

    // Accessibility tests (axe-core scans + keyboard/focus behaviour).
    // Own project so it can be run and sharded independently:
    //   pnpm exec playwright test --project=a11y
    {
      name: 'a11y',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['test-reset'],
      testMatch: '**/tests/a11y/**/*.spec.ts',
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
    port: process.env.CI ? 4173 : 5555,
    reuseExistingServer: !process.env.CI,
  },
})
