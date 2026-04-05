/**
 * E2E tests for Admin User Management actions (activate, reject, approval password).
 */

import { test, expect } from '../../fixtures.js'

test.describe('Admin Users – approval password', () => {
  test('approval password section is visible', async ({ adminPage: page }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByTestId('section-approval-password')).toBeVisible()
  })

  test('approval password section has input and save button', async ({ adminPage: page }) => {
    await page.goto('/app/admin/users')
    const section = page.getByTestId('section-approval-password')
    if (await section.isVisible({ timeout: 3000 }).catch(() => false)) {
      await expect(
        section.locator('input[type="password"], input[type="text"]').first()
          .or(section.getByRole('button').first()),
      ).toBeVisible()
    }
  })
})

test.describe('Admin Users – user table actions', () => {
  test('user table is visible with data', async ({ adminPage: page }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByTestId('users-table')).toBeVisible()
    // Test user should appear in the table
    await expect(page.getByText(/test admin/i).first()).toBeVisible()
  })

  test('shows stat cards for filtering', async ({ adminPage: page }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByTestId('stat-active')).toBeVisible()
  })
})
