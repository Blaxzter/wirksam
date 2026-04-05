/**
 * E2E tests for the How It Works public page.
 */

import { expect, test } from '@playwright/test'

test.describe('How It Works page', () => {
  test('is accessible via direct URL', async ({ page }) => {
    await page.goto('/how-it-works')
    await expect(page).toHaveURL(/\/how-it-works/)
  })

  test('shows page content', async ({ page }) => {
    await page.goto('/how-it-works')
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })
})
