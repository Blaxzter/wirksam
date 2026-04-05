import { test, expect } from '../../fixtures.js'

test.describe('authenticated routes', () => {
  test('can open dashboard home', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page).toHaveURL(/\/app\/home/)
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('can open settings page', async ({ adminPage: page }) => {
    await page.goto('/app/settings')
    await expect(page).toHaveURL(/\/app\/settings/)
  })
})
