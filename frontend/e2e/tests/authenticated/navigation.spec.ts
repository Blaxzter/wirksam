/**
 * E2E tests for Navigation, Sidebar, Breadcrumbs, and 404 page.
 */

import { expect, test } from '@playwright/test'

// ── sidebar navigation ──────────────────────────────────────────────────────

test.describe('Sidebar – links', () => {
  test('shows Home link', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('link', { name: /^Home$/i }).first()).toBeVisible()
  })

  test('shows Event Groups link', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('link', { name: /event.?groups/i })).toBeVisible()
  })

  test('shows Events link', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('link', { name: /^Events$/i })).toBeVisible()
  })

  test('shows My Bookings link', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('link', { name: /my bookings/i })).toBeVisible()
  })

  test('shows User Management link for admin', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('link', { name: /user management/i })).toBeVisible()
  })

  test('shows Demo Data link for admin', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('link', { name: /demo data/i })).toBeVisible()
  })

  test('shows user profile button in sidebar', async ({ page }) => {
    await page.goto('/app/home')
    await expect(
      page.getByRole('button', { name: /frederic abraham/i }),
    ).toBeVisible()
  })
})

// ── sidebar navigation (clicking) ───────────────────────────────────────────

test.describe('Sidebar – navigation', () => {
  test('Home link navigates to dashboard', async ({ page }) => {
    await page.goto('/app/events')
    await page.getByRole('link', { name: /^Home$/i }).click()
    await expect(page).toHaveURL(/\/app\/home/)
  })

  test('Event Groups link navigates correctly', async ({ page }) => {
    await page.goto('/app/home')
    await page.getByRole('link', { name: /event.?groups/i }).click()
    await expect(page).toHaveURL(/\/app\/event-groups/)
  })

  test('Events link navigates correctly', async ({ page }) => {
    await page.goto('/app/home')
    await page.getByRole('link', { name: /^Events$/i }).click()
    await expect(page).toHaveURL(/\/app\/events/)
  })

  test('My Bookings link navigates correctly', async ({ page }) => {
    await page.goto('/app/home')
    await page.getByRole('link', { name: /my bookings/i }).click()
    await expect(page).toHaveURL(/\/app\/bookings/)
  })

  test('User Management link navigates correctly', async ({ page }) => {
    await page.goto('/app/home')
    await page.getByRole('link', { name: /user management/i }).click()
    await expect(page).toHaveURL(/\/app\/admin\/users/)
  })

  test('Demo Data link navigates correctly', async ({ page }) => {
    await page.goto('/app/home')
    await page.getByRole('link', { name: /demo data/i }).click()
    await expect(page).toHaveURL(/\/app\/admin\/demo-data/)
  })
})

// ── breadcrumbs ──────────────────────────────────────────────────────────────

test.describe('Breadcrumbs', () => {
  test('dashboard shows Home breadcrumb', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('navigation', { name: /breadcrumb/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /home/i }).first()).toBeVisible()
  })

  test('events page shows breadcrumbs', async ({ page }) => {
    await page.goto('/app/events')
    await expect(page.getByRole('navigation', { name: /breadcrumb/i })).toBeVisible()
  })
})

// ── sidebar toggle ───────────────────────────────────────────────────────────

test.describe('Sidebar – toggle', () => {
  test('Toggle Sidebar button is visible', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('button', { name: /toggle sidebar/i }).first()).toBeVisible()
  })
})

// ── 404 page ─────────────────────────────────────────────────────────────────

test.describe('404 – not found', () => {
  test('navigating to non-existent route shows 404', async ({ page }) => {
    await page.goto('/this-does-not-exist-at-all')
    // Should either redirect to 404 or show the not found page
    await expect(
      page.getByText(/not found|404|page.*exist/i).first(),
    ).toBeVisible({ timeout: 5000 })
  })

  test('navigating to /404 directly shows not found page', async ({ page }) => {
    await page.goto('/404')
    await expect(
      page.getByText(/not found|404|page.*exist/i).first(),
    ).toBeVisible({ timeout: 5000 })
  })
})

// ── member sidebar ───────────────────────────────────────────────────────────

test.describe('Member sidebar – no admin links', () => {
  const MEMBER_STATE = 'e2e/.auth/member.json'

  test('member does not see User Management link', async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: MEMBER_STATE })
    const member = await ctx.newPage()
    try {
      await member.goto('/app/home')
      await expect(member.getByRole('link', { name: /user management/i })).toBeHidden()
    } finally {
      await ctx.close()
    }
  })

  test('member does not see Demo Data link', async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: MEMBER_STATE })
    const member = await ctx.newPage()
    try {
      await member.goto('/app/home')
      await expect(member.getByRole('link', { name: /demo data/i })).toBeHidden()
    } finally {
      await ctx.close()
    }
  })
})
