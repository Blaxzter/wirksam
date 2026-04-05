/**
 * E2E tests for Events list view.
 */
import { expect, test } from '../../fixtures.js'
import {
  type EventWithSlots,
  createEventWithSlots,
  deleteEvent,
  publishEvent,
  uniqueName,
} from '../../helpers/api.js'

// ── navigation ───────────────────────────────────────────────────────────────

test.describe('Events – navigation', () => {
  test('sidebar shows Events link', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('sidebar-link-events')).toBeVisible()
  })

  test('clicking sidebar link navigates to /app/events', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('sidebar-link-events').click()
    await expect(page).toHaveURL(/\/app\/events$/)
  })

  test('direct navigation to /app/events works', async ({ adminPage: page }) => {
    await page.goto('/app/events')
    await expect(page).toHaveURL(/\/app\/events$/)
  })
})

// ── list view ────────────────────────────────────────────────────────────────

test.describe('Events – list view', () => {
  let created: EventWithSlots

  test.beforeEach(async ({ adminPage: page }) => {
    await page.goto('/app/events')
    created = await createEventWithSlots(page, { name: uniqueName('E2E Test Event List') })
    await publishEvent(page, created.event.id)
  })

  test.afterEach(async ({ adminPage: page }) => {
    await deleteEvent(page, created.event.id).catch(() => {})
  })

  test('shows heading and search input', async ({ adminPage: page }) => {
    await page.goto('/app/events')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expect(page.getByTestId('input-search')).toBeVisible()
  })

  test('created event appears in list after search', async ({ adminPage: page }) => {
    // Use search to find the event (list is paginated with infinite scroll)
    await page.reload()
    const content = page.getByTestId('main-content')
    await page.getByTestId('input-search').fill(created.event.name)
    await expect(content.getByText(created.event.name)).toBeVisible()
  })

  test('search filters events by name', async ({ adminPage: page }) => {
    const searchInput = page.getByTestId('input-search')
    const content = page.getByTestId('main-content')

    await searchInput.fill(created.event.name)
    await expect(content.getByText(created.event.name)).toBeVisible()

    await searchInput.fill('zzzznomatch')
    await expect(content.getByText(created.event.name)).toBeHidden()
  })

  test('clicking an event card navigates to detail', async ({ adminPage: page }) => {
    const content = page.getByTestId('main-content')
    // Search to find the event in the paginated list
    await page.getByTestId('input-search').fill(created.event.name)
    await expect(content.getByText(created.event.name)).toBeVisible()
    await content.getByText(created.event.name).click()
    await expect(page).toHaveURL(new RegExp(`/app/events/${created.event.id}`))
  })
})

// ── view mode toggles ────────────────────────────────────────────────────────

test.describe('Events – view modes', () => {
  test('can switch to cards view', async ({ adminPage: page }) => {
    await page.goto('/app/events')
    await page.getByTestId('btn-view-cards').click()
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('can switch to calendar view', async ({ adminPage: page }) => {
    await page.goto('/app/events')
    await page.getByTestId('btn-view-calendar').click()
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('can switch back to list view', async ({ adminPage: page }) => {
    await page.goto('/app/events')
    await page.getByTestId('btn-view-calendar').click()
    await page.getByTestId('btn-view-list').click()
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })
})

// ── admin actions ────────────────────────────────────────────────────────────

test.describe('Events – admin', () => {
  test('Create button is visible for admin', async ({ adminPage: page }) => {
    await page.goto('/app/events')
    await expect(page.getByTestId('btn-create-event')).toBeVisible()
  })

  test('Create button navigates to create page', async ({ adminPage: page }) => {
    await page.goto('/app/events')
    await page.getByTestId('btn-create-event').click()
    await expect(page).toHaveURL(/\/app\/events\/create/)
  })
})
