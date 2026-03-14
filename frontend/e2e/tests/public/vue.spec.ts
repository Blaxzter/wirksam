import { expect, test } from '@playwright/test'

test('root path renders preauth layout', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'About' })).toBeVisible()
  // User may already be authenticated — check for either Sign In or Go to Dashboard
  await expect(
    page.getByRole('button', { name: /Sign In|Go to Dashboard/i }).first(),
  ).toBeVisible()
})
