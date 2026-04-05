/**
 * E2E smoke tests for Changelog view.
 */

import { test, expect } from '../../fixtures.js'

test.describe('Changelog – authenticated', () => {
  test('can access changelog page via URL', async ({ adminPage: page }) => {
    await page.goto('/app/changelog')
    await expect(page).toHaveURL(/\/app\/changelog/)
  })

  test('shows page heading', async ({ adminPage: page }) => {
    await page.goto('/app/changelog')
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('shows version chips for navigation', async ({ adminPage: page }) => {
    await page.goto('/app/changelog')
    await expect(page.getByTestId('changelog-nav')).toBeVisible()
  })
})

test.describe('Changelog – public (pre-auth)', () => {
  test('can access public changelog page', async ({ page }) => {
    await page.goto('/changelog')
    await expect(page).toHaveURL(/\/changelog/)
  })

  test('public changelog shows heading', async ({ page }) => {
    await page.goto('/changelog')
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })
})
