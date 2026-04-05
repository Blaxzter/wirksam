/**
 * E2E tests for Dashboard page — stats cards, calendar, quick actions.
 */

import { test, expect } from '../../fixtures.js'

test.describe('Dashboard – stats cards', () => {
  test('shows Events stat card', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('stat-card-events')).toBeVisible()
  })

  test('shows My Bookings stat card', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('stat-card-bookings')).toBeVisible()
  })

  test('shows Pending Users stat card for admin', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('stat-card-users')).toBeVisible()
  })

  test('Events card navigates to events', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('stat-card-events').click()
    await expect(page).toHaveURL(/\/app\/events/)
  })

  test('My Bookings card navigates to bookings', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('stat-card-bookings').click()
    await expect(page).toHaveURL(/\/app\/bookings/)
  })
})

test.describe('Dashboard – calendar', () => {
  test('shows calendar section', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('dashboard-calendar')).toBeVisible()
  })

  test('Filter button is visible', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('btn-calendar-filter')).toBeVisible()
  })
})

test.describe('Dashboard – quick actions', () => {
  test('shows Quick Actions section', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('dashboard-quick-actions')).toBeVisible()
  })

  test('shows Browse Events button', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('btn-browse-events')).toBeVisible()
  })

  test('shows My Bookings button', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('btn-my-bookings')).toBeVisible()
  })

  test('Browse Events navigates to events page', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('btn-browse-events').click()
    await expect(page).toHaveURL(/\/app\/events/)
  })

  test('My Bookings quick action navigates to bookings', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('btn-my-bookings').click()
    await expect(page).toHaveURL(/\/app\/bookings/)
  })
})
