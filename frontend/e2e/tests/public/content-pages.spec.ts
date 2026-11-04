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

test.describe('feature pages and guides', () => {
  test('the overview groups the feature pages and leads to one', async ({ page }) => {
    await page.goto('/features')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('What WirkSam can do')
    await expect(page).toHaveTitle(/All features/)
    await expect(page.locator('[data-testid^="docs-group-"]')).toHaveCount(5)
    await expect(page.locator('[data-testid^="doc-card-"]')).toHaveCount(10)

    await page.getByTestId('doc-card-featureVouchers').click()
    await expect(page).toHaveURL(/\/features\/vouchers$/)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Vouchers instead of paper')
  })

  test('a feature page explains in sections, with the FAQ and links to read on', async ({
    page,
  }) => {
    await page.goto('/features/vouchers')
    await expect(page).toHaveTitle(/vouchers/i)
    await expect(page.getByTestId('content-cta-primary')).toBeVisible()
    await expect(page.locator('[data-testid="doc-body"] h2').first()).toBeVisible()

    const item = page.locator('#faq details').first()
    await item.locator('summary').scrollIntoViewIfNeeded()
    await expect(item.locator('p')).toBeHidden()
    await item.locator('summary').click()
    await expect(item.locator('p')).toBeVisible()

    await page.getByTestId('doc-related-guideVouchers').click()
    await expect(page).toHaveURL(/\/guides\/vouchers$/)
  })

  test('a guide numbers its steps and gets straight to them', async ({ page }) => {
    await page.goto('/guides/vouchers')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Set up vouchers')
    await expect(page.getByTestId('doc-body').locator('ol').first().locator('> li')).toHaveCount(5)
    await expect(page.getByTestId('content-cta-primary')).toBeHidden()

    await page.getByTestId('doc-hub-link').click()
    await expect(page).toHaveURL(/\/guides$/)
    await expect(page.locator('[data-testid^="doc-card-"]')).toHaveCount(8)
  })

  test('a link in the text stays in the app and in German', async ({ page }) => {
    await page.goto('/de/features/vouchers')
    await expect(page.locator('html')).toHaveAttribute('lang', 'de')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Marken statt Papier')
    await page.evaluate(() => ((window as unknown as { sameApp: boolean }).sameApp = true))

    await page.getByTestId('doc-body').getByRole('link', { name: 'Team', exact: true }).click()
    await expect(page).toHaveURL(/\/de\/features\/teams$/)
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Team')
    await expect(page.locator('html')).toHaveAttribute('lang', 'de')
    // Still the same document: the link was followed by the router, not a reload.
    expect(await page.evaluate(() => (window as unknown as { sameApp?: boolean }).sameApp)).toBe(
      true,
    )
  })

  test('a screenshot opens large, and a phone capture keeps its shape', async ({ page }) => {
    await page.goto('/features/vouchers')
    const phone = page.getByTestId('doc-body').locator('img[src*="vouchers-my"]')
    await phone.scrollIntoViewIfNeeded()
    await expect(phone).toHaveAttribute('width', '780')
    await phone.click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByRole('dialog').locator('img')).toHaveAttribute('src', /vouchers-my/)
  })

  test('fits a phone without sideways scrolling', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 })
    for (const path of ['/features', '/features/vouchers', '/guides/vouchers']) {
      await page.goto(path)
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
      expect(overflow, path).toBeLessThanOrEqual(0)
    }
  })

  test('the landing page and the header lead there', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('landing-all-features').click()
    await expect(page).toHaveURL(/\/features$/)
    await page.getByTestId('nav-guides').click()
    await expect(page).toHaveURL(/\/guides$/)
  })
})

test.describe('links into the content pages', () => {
  test('the footer of every public page links to them', async ({ page }) => {
    await page.goto('/terms')
    const footer = page.getByRole('contentinfo')
    await footer.getByRole('link', { name: 'Features' }).click()
    await expect(page).toHaveURL(/\/features$/)
    await footer.getByRole('link', { name: 'Guides' }).click()
    await expect(page).toHaveURL(/\/guides$/)
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
