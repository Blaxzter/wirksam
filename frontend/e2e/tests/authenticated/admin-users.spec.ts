/**
 * E2E tests for Admin User Management page.
 */

import type { Locator, Page } from '@playwright/test'

import { test, expect } from '../../fixtures.js'
import { AUTH_TEST_PASSWORD, deleteAccount } from '../../helpers/auth.js'

const API = process.env.VITE_API_URL ?? 'http://localhost:8787/api/v1'

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
    await expect(page.getByTestId('stat-suspended')).toBeVisible()
  })

  test('hides the approval queue when signup is open', async ({ adminPage: page }) => {
    // The E2E stack runs REGISTRATION_MODE=open, so nobody can be waiting and
    // the pending/rejected cards would only ever read zero.
    await page.goto('/app/admin/users')
    await expect(page.getByTestId('stat-total')).toBeVisible()
    await expect(page.getByTestId('stat-pending')).toHaveCount(0)
    await expect(page.getByTestId('stat-rejected')).toHaveCount(0)
  })

  test('shows user table', async ({ adminPage: page }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByTestId('users-table')).toBeVisible()
  })

  test('current admin user appears in the list', async ({ adminPage: page, adminUser }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByTestId('users-table').getByText(new RegExp(adminUser.name, 'i'))).toBeVisible()
  })

  test('no longer offers an approval password', async ({ adminPage: page }) => {
    // Signup is open, so there is no approval to shortcut with a password.
    await page.goto('/app/admin/users')
    await expect(page.getByTestId('section-approval-password')).toHaveCount(0)
  })
})

test.describe('Admin Users – member RBAC', () => {
  test('member cannot access admin users page', async ({ memberPage: member }) => {
    await member.goto('/app/admin/users')
    // Should redirect away or show unauthorized
    await expect(member).not.toHaveURL(/\/app\/admin\/users/)
  })
})

/**
 * Deciding on a waiting registration from the admin screen.
 *
 * The account is put in the queue by registering it with an approval-mode
 * policy in `X-Test-Registration-Policy` (see `tests/auth/registration-modes.spec.ts`
 * for why it is a header and not a setting). The admin screen itself needs no
 * override: a pending account is pending whatever mode the server runs.
 */
test.describe('Admin Users – approval queue', () => {
  async function registerPending(email: string): Promise<void> {
    const res = await fetch(`${API}/auth/register`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Test-Registration-Policy': JSON.stringify({
          mode: 'approval',
          allowed_domains: [],
          invite_bypass: true,
        }),
      },
      body: JSON.stringify({ email, name: 'Queued Person', password: AUTH_TEST_PASSWORD }),
    })
    expect(res.status, await res.clone().text()).toBe(201)
  }

  async function queuedRow(page: Page, email: string): Promise<Locator> {
    await page.goto('/app/admin/users')
    await page.getByTestId('users-search').fill(email)
    const row = page.getByTestId('users-table').getByRole('row').filter({ hasText: email })
    await expect(row).toContainText('Pending')
    return row
  }

  function queueEmail(label: string, workerIndex: number): string {
    return `queue-${label}-${workerIndex}-${Date.now()}@test.example.com`
  }

  test('approving lets the account in', async ({ adminPage: page, adminUser }, testInfo) => {
    const email = queueEmail('approve', testInfo.workerIndex)
    await registerPending(email)
    try {
      const row = await queuedRow(page, email)
      await row.getByRole('button').click()
      await page.getByTestId('action-approve').click()
      await expect(row).toContainText('Active')
    } finally {
      await deleteAccount(adminUser.email, email).catch(() => {})
    }
  })

  test('rejecting asks for a reason and keeps the account', async ({
    adminPage: page,
    adminUser,
  }, testInfo) => {
    const email = queueEmail('reject', testInfo.workerIndex)
    await registerPending(email)
    try {
      const row = await queuedRow(page, email)
      await row.getByRole('button').click()
      await page.getByTestId('action-reject').click()

      const dialog = page.getByRole('dialog')
      await dialog.getByRole('textbox').fill('Not a member of the parish.')
      await dialog.getByRole('button', { name: 'Reject', exact: true }).click()

      await expect(dialog).toBeHidden()
      await expect(row).toContainText('Rejected')
    } finally {
      await deleteAccount(adminUser.email, email).catch(() => {})
    }
  })
})
