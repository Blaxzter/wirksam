/**
 * E2E tests for Calendar Feed settings (within User Settings).
 */

import { test, expect } from '../../fixtures.js'

test.describe('Calendar Feed – settings section', () => {
  test('settings page shows calendar feed section', async ({ adminPage: page }) => {
    await page.goto('/app/settings/calendar')
    await expect(page.getByTestId('section-calendar')).toBeVisible()
  })

  test('can navigate to calendar section in settings', async ({ adminPage: page }) => {
    await page.goto('/app/settings/calendar')
    await expect(page).toHaveURL(/\/app\/settings\/calendar/)
    await expect(page.getByTestId('section-calendar')).toBeVisible()
  })

  test('shows enable/disable feed toggle or button', async ({ adminPage: page }) => {
    await page.goto('/app/settings/calendar')
    const section = page.getByTestId('section-calendar')
    // Should show an enable button or a feed URL if already enabled
    await expect(
      section
        .getByRole('button', { name: /enable|disable|generate/i })
        .or(section.getByText(/feed.*url|\.ics/i).first())
        .or(section.locator('button[role="switch"]').first()),
    ).toBeVisible()
  })
})
