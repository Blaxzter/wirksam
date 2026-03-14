import { expect, test } from '@playwright/test'

test.describe('landing page', () => {
  test('renders main hero and auth actions', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: /Welcome to DutyHub/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /Go to Dashboard|Get Started/i })).toBeVisible()
  })
})
