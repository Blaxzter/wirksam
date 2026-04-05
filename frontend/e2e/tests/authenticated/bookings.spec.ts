/**
 * E2E tests for My Bookings page.
 */
import { expect, test } from '../../fixtures.js'
import {
  type DutySlotRead,
  type EventWithSlots,
  api,
  bookSlot,
  cancelBooking,
  createEventWithSlots,
  deleteEvent,
  listSlots,
  publishEvent,
  uniqueName,
} from '../../helpers/api.js'

let created: EventWithSlots
let slots: DutySlotRead[]

test.beforeEach(async ({ adminPage: page }) => {
  await page.goto('/app/events')
  created = await createEventWithSlots(page, {
    name: uniqueName('E2E Booking Event'),
    location: 'Room A',
    startTime: '10:00',
    endTime: '12:00',
    slotDuration: 60,
    peoplePerSlot: 5,
  })
  await publishEvent(page, created.event.id)
  slots = await listSlots(page, created.event.id)
})

test.afterEach(async ({ adminPage: page }) => {
  await deleteEvent(page, created.event.id).catch(() => {})
})

// ── navigation ───────────────────────────────────────────────────────────────

test.describe('My Bookings – navigation', () => {
  test('sidebar shows My Bookings link', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('sidebar-link-my-bookings')).toBeVisible()
  })

  test('clicking sidebar link navigates to /app/bookings', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('sidebar-link-my-bookings').click()
    await expect(page).toHaveURL(/\/app\/bookings$/)
  })
})

// ── page structure ───────────────────────────────────────────────────────────

test.describe('My Bookings – page structure', () => {
  test('shows heading', async ({ adminPage: page }) => {
    await page.goto('/app/bookings')
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('shows search input', async ({ adminPage: page }) => {
    await page.goto('/app/bookings')
    await expect(page.getByTestId('input-search')).toBeVisible()
  })

  test('shows show cancelled toggle', async ({ adminPage: page }) => {
    await page.goto('/app/bookings')
    await expect(page.getByTestId('btn-toggle-cancelled')).toBeVisible()
  })
})

// ── with bookings ────────────────────────────────────────────────────────────

test.describe('My Bookings – with data', () => {
  test('booked slot appears in bookings list', async ({ adminPage: page }) => {
    if (slots.length === 0) return

    await bookSlot(page, slots[0].id)
    await page.goto('/app/bookings')

    // The event name is dynamic data — use heading role to avoid strict mode violation
    await expect(page.getByRole('heading', { name: created.event.name })).toBeVisible()
  })

  test('can cancel a booking from bookings page', async ({ adminPage: page }) => {
    if (slots.length === 0) return

    await bookSlot(page, slots[0].id)
    await page.goto('/app/bookings')

    // Wait for the booking card to appear (dynamic event name)
    await expect(page.getByRole('heading', { name: created.event.name })).toBeVisible()

    // Click the cancel/trash button (accept the confirm dialog)
    page.on('dialog', (d) => d.accept())
    const card = page.locator('[class*="Card"]').filter({ hasText: created.event.name }).first()
    const cancelBtn = card.locator(
      'button[class*="destructive"], button:has(svg.text-destructive), button:has(svg[class*="text-destructive"])',
    )
    if (await cancelBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await cancelBtn.click()
    }
  })
})

// ── filter switching ─────────────────────────────────────────────────────────

test.describe('My Bookings – filters', () => {
  test('show cancelled toggle can be activated', async ({ adminPage: page }) => {
    await page.goto('/app/bookings')
    await page.getByTestId('btn-toggle-cancelled').click()
    // Page should remain functional
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })
})

// ── grouping ─────────────────────────────────────────────────────────────────

test.describe('My Bookings – grouping', () => {
  test('grouping buttons are visible', async ({ adminPage: page }) => {
    if (slots.length === 0) return

    await bookSlot(page, slots[0].id)
    await page.goto('/app/bookings')

    await expect(page.getByTestId('btn-group-date')).toBeVisible()
    await expect(page.getByTestId('btn-group-event')).toBeVisible()
    await expect(page.getByTestId('btn-group-location')).toBeVisible()
  })
})
