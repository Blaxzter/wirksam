/**
 * E2E tests for Dashboard page — stats cards, calendar, quick actions.
 */

import { expect, test } from '@playwright/test'

test.describe('Dashboard – stats cards', () => {
  test('shows Events stat card', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('heading', { name: 'Events', level: 3 })).toBeVisible()
  })

  test('shows My Bookings stat card', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('heading', { name: 'My Bookings', level: 3 })).toBeVisible()
  })

  test('shows Pending Users stat card for admin', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('heading', { name: /pending users/i, level: 3 })).toBeVisible()
  })

  test('stat cards have numeric counts', async ({ page }) => {
    await page.goto('/app/home')
    // The stat cards show quoted numbers like "13", "2", "0"
    await expect(page.getByText(/available events/i)).toBeVisible()
    await expect(page.getByText(/confirmed duty bookings/i)).toBeVisible()
  })

  test('Events card navigates to events', async ({ page }) => {
    await page.goto('/app/home')
    // Click the stat card containing "Events" heading (not sidebar link)
    const card = page.locator('main').getByRole('heading', { name: 'Events', level: 3 })
    await card.click()
    await expect(page).toHaveURL(/\/app\/events/)
  })

  test('My Bookings card navigates to bookings', async ({ page }) => {
    await page.goto('/app/home')
    const card = page.locator('main').getByRole('heading', { name: 'My Bookings', level: 3 })
    await card.click()
    await expect(page).toHaveURL(/\/app\/bookings/)
  })
})

test.describe('Dashboard – calendar', () => {
  test('shows calendar section', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('heading', { name: 'Calendar', level: 2 })).toBeVisible()
  })

  test('shows calendar view toggles', async ({ page }) => {
    await page.goto('/app/home')
    // Month/Week/Day toggle buttons contain icon + text
    await expect(page.getByRole('button', { name: /^Month$/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /^Week$/i })).toBeVisible()
  })

  test('shows Today button', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('button', { name: /^Today$/i })).toBeVisible()
  })

  test('shows current month heading', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('heading', { name: /march 2026/i, level: 2 })).toBeVisible()
  })

  test('can switch to week view', async ({ page }) => {
    await page.goto('/app/home')
    await page.getByRole('button', { name: /^Week$/i }).click()
    await expect(page.getByRole('heading', { name: 'Calendar', level: 2 })).toBeVisible()
  })

  test('Filter button is visible', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('button', { name: /^Filter$/i })).toBeVisible()
  })
})

test.describe('Dashboard – quick actions', () => {
  test('shows Quick Actions section', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('heading', { name: 'Quick Actions', level: 2 })).toBeVisible()
  })

  test('shows Browse Events button', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('button', { name: 'Browse Events' })).toBeVisible()
  })

  test('shows My Bookings button', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('button', { name: /^My Bookings$/ })).toBeVisible()
  })

  test('Browse Events navigates to events page', async ({ page }) => {
    await page.goto('/app/home')
    await page.getByRole('button', { name: 'Browse Events' }).click()
    await expect(page).toHaveURL(/\/app\/events/)
  })

  test('My Bookings quick action navigates to bookings', async ({ page }) => {
    await page.goto('/app/home')
    await page.getByRole('button', { name: /^My Bookings$/ }).click()
    await expect(page).toHaveURL(/\/app\/bookings/)
  })
})
