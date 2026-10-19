/**
 * The content pages written for search: the comparison with other tools and
 * the use-case pages (`lib/content-pages.ts`), in both languages.
 */
import { type Page, expect, test } from '@playwright/test'

test.describe('comparison page', () => {
  test('shows the comparison table with its date and sources', async ({ page }) => {
    await page.goto('/alternatives')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('WirkSam and the alternatives')
    await expect(page).toHaveTitle(/compared/)

    const table = page.getByTestId('comparison-table')
    await expect(table).toBeVisible()
    // WirkSam and the five tools it is compared with.
    await expect(table.locator('tbody tr')).toHaveCount(6)
    await expect(page.getByTestId('comparison-as-of')).toContainText('October 2026')
    await expect(page.locator('#tool-engelsystem a[href^="https://"]').first()).toBeVisible()
  })

  test('is served in German under /de', async ({ page }) => {
    await page.goto('/de/alternatives')
    await expect(page.locator('html')).toHaveAttribute('lang', 'de')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('WirkSam und die Alternativen')
    await expect(page.getByTestId('comparison-as-of')).toContainText(
      'Stand: Oktober 2026, Angaben ohne Gewähr',
    )
  })

  test('turns into one card per tool on a phone, without sideways scrolling', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 })
    await page.goto('/alternatives')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

    await expect(page.getByTestId('comparison-table')).toBeHidden()
    await expect(page.getByTestId('comparison-cards').locator(':scope > li')).toHaveCount(6)

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })

  test('links on to the club festival page', async ({ page }) => {
    await page.goto('/alternatives')
    await page.getByTestId('related-clubFestival').click()
    await expect(page).toHaveURL(/\/use-cases\/club-festival$/)
  })
})

test.describe('club festival page', () => {
  test('answers first, then walks through the steps and the FAQ', async ({ page }) => {
    await page.goto('/use-cases/club-festival')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('club festival')
    await expect(page).toHaveTitle(/club festival/)

    await expect(page.locator('#how-it-works ol > li')).toHaveCount(6)

    const item = page.locator('#app #faq-account')
    await item.locator('summary').scrollIntoViewIfNeeded()
    await expect(item.locator('p')).toBeHidden()
    await item.locator('summary').click()
    await expect(item.locator('p')).toBeVisible()
  })

  test('stays in German when following a related link', async ({ page }) => {
    await page.goto('/de/use-cases/club-festival')
    await expect(page.locator('html')).toHaveAttribute('lang', 'de')
    await expect(page).toHaveTitle(/Vereinsfest/)
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Vereinsfest')

    await page.getByTestId('related-alternatives').click()
    await expect(page).toHaveURL(/\/de\/alternatives$/)
  })

  test('offers the demo next to the sign-up', async ({ page }) => {
    await page.goto('/use-cases/club-festival')
    await expect(page.getByTestId('content-cta-primary')).toBeVisible()
    await page.getByTestId('content-cta-demo').click()
    await expect(page.getByRole('dialog')).toBeVisible()
  })
})

test.describe('links into the content pages', () => {
  test('the footer of every public page links to both', async ({ page }) => {
    await page.goto('/terms')
    const footer = page.getByRole('contentinfo')
    await footer.getByRole('link', { name: 'Compare alternatives' }).click()
    await expect(page).toHaveURL(/\/alternatives$/)
    await footer.getByRole('link', { name: 'Club festivals' }).click()
    await expect(page).toHaveURL(/\/use-cases\/club-festival$/)
  })
})

test.describe('content pages under runtime switches', () => {
  function serveConfig(page: Page, config: string) {
    return page.route('**/config.js', (route) =>
      route.fulfill({
        contentType: 'application/javascript',
        body: `window.__APP_CONFIG__ = ${config}`,
      }),
    )
  }

  test('without the demo there is no demo button', async ({ page }) => {
    await serveConfig(page, "{ SANDBOX_ENABLED: 'false' }")
    await page.goto('/alternatives')
    await expect(page.getByTestId('content-cta-primary')).toBeVisible()
    await expect(page.getByTestId('content-cta-demo')).toHaveCount(0)
  })

  test('without the landing page they lead to sign-in and leave the footer', async ({ page }) => {
    await serveConfig(page, "{ LANDING_ENABLED: 'false' }")
    await page.goto('/use-cases/club-festival')
    await expect(page).toHaveURL(/\/login$/)

    await page.goto('/terms')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Compare alternatives' })).toHaveCount(0)
  })
})
