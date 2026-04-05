/**
 * E2E tests for Navigation, Sidebar, Breadcrumbs, and 404 page.
 */

import { test, expect } from '../../fixtures.js'

// ── sidebar navigation ──────────────────────────────────────────────────────

test.describe('Sidebar – links', () => {
  test('shows Home link', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('sidebar-link-home')).toBeVisible()
  })

  test('shows Event Groups link', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('sidebar-link-event-groups')).toBeVisible()
  })

  test('shows Events link', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('sidebar-link-events')).toBeVisible()
  })

  test('shows My Bookings link', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('sidebar-link-my-bookings')).toBeVisible()
  })

  test('shows User Management link for admin', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('sidebar-link-admin-users')).toBeVisible()
  })

  test('shows Demo Data link for admin', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('sidebar-link-admin-demo-data')).toBeVisible()
  })

  test('shows user profile button in sidebar', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('nav-user-menu')).toBeVisible()
  })
})

// ── sidebar navigation (clicking) ───────────────────────────────────────────

test.describe('Sidebar – navigation', () => {
  test('Home link navigates to dashboard', async ({ adminPage: page }) => {
    await page.goto('/app/events')
    await page.getByTestId('sidebar-link-home').click()
    await expect(page).toHaveURL(/\/app\/home/)
  })

  test('Event Groups link navigates correctly', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('sidebar-link-event-groups').click()
    await expect(page).toHaveURL(/\/app\/event-groups/)
  })

  test('Events link navigates correctly', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('sidebar-link-events').click()
    await expect(page).toHaveURL(/\/app\/events/)
  })

  test('My Bookings link navigates correctly', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('sidebar-link-my-bookings').click()
    await expect(page).toHaveURL(/\/app\/bookings/)
  })

  test('User Management link navigates correctly', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('sidebar-link-admin-users').click()
    await expect(page).toHaveURL(/\/app\/admin\/users/)
  })

  test('Demo Data link navigates correctly', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('sidebar-link-admin-demo-data').click()
    await expect(page).toHaveURL(/\/app\/admin\/demo-data/)
  })
})

// ── breadcrumbs ──────────────────────────────────────────────────────────────

test.describe('Breadcrumbs', () => {
  test('dashboard shows breadcrumb navigation', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('navigation', { name: /breadcrumb/i })).toBeVisible()
  })

  test('events page shows breadcrumbs', async ({ adminPage: page }) => {
    await page.goto('/app/events')
    await expect(page.getByRole('navigation', { name: /breadcrumb/i })).toBeVisible()
  })
})

// ── sidebar toggle ───────────────────────────────────────────────────────────

test.describe('Sidebar – toggle', () => {
  test('Toggle Sidebar button is visible', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    // SidebarTrigger in the header (data-sidebar="trigger")
    await expect(page.locator('[data-sidebar="trigger"]')).toBeVisible()
  })
})

// ── 404 page ─────────────────────────────────────────────────────────────────

test.describe('404 – not found', () => {
  test('navigating to non-existent route shows 404', async ({ adminPage: page }) => {
    await page.goto('/this-does-not-exist-at-all')
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('navigating to /404 directly shows not found page', async ({ adminPage: page }) => {
    await page.goto('/404')
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('404 page has go home button', async ({ adminPage: page }) => {
    await page.goto('/404')
    await expect(page.getByTestId('btn-go-home')).toBeVisible()
  })
})

// ── member sidebar ───────────────────────────────────────────────────────────

test.describe('Member sidebar – no admin links', () => {
  test('member does not see User Management link', async ({ memberPage: member }) => {
    await member.goto('/app/home')
    await expect(member.getByTestId('sidebar-link-admin-users')).toBeHidden()
  })

  test('member does not see Demo Data link', async ({ memberPage: member }) => {
    await member.goto('/app/home')
    await expect(member.getByTestId('sidebar-link-admin-demo-data')).toBeHidden()
  })
})
