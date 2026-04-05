import { expect, test } from '@playwright/test'

test.describe('public pages', () => {
  test('about page is accessible', async ({ page }) => {
    await page.goto('/about')
    await expect(page).toHaveURL(/\/about/)
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('navigation works between landing and about', async ({ page }) => {
    await page.goto('/about')
    await expect(page).toHaveURL(/\/about/)

    await page.getByTestId('btn-back').click()
    await expect(page).toHaveURL('/')
  })
})
