/**
 * E2E smoke tests for remaining pre-auth pages (privacy, terms, impressum).
 */

import { expect, test } from '@playwright/test'

test.describe('Privacy page', () => {
  test('loads and shows content', async ({ page }) => {
    await page.goto('/privacy')
    await expect(page).toHaveURL(/\/privacy/)
    await expect(page.getByTestId('main-content')).toBeVisible()
  })
})

test.describe('Terms page', () => {
  test('loads and shows content', async ({ page }) => {
    await page.goto('/terms')
    await expect(page).toHaveURL(/\/terms/)
    await expect(page.getByTestId('main-content')).toBeVisible()
  })
})

test.describe('Impressum page', () => {
  test('loads and shows content', async ({ page }) => {
    await page.goto('/impressum')
    await expect(page).toHaveURL(/\/impressum/)
    await expect(page.getByTestId('main-content')).toBeVisible()
  })
})
