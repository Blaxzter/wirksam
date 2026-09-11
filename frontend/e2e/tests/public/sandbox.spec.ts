import { expect, test } from '@playwright/test'

/**
 * The demo session, driven the way a visitor meets it: anonymous, from the
 * landing page, through the real `POST /auth/sandbox`.
 *
 * These belong in the `public` project rather than with the signed-in specs
 * because the demo does **not** use the `X-Test-User-Email` bypass — it mints a
 * real session against the real endpoint, which is precisely what is worth
 * covering. That also means every test here leaves rows in the database, so
 * each one exits its own demo; the TTL sweep is the backstop, not the plan.
 */

/** Start a demo and wait until the app has actually opened. */
async function startDemo(page: import('@playwright/test').Page, role: 'helper' | 'manager') {
  await page.goto('/')
  await page.getByTestId('btn-cta-demo').click()
  await expect(page.getByTestId('dialog-sandbox-start')).toBeVisible()
  await page.getByTestId(`btn-sandbox-role-${role}`).click()
  await page.getByTestId('btn-sandbox-start').click()
  await page.waitForURL(/\/app\//, { timeout: 30_000 })
}

/**
 * Get the guided tour out of the way, whichever half of it is on screen.
 *
 * A demo opens on the welcome dialog, which is modal, and the tour it offers
 * dims the page and swallows pointer events — so anything that clicks the app
 * itself has to answer the question first and then close whatever it started.
 * Both are best-effort: a case that has already dealt with one of them should
 * not fail here.
 */
async function dismissTour(page: import('@playwright/test').Page) {
  await page
    .getByTestId('btn-tour-decline')
    .click({ timeout: 10_000 })
    .catch(() => {})
  await expect(page.getByTestId('dialog-sandbox-welcome')).toBeHidden()

  await page
    .locator('.driver-popover-close-btn')
    .click({ timeout: 5000 })
    .catch(() => {})
  await expect(page.locator('.driver-popover')).toBeHidden()
}

/** Tear the demo down, so the suite does not rely on the TTL sweep to tidy up. */
async function exitDemo(page: import('@playwright/test').Page) {
  await dismissTour(page)
  await page.getByTestId('btn-sandbox-exit').click()
  await page.getByTestId('btn-dialog-confirm').click()
  await page.waitForURL(/\/$/, { timeout: 15_000 })
}

test.describe('demo session', () => {
  test('the landing page offers a demo to an anonymous visitor', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('btn-cta-demo')).toBeVisible()
    await expect(page.getByTestId('btn-cta-demo-footer')).toBeAttached()
  })

  test('opens the app directly, without ever showing the event picker', async ({ page }) => {
    // The point of preselecting the event server-side. Collect every main-frame
    // URL rather than asserting on the final one, because a picker that flashed
    // for 200ms and redirected would pass a `toHaveURL` check and still be the
    // bug this guards against.
    const visited: string[] = []
    page.on('framenavigated', (frame) => {
      if (frame === page.mainFrame()) visited.push(frame.url())
    })

    await startDemo(page, 'helper')

    expect(page.url()).toContain('/app/home')
    expect(visited.filter((url) => url.includes('select-event'))).toEqual([])

    await exitDemo(page)
  })

  test('shows a banner with a live countdown and a way out', async ({ page }) => {
    await startDemo(page, 'helper')

    await expect(page.getByTestId('sandbox-banner')).toBeVisible()
    await expect(page.getByTestId('btn-sandbox-exit')).toBeVisible()
    await expect(page.getByTestId('btn-sandbox-tour')).toBeVisible()

    // A deadline an hour out must not read as expired. This is the regression
    // test for the timestamp trap: the API sends naive UTC, and reading it as
    // local time puts a fresh deadline in the past everywhere east of London.
    const countdown = page.getByTestId('sandbox-countdown')
    await expect(countdown).toBeVisible()
    await expect(countdown).toHaveText(/\d+:\d{2}/)

    await exitDemo(page)
  })

  test('a helper sees the volunteer side and none of the management screens', async ({ page }) => {
    await startDemo(page, 'helper')

    // Membership role `member` is what hides these — the router's
    // requiresEventManager guard keys off it.
    await expect(page.getByTestId('sidebar-link-reporting')).toHaveCount(0)
    await expect(page.getByTestId('sidebar-link-my-events')).toHaveCount(0)

    await exitDemo(page)
  })

  test('an organiser sees the management screens', async ({ page }) => {
    await startDemo(page, 'manager')

    await expect(page.getByTestId('sidebar-link-reporting')).toBeVisible()

    await exitDemo(page)
  })

  test('the seeded event has work in it on every screen the tour visits', async ({ page }) => {
    // An empty state is the failure mode this feature cannot afford; the seed
    // exists to prevent it, so assert the data actually arrived.
    await startDemo(page, 'helper')

    // Navigated by clicking, not by `page.goto`. A hard load drops the access
    // token — it is held in memory by design — and the app rebuilds the session
    // from the refresh cookie, which is `SameSite=Lax`. In CI the page is served
    // from `localhost:4173` while the API is `http://backend:8787`, and those
    // are two different sites, so the browser withholds the cookie and the
    // bootstrap refresh 401s straight to the sign-in screen.
    //
    // That split is a property of the compose topology, not of the product:
    // production serves the app and the API from one domain and local dev from
    // one host, so a demo survives F5 in both. Do not "fix" a failure here by
    // loosening the cookie to `SameSite=None`; it would weaken every real
    // session to make a test-only topology work.
    await dismissTour(page)

    await page.getByTestId('sidebar-link-tasks').click()
    await expect(page.getByTestId('task-row').first()).toBeVisible()

    await page.getByTestId('sidebar-link-my-bookings').click()
    await expect(page.getByTestId('booking-card').first()).toBeVisible()

    // The inbox is the one screen the demo cannot fill for itself: the
    // notification service drops a sandbox recipient before it writes a row,
    // so nothing the visitor does during the tour ever reaches the bell. If
    // the seeder stops writing these, the screen is empty for the whole hour.
    await page.getByTestId('sidebar-link-notifications').click()
    await expect(page.getByTestId('notification-row').first()).toBeVisible()

    await exitDemo(page)
  })

  test('leaving the demo signs the visitor out and takes the app back', async ({ page }) => {
    await startDemo(page, 'helper')
    await exitDemo(page)

    await expect(page.getByTestId('sandbox-banner')).toBeHidden()

    // The session is genuinely gone, not merely navigated away from: the app
    // bounces to the sign-in screen, carrying the intended destination.
    await page.goto('/app/home')
    await expect(page).toHaveURL(/\/login/)
  })
})
