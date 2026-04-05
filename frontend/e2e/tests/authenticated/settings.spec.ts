/**
 * E2E tests for User Settings page.
 */

import { test, expect } from '../../fixtures.js'

test.describe('Settings – navigation', () => {
  test('can navigate to settings page via URL', async ({ adminPage: page }) => {
    await page.goto('/app/settings')
    await expect(page).toHaveURL(/\/app\/settings/)
  })
})

test.describe('Settings – page structure', () => {
  test('shows page heading', async ({ adminPage: page }) => {
    await page.goto('/app/settings')
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('shows profile section', async ({ adminPage: page }) => {
    await page.goto('/app/settings/profile')
    await expect(page.getByTestId('section-profile')).toBeVisible()
  })

  test('shows language section', async ({ adminPage: page }) => {
    await page.goto('/app/settings/language')
    await expect(page.getByTestId('section-language')).toBeVisible()
  })

  test('shows notifications section', async ({ adminPage: page }) => {
    await page.goto('/app/settings/notifications')
    await expect(page.getByTestId('section-notifications')).toBeVisible()
  })

  test('shows security section', async ({ adminPage: page }) => {
    // Security section is auth0Only — skip in isolated testing mode
    test.skip(process.env.USE_AUTH0_E2E?.toLowerCase() !== 'true', 'Security section requires Auth0')
    await page.goto('/app/settings/security')
    await expect(page.getByTestId('section-security')).toBeVisible()
  })

  test('shows data section', async ({ adminPage: page }) => {
    await page.goto('/app/settings/dataPrivacy')
    await expect(page.getByTestId('section-data')).toBeVisible()
  })
})

test.describe('Settings – language', () => {
  test('can switch language to German', async ({ adminPage: page }) => {
    await page.goto('/app/settings/language')
    const germanBtn = page.getByText(/deutsch|german/i).first()
    if (await germanBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await germanBtn.click()
      await expect(page.getByText(/sprache|einstellungen/i).first()).toBeVisible()
      const englishBtn = page.getByText(/english/i).first()
      if (await englishBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
        await englishBtn.click()
      }
    }
  })
})

test.describe('Settings – notification preferences', () => {
  test('can navigate to notification preferences', async ({ adminPage: page }) => {
    await page.goto('/app/settings/notifications')
    await expect(page.getByTestId('section-notifications')).toBeVisible()
  })

  test('notification preferences page loads', async ({ adminPage: page }) => {
    await page.goto('/app/settings/notification-preferences')
    await expect(page).toHaveURL(/notification-preferences/)
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })
})
