import { expect, test } from '@playwright/test'

test('root path renders preauth layout', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByTestId('main-content')).toBeVisible()
  await expect(page.getByTestId('btn-cta-primary')).toBeVisible()
})
