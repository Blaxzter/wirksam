/**
 * E2E smoke tests for individual Settings sections.
 */

import { test, expect } from '../../fixtures.js'

test.describe('Settings – profile section', () => {
  test('can navigate to profile section', async ({ adminPage: page }) => {
    await page.goto('/app/settings/profile')
    await expect(page).toHaveURL(/\/app\/settings\/profile/)
  })

  test('shows profile section content', async ({ adminPage: page }) => {
    await page.goto('/app/settings/profile')
    await expect(page.getByTestId('section-profile')).toBeVisible()
  })
})

test.describe('Settings – security section', () => {
  test('can navigate to security section', async ({ adminPage: page }) => {
    test.skip(process.env.USE_AUTH0_E2E?.toLowerCase() !== 'true', 'Security section requires Auth0')
    await page.goto('/app/settings/security')
    await expect(page).toHaveURL(/\/app\/settings\/security/)
  })

  test('shows security section content', async ({ adminPage: page }) => {
    test.skip(process.env.USE_AUTH0_E2E?.toLowerCase() !== 'true', 'Security section requires Auth0')
    await page.goto('/app/settings/security')
    await expect(page.getByTestId('section-security')).toBeVisible()
  })
})

test.describe('Settings – data export section', () => {
  test('can navigate to data section', async ({ adminPage: page }) => {
    await page.goto('/app/settings/dataPrivacy')
    await expect(page).toHaveURL(/\/app\/settings\/dataPrivacy/)
  })

  test('shows data section content', async ({ adminPage: page }) => {
    await page.goto('/app/settings/dataPrivacy')
    await expect(page.getByTestId('section-data')).toBeVisible()
  })
})

test.describe('Settings – language section', () => {
  test('can navigate to language section', async ({ adminPage: page }) => {
    await page.goto('/app/settings/language')
    await expect(page).toHaveURL(/\/app\/settings\/language/)
  })

  test('shows language section content', async ({ adminPage: page }) => {
    await page.goto('/app/settings/language')
    await expect(page.getByTestId('section-language')).toBeVisible()
  })
})
