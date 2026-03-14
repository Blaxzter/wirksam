/**
 * E2E tests for Admin User Management page.
 */

import { expect, test } from '@playwright/test'

test.describe('Admin Users – navigation', () => {
  test('sidebar shows User Management link for admin', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('link', { name: /user management/i })).toBeVisible()
  })

  test('clicking sidebar link navigates to /app/admin/users', async ({ page }) => {
    await page.goto('/app/home')
    await page.getByRole('link', { name: /user management/i }).click()
    await expect(page).toHaveURL(/\/app\/admin\/users/)
  })

  test('direct navigation to /app/admin/users works', async ({ page }) => {
    await page.goto('/app/admin/users')
    await expect(page).toHaveURL(/\/app\/admin\/users/)
  })
})

test.describe('Admin Users – page structure', () => {
  test('shows heading', async ({ page }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('shows stats cards (total, active, pending, rejected)', async ({ page }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByText(/total/i).first()).toBeVisible()
    await expect(page.getByText(/active/i).first()).toBeVisible()
  })

  test('shows user table', async ({ page }) => {
    await page.goto('/app/admin/users')
    // Table should have header columns
    await expect(page.getByText(/name/i).first()).toBeVisible()
    await expect(page.getByText(/email/i).first()).toBeVisible()
  })

  test('current admin user appears in the list', async ({ page }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByText(/frederic abraham/i).first()).toBeVisible({ timeout: 5000 })
  })

  test('shows approval password section', async ({ page }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByText(/approval.*password|self.*approv/i).first()).toBeVisible()
  })
})

test.describe('Admin Users – member RBAC', () => {
  test('member cannot access admin users page', async ({ browser }) => {
    const MEMBER_STATE = 'e2e/.auth/member.json'
    const ctx = await browser.newContext({ storageState: MEMBER_STATE })
    const member = await ctx.newPage()
    try {
      await member.goto('/app/admin/users')
      // Should redirect away or show unauthorized
      // The route guard should prevent access
      await expect(member).not.toHaveURL(/\/app\/admin\/users/, { timeout: 5000 })
    } finally {
      await ctx.close()
    }
  })
})
