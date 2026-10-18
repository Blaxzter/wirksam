/**
 * Accessibility scans of the public (pre-auth) pages.
 *
 * These use the plain `page` fixture — no auth bypass — so the scan sees what an
 * anonymous visitor sees. storageState is cleared explicitly so no other
 * project's session can leak in and change what renders.
 */
import { expect, test } from '@playwright/test'

import { expectNoA11yViolations } from '../../helpers/a11y.js'

test.use({ storageState: { cookies: [], origins: [] } })

test.describe('a11y – public pages', () => {
  test('landing page has no serious or critical violations', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'landing (/)' })
  })

  test('landing page volunteer journey has no serious or critical violations', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('page-heading')).toBeVisible()

    // The second journey tab renders a whole panel that the default scan never
    // sees, so it gets its own pass.
    await page.locator('#how-it-works').getByRole('tab').nth(1).click()
    await expectNoA11yViolations(page, { label: 'landing – volunteer journey (/)' })
  })

  test('privacy page has no serious or critical violations', async ({ page }) => {
    await page.goto('/privacy')
    // Legal pages have no page-heading testid, so anchor on the h1 itself.
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expectNoA11yViolations(page, { label: 'privacy (/privacy)' })
  })

  test('comparison page has no serious or critical violations', async ({ page }) => {
    await page.goto('/alternatives')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'comparison (/alternatives)' })
  })

  test('club festival page has no serious or critical violations', async ({ page }) => {
    await page.goto('/de/use-cases/club-festival')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'club festival (/de/use-cases/club-festival)' })
  })

  test('the screenshot viewer has no serious or critical violations', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('page-heading')).toBeVisible()

    // The viewer is a portalled dialog the default scan never reaches.
    const thumbnail = page.locator('#features button[aria-label]').first()
    await thumbnail.scrollIntoViewIfNeeded()
    await thumbnail.click()
    await expect(page.getByRole('dialog')).toBeVisible()

    await expectNoA11yViolations(page, { label: 'landing – screenshot viewer (/)' })
  })
})
