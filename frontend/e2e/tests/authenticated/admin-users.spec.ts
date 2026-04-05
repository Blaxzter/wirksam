/**
 * E2E tests for Admin User Management page.
 */

import { test, expect } from '../../fixtures.js'

test.describe('Admin Users – navigation', () => {
  test('sidebar shows User Management link for admin', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('sidebar-link-admin-users')).toBeVisible()
  })

  test('clicking sidebar link navigates to /app/admin/users', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('sidebar-link-admin-users').click()
    await expect(page).toHaveURL(/\/app\/admin\/users/)
  })

  test('direct navigation to /app/admin/users works', async ({ adminPage: page }) => {
    await page.goto('/app/admin/users')
    await expect(page).toHaveURL(/\/app\/admin\/users/)
  })
})

test.describe('Admin Users – page structure', () => {
  test('shows heading', async ({ adminPage: page }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('shows stats section', async ({ adminPage: page }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByTestId('section-stats')).toBeVisible()
  })

  test('shows individual stat cards', async ({ adminPage: page }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByTestId('stat-total')).toBeVisible()
    await expect(page.getByTestId('stat-active')).toBeVisible()
    await expect(page.getByTestId('stat-pending')).toBeVisible()
    await expect(page.getByTestId('stat-rejected')).toBeVisible()
  })

  test('shows user table', async ({ adminPage: page }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByTestId('users-table')).toBeVisible()
  })

  test('current admin user appears in the list', async ({ adminPage: page, adminUser }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByText(new RegExp(adminUser.name, 'i'))).toBeVisible()
  })

  test('shows approval password section', async ({ adminPage: page }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByTestId('section-approval-password')).toBeVisible()
  })
})

test.describe('Admin Users – member RBAC', () => {
  test('member cannot access admin users page', async ({ memberPage: member }) => {
    await member.goto('/app/admin/users')
    // Should redirect away or show unauthorized
    await expect(member).not.toHaveURL(/\/app\/admin\/users/)
  })
})
