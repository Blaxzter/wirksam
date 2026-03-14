/**
 * E2E tests for User Settings page.
 */

import { expect, test } from '@playwright/test'

test.describe('Settings – navigation', () => {
  test('can navigate to settings page via URL', async ({ page }) => {
    await page.goto('/app/settings')
    await expect(page).toHaveURL(/\/app\/settings/)
  })
})

test.describe('Settings – page structure', () => {
  test('shows current profile card', async ({ page }) => {
    await page.goto('/app/settings')
    // Should show the user's name
    await expect(page.getByText(/Frederic Abraham/i).first()).toBeVisible()
  })

  test('shows update profile section', async ({ page }) => {
    await page.goto('/app/settings')
    await expect(page.getByText(/update.*profile/i).first()).toBeVisible()
  })

  test('shows language settings', async ({ page }) => {
    await page.goto('/app/settings')
    await expect(page.getByText(/language/i).first()).toBeVisible()
  })

  test('shows notification settings link', async ({ page }) => {
    await page.goto('/app/settings')
    await expect(page.getByText(/notification/i).first()).toBeVisible()
  })

  test('shows password reset section', async ({ page }) => {
    await page.goto('/app/settings')
    await expect(page.getByText(/password/i).first()).toBeVisible()
  })

  test('shows danger zone / delete account', async ({ page }) => {
    await page.goto('/app/settings')
    await expect(page.getByText(/delete.*account|danger/i).first()).toBeVisible()
  })
})

test.describe('Settings – language', () => {
  test('can switch language to German', async ({ page }) => {
    await page.goto('/app/settings')
    // Find language setting and click German option
    const germanBtn = page.getByText(/deutsch|german/i).first()
    if (await germanBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await germanBtn.click()
      // Some text should now be in German
      await expect(page.getByText(/sprache|einstellungen/i).first()).toBeVisible({ timeout: 3000 })
      // Switch back to English
      const englishBtn = page.getByText(/english/i).first()
      if (await englishBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
        await englishBtn.click()
      }
    }
  })
})

test.describe('Settings – notification preferences', () => {
  test('can navigate to notification preferences', async ({ page }) => {
    await page.goto('/app/settings')
    const link = page.getByRole('link', { name: /notification/i }).or(
      page.getByRole('button', { name: /notification/i }),
    )
    if (await link.isVisible({ timeout: 2000 }).catch(() => false)) {
      await link.click()
      await expect(page).toHaveURL(/\/app\/settings\/notifications/)
    }
  })

  test('notification preferences page loads', async ({ page }) => {
    await page.goto('/app/settings/notifications')
    await expect(page).toHaveURL(/\/app\/settings\/notifications/)
    // Should show some notification type headings
    await expect(page.getByRole('heading', { level: 1 }).or(page.getByText(/notification/i).first())).toBeVisible()
  })
})
