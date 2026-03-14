/**
 * E2E tests for Events list view.
 */

import { expect, test } from '@playwright/test'
import {
  type EventWithSlots,
  createEventWithSlots,
  deleteEvent,
  publishEvent,
} from '../../helpers/api'

// ── navigation ───────────────────────────────────────────────────────────────

test.describe('Events – navigation', () => {
  test('sidebar shows Events link', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('link', { name: /^Events$/i })).toBeVisible()
  })

  test('clicking sidebar link navigates to /app/events', async ({ page }) => {
    await page.goto('/app/home')
    await page.getByRole('link', { name: /^Events$/i }).click()
    await expect(page).toHaveURL(/\/app\/events$/)
  })

  test('direct navigation to /app/events works', async ({ page }) => {
    await page.goto('/app/events')
    await expect(page).toHaveURL(/\/app\/events$/)
  })
})

// ── list view ────────────────────────────────────────────────────────────────

test.describe('Events – list view', () => {
  let created: EventWithSlots

  test.beforeEach(async ({ page }) => {
    await page.goto('/app/events')
    created = await createEventWithSlots(page, { name: 'E2E Test Event List' })
    await publishEvent(page, created.event.id)
  })

  test.afterEach(async ({ page }) => {
    await deleteEvent(page, created.event.id).catch(() => {})
  })

  test('shows heading and search input', async ({ page }) => {
    await page.goto('/app/events')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByPlaceholder(/search/i)).toBeVisible()
  })

  test('created event appears in list after reload', async ({ page }) => {
    // Reload to pick up the newly created + published event
    await page.reload()
    await expect(page.getByText(created.event.name).first()).toBeVisible({ timeout: 10000 })
  })

  test('search filters events by name', async ({ page }) => {
    await page.reload()
    await expect(page.getByText(created.event.name).first()).toBeVisible({ timeout: 10000 })

    const searchInput = page.getByPlaceholder(/search/i)
    await searchInput.fill('E2E Test Event List')
    await expect(page.getByText(created.event.name).first()).toBeVisible()

    await searchInput.fill('zzzznomatch')
    await expect(page.getByText(created.event.name)).toBeHidden()
  })

  test('clicking an event card navigates to detail', async ({ page }) => {
    await page.reload()
    await expect(page.getByText(created.event.name).first()).toBeVisible({ timeout: 10000 })
    await page.getByText(created.event.name).first().click()
    await expect(page).toHaveURL(new RegExp(`/app/events/${created.event.id}`))
  })
})

// ── view mode toggles ────────────────────────────────────────────────────────

test.describe('Events – view modes', () => {
  test('can switch to cards view', async ({ page }) => {
    await page.goto('/app/events')
    await page.getByRole('button', { name: /cards/i }).click()
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('can switch to calendar view', async ({ page }) => {
    await page.goto('/app/events')
    await page.getByRole('button', { name: /calendar/i }).click()
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('can switch back to list view', async ({ page }) => {
    await page.goto('/app/events')
    await page.getByRole('button', { name: /calendar/i }).click()
    await page.getByRole('button', { name: /list/i }).click()
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })
})

// ── admin actions ────────────────────────────────────────────────────────────

test.describe('Events – admin', () => {
  test('Create button is visible for admin', async ({ page }) => {
    await page.goto('/app/events')
    await expect(page.getByRole('button', { name: /create/i })).toBeVisible()
  })

  test('Create button navigates to create page', async ({ page }) => {
    await page.goto('/app/events')
    await page.getByRole('button', { name: /create/i }).click()
    await expect(page).toHaveURL(/\/app\/events\/create/)
  })
})
