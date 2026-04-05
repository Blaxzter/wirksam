/**
 * E2E tests for Notification feed and bell.
 */

import { test, expect } from '../../fixtures.js'

test.describe('Notifications – bell icon', () => {
  test('notification bell is visible in the header', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('notification-bell')).toBeVisible()
  })
})

test.describe('Notifications – preferences page', () => {
  test('notification preferences page loads', async ({ adminPage: page }) => {
    await page.goto('/app/settings/notification-preferences')
    await expect(page).toHaveURL(/notification-preferences/)
  })

  test('shows page heading', async ({ adminPage: page }) => {
    await page.goto('/app/settings/notification-preferences')
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('shows email channel section', async ({ adminPage: page }) => {
    await page.goto('/app/settings/notification-preferences')
    await expect(page.getByTestId('channel-email')).toBeVisible()
  })

  test('shows push channel section', async ({ adminPage: page }) => {
    await page.goto('/app/settings/notification-preferences')
    await expect(page.getByTestId('channel-push')).toBeVisible()
  })

  test('shows telegram channel section when configured', async ({ adminPage: page }) => {
    await page.goto('/app/settings/notification-preferences')
    // Telegram section only renders when the backend has a bot token configured;
    // wait briefly then skip if the element never appears (e.g. CI with .env.example)
    const telegram = page.getByTestId('channel-telegram')
    try {
      await telegram.waitFor({ timeout: 3_000 })
    } catch {
      test.skip(true, 'Telegram bot not configured')
    }
    await expect(telegram).toBeVisible()
  })

  test('shows per-type notification sections', async ({ adminPage: page }) => {
    await page.goto('/app/settings/notification-preferences')
    await expect(page.getByTestId('section-per-type')).toBeVisible()
  })

  test('shows default reminders section', async ({ adminPage: page }) => {
    await page.goto('/app/settings/notification-preferences')
    await expect(page.getByTestId('section-reminders')).toBeVisible()
  })

  test('can toggle a global channel switch', async ({ adminPage: page }) => {
    await page.goto('/app/settings/notification-preferences')
    // Find a switch element and click it
    const switches = page.locator('button[role="switch"]')
    const count = await switches.count()
    if (count > 0) {
      const firstSwitch = switches.first()
      const wasChecked = await firstSwitch.getAttribute('data-state')
      await firstSwitch.click()
      // State should have changed
      await page.waitForTimeout(500)
      const nowChecked = firstSwitch
      await expect(nowChecked).not.toHaveAttribute('data-state', wasChecked)
      // Toggle back to restore original state
      await firstSwitch.click()
    }
  })
})
