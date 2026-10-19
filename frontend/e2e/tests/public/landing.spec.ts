import { expect, test } from '@playwright/test'

test.describe('landing page', () => {
  test('renders main hero and auth actions', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    // `btn-cta-primary` is on both branches of the hero — "get started" for an
    // anonymous visitor, "go to dashboard" for a signed-in one — so it is
    // present either way and the assertion needs no escape hatch.
    await expect(page.getByTestId('btn-cta-primary')).toBeVisible()
  })

  test('every section the in-page nav links to actually exists', async ({ page }) => {
    await page.goto('/')
    // Anchor on the hero first: under parallel load the section assertions can
    // otherwise start before the app has hydrated, and fail on an empty body.
    await expect(page.getByTestId('page-heading')).toBeVisible()

    for (const id of ['audience', 'how-it-works', 'features', 'about', 'faq', 'get-started']) {
      await expect(page.locator(`#${id}`)).toBeVisible()
    }
  })

  test('the old /about path redirects into the landing page', async ({ page }) => {
    await page.goto('/about')
    await expect(page).toHaveURL(/\/#about$/)
    await expect(page.locator('#about')).toBeVisible()
  })

  test('a screenshot opens in the viewer and pages through the gallery', async ({ page }) => {
    await page.goto('/')

    const frames = page.locator('#app #features button[aria-label]')
    await frames.first().scrollIntoViewIfNeeded()
    await frames.first().click()

    const viewer = page.getByRole('dialog')
    await expect(viewer).toBeVisible()
    await expect(viewer.locator('img')).toHaveAttribute('src', /shift-schedule-(light|dark)\.png$/)

    // Arrow keys walk the gallery.
    await page.keyboard.press('ArrowRight')
    await expect(viewer.locator('img')).toHaveAttribute('src', /tasks-(light|dark)\.png$/)

    // Escape closes it and hands focus back to the frame that opened it.
    await page.keyboard.press('Escape')
    await expect(viewer).toBeHidden()
    await expect(frames.first()).toBeFocused()
  })

  test('a FAQ answer opens from its question', async ({ page }) => {
    await page.goto('/')
    // The prerendered copy keeps its ids until the app replaces it, so an id
    // locator can land on that copy just before it is removed. Test ids are
    // stripped from it: once the heading is visible, the live page is up.
    await expect(page.getByTestId('page-heading')).toBeVisible()
    const item = page.locator('#app #faq-cost')
    await item.locator('summary').scrollIntoViewIfNeeded()
    await expect(item.locator('p')).toBeHidden()
    await item.locator('summary').click()
    await expect(item.locator('p')).toBeVisible()
  })
})

test.describe('public pages per language', () => {
  test('/de serves the landing page in German', async ({ page }) => {
    await page.goto('/de')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('lang', 'de')
    await expect(page).toHaveTitle(/Schichtplanung/)
  })

  test('switching language on a public page moves to its other URL', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('locale', 'en'))
    await page.goto('/terms')
    await expect(page.locator('html')).toHaveAttribute('lang', 'en')

    await page.getByRole('button', { name: 'Switch language' }).click()
    await page.getByRole('menuitem', { name: /Deutsch/ }).click()
    await expect(page).toHaveURL(/\/de\/terms$/)
    await expect(page.locator('html')).toHaveAttribute('lang', 'de')

    await page.getByRole('button', { name: 'Sprache wechseln' }).click()
    await page.getByRole('menuitem', { name: /English/ }).click()
    await expect(page).toHaveURL(/\/terms$/)
    await expect(page).not.toHaveURL(/\/de\//)
    await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  })
})

test.describe('a deployment without the landing page', () => {
  // LANDING_ENABLED reaches the browser through config.js, so serving a
  // different one is the whole switch from the app's side.
  test.beforeEach(async ({ page }) => {
    await page.route('**/config.js', (route) =>
      route.fulfill({
        contentType: 'application/javascript',
        body: "window.__APP_CONFIG__ = { LANDING_ENABLED: 'false' }",
      }),
    )
  })

  test('/ leads to the sign-in screen', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/login$/)
  })

  test('the legal pages stay, without links into the missing landing page', async ({ page }) => {
    await page.goto('/terms')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Features' })).toHaveCount(0)
  })
})
