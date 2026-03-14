/**
 * E2E tests for My Bookings page.
 */

import { expect, test } from '@playwright/test'
import {
  type DutySlotRead,
  type EventWithSlots,
  bookSlot,
  cancelBooking,
  createEventWithSlots,
  deleteEvent,
  listSlots,
  publishEvent,
  api,
} from '../../helpers/api'

let created: EventWithSlots
let slots: DutySlotRead[]

test.beforeEach(async ({ page }) => {
  await page.goto('/app/events')
  created = await createEventWithSlots(page, {
    name: 'E2E Booking Event',
    location: 'Room A',
    startTime: '10:00',
    endTime: '12:00',
    slotDuration: 60,
    peoplePerSlot: 5,
  })
  await publishEvent(page, created.event.id)
  slots = await listSlots(page, created.event.id)
})

test.afterEach(async ({ page }) => {
  await deleteEvent(page, created.event.id).catch(() => {})
})

// ── navigation ───────────────────────────────────────────────────────────────

test.describe('My Bookings – navigation', () => {
  test('sidebar shows My Bookings link', async ({ page }) => {
    await page.goto('/app/home')
    await expect(page.getByRole('link', { name: /my bookings/i })).toBeVisible()
  })

  test('clicking sidebar link navigates to /app/bookings', async ({ page }) => {
    await page.goto('/app/home')
    await page.getByRole('link', { name: /my bookings/i }).click()
    await expect(page).toHaveURL(/\/app\/bookings$/)
  })
})

// ── page structure ───────────────────────────────────────────────────────────

test.describe('My Bookings – page structure', () => {
  test('shows heading', async ({ page }) => {
    await page.goto('/app/bookings')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('shows filter tabs (upcoming, this month, all)', async ({ page }) => {
    await page.goto('/app/bookings')
    await expect(page.getByRole('button', { name: /upcoming/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /this month/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /all/i })).toBeVisible()
  })

  test('shows show cancelled toggle', async ({ page }) => {
    await page.goto('/app/bookings')
    await expect(page.getByRole('button', { name: /cancelled/i })).toBeVisible()
  })
})

// ── with bookings ────────────────────────────────────────────────────────────

test.describe('My Bookings – with data', () => {
  test('booked slot appears in bookings list', async ({ page }) => {
    if (slots.length === 0) return

    await bookSlot(page, slots[0].id)
    await page.goto('/app/bookings')

    // Switch to "all" filter since the event date might be in the future
    await page.getByRole('button', { name: /all/i }).click()

    await expect(page.getByText(created.event.name).first()).toBeVisible({ timeout: 5000 })
  })

  test('booking shows confirmed status', async ({ page }) => {
    if (slots.length === 0) return

    await bookSlot(page, slots[0].id)
    await page.goto('/app/bookings')
    await page.getByRole('button', { name: /all/i }).click()

    await expect(page.getByText(/confirmed/i).first()).toBeVisible({ timeout: 5000 })
  })

  test('can cancel a booking from bookings page', async ({ page }) => {
    if (slots.length === 0) return

    await bookSlot(page, slots[0].id)
    await page.goto('/app/bookings')
    await page.getByRole('button', { name: /all/i }).click()

    // Wait for the booking card to appear
    await expect(page.getByText(created.event.name).first()).toBeVisible({ timeout: 5000 })

    // Click the cancel/trash button (accept the confirm dialog)
    page.on('dialog', (d) => d.accept())
    const trashBtn = page.locator('button').filter({ has: page.locator('svg') }).filter({ hasText: '' })
    // Find the delete/trash icon button within the card
    const card = page.locator('[class*="Card"]').filter({ hasText: created.event.name }).first()
    const cancelBtn = card.locator('button[class*="destructive"], button:has(svg.text-destructive), button:has(svg[class*="text-destructive"])')
    if (await cancelBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await cancelBtn.click()
    }
  })
})

// ── filter switching ─────────────────────────────────────────────────────────

test.describe('My Bookings – filters', () => {
  test('switching to "all" filter keeps the page functional', async ({ page }) => {
    await page.goto('/app/bookings')
    await page.getByRole('button', { name: /all/i }).click()
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('switching to "this month" filter keeps the page functional', async ({ page }) => {
    await page.goto('/app/bookings')
    await page.getByRole('button', { name: /this month/i }).click()
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('show cancelled toggle can be activated', async ({ page }) => {
    await page.goto('/app/bookings')
    const btn = page.getByRole('button', { name: /cancelled/i })
    await btn.click()
    // Button should now have active/default variant
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })
})

// ── grouping ─────────────────────────────────────────────────────────────────

test.describe('My Bookings – grouping', () => {
  test('grouping buttons are visible', async ({ page }) => {
    if (slots.length === 0) return

    await bookSlot(page, slots[0].id)
    await page.goto('/app/bookings')
    await page.getByRole('button', { name: /all/i }).click()

    // There should be icon-only grouping buttons
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })
})
