/**
 * E2E tests for Event Detail page — viewing, booking, status, admin actions.
 */
import { expect, test } from '../../fixtures.js'
import {
  type DutySlotRead,
  type EventWithSlots,
  bookSlot,
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
    name: uniqueName('E2E Detail Event'),
    description: 'E2E test description',
    location: 'Main Hall',
    category: 'Sound',
    startTime: '09:00',
    endTime: '11:00',
    slotDuration: 60,
    peoplePerSlot: 3,
  })
  await publishEvent(page, created.event.id)
  slots = await listSlots(page, created.event.id)
})

test.afterEach(async ({ adminPage: page }) => {
  await deleteEvent(page, created.event.id).catch(() => {})
})

// ── page structure ───────────────────────────────────────────────────────────

test.describe('Event Detail – page structure', () => {
  test('shows event name and status', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByTestId('page-heading')).toContainText(created.event.name)
    await expect(page.getByTestId('event-status')).toBeVisible()
  })

  test('shows event description', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByText('E2E test description')).toBeVisible()
  })

  test('shows location in header', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByText('Main Hall')).toBeVisible()
  })

  test('shows category in header', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByText('Sound')).toBeVisible()
  })

  test('shows duty slots section', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByTestId('section-duty-slots')).toBeVisible()
  })

  test('shows slot time cards', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    // Slots should show time and availability count
    await expect(page.getByText(/0\/3/).first()).toBeVisible()
  })

  test('back button navigates to events list', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await page.getByTestId('btn-back').click()
    await expect(page).toHaveURL(/\/app\/events$/)
  })
})

// ── booking ──────────────────────────────────────────────────────────────────

test.describe('Event Detail – booking', () => {
  test('clicking a slot books it', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    // Wait for slots to render — find slot cards by their availability text
    const slotCard = page.getByText(/0\/3/).first()
    await expect(slotCard).toBeVisible()

    // Click first available slot card
    await slotCard.click()

    // Handle booking confirmation dialog if it appears
    const confirmBtn = page.getByRole('button', { name: /confirm|bestätigen/i })
    if (await confirmBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await confirmBtn.click()
    }

    // Should show booking count updated
    await expect(page.getByText(/1\/3/).first()).toBeVisible()
  })

  test('booked slot shows in My Bookings summary', async ({ adminPage: page }) => {
    // Pre-book via API
    if (slots.length > 0) {
      await bookSlot(page, slots[0].id)
    }

    await page.goto(`/app/events/${created.event.id}`)
    // The "My Bookings" / "Meine Buchungen" heading is inside the main content area
    await expect(
      page
        .getByTestId('main-content')
        .getByText(/my bookings|meine buchungen/i)
        .first(),
    ).toBeVisible()
  })

  test('clicking a booked slot cancels it', async ({ adminPage: page }) => {
    // Pre-book via API
    if (slots.length > 0) {
      await bookSlot(page, slots[0].id)
    }

    await page.goto(`/app/events/${created.event.id}`)
    // Wait for booked state to load
    await expect(page.getByText(/1\/3/).first()).toBeVisible()

    // Click to cancel
    await page.getByText(/1\/3/).first().click()

    // Handle confirmation dialog (app-level dialog, not browser dialog)
    const confirmBtn = page.getByRole('button', { name: /confirm|bestätigen/i })
    if (await confirmBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await confirmBtn.click()
    }

    // Should revert to 0 bookings
    await expect(page.getByText(/0\/3/).first()).toBeVisible()
  })
})

// ── admin status changes ─────────────────────────────────────────────────────

test.describe('Event Detail – admin actions', () => {
  test('admin can change event status to archived', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    // Click the status dropdown (inside the span wrapper)
    const statusEl = page.getByTestId('event-status')
    await expect(statusEl).toBeVisible()
    await statusEl.click()
    await page.getByText(/archived|archiviert/i).click()
    await expect(statusEl).toBeVisible()
  })

  test('admin sees edit button', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByTestId('btn-edit-event')).toBeVisible()
  })

  test('admin sees delete button', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByTestId('btn-delete-event')).toBeVisible()
  })

  test('admin sees Add Slots button', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByTestId('btn-add-slots')).toBeVisible()
  })

  test('admin can delete event', async ({ adminPage: page }) => {
    const toDelete = await createEventWithSlots(page, { name: uniqueName('E2E Delete Me') })
    await publishEvent(page, toDelete.event.id)

    await page.goto(`/app/events/${toDelete.event.id}`)
    await page.getByTestId('btn-delete-event').click()

    // Confirm in the dialog
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByRole('button', { name: /confirm|delete|yes|bestätigen|löschen|ja/i }).click()

    // Should navigate back to events list
    await expect(page).toHaveURL(/\/app\/events$/)
  })
})
