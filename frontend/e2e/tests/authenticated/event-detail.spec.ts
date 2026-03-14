/**
 * E2E tests for Event Detail page — viewing, booking, status, admin actions.
 */

import { expect, test } from '@playwright/test'
import {
  type DutySlotRead,
  type EventWithSlots,
  bookSlot,
  createEventWithSlots,
  deleteEvent,
  listSlots,
  publishEvent,
} from '../../helpers/api'

let created: EventWithSlots
let slots: DutySlotRead[]

test.beforeEach(async ({ page }) => {
  await page.goto('/app/events')
  created = await createEventWithSlots(page, {
    name: 'E2E Detail Event',
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

test.afterEach(async ({ page }) => {
  await deleteEvent(page, created.event.id).catch(() => {})
})

// ── page structure ───────────────────────────────────────────────────────────

test.describe('Event Detail – page structure', () => {
  test('shows event name and status', async ({ page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByRole('heading', { name: created.event.name })).toBeVisible()
    await expect(page.getByText(/published/i)).toBeVisible()
  })

  test('shows event description', async ({ page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByText('E2E test description')).toBeVisible()
  })

  test('shows location in header', async ({ page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByText('Main Hall')).toBeVisible()
  })

  test('shows category in header', async ({ page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByText('Sound')).toBeVisible()
  })

  test('shows duty slots section', async ({ page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByRole('heading', { name: /slots/i })).toBeVisible()
  })

  test('shows slot time cards', async ({ page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    // Slots should show time and availability count
    await expect(page.getByText(/0\/3/).first()).toBeVisible()
  })

  test('back button navigates to events list', async ({ page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await page.getByRole('button', { name: /back/i }).click()
    await expect(page).toHaveURL(/\/app\/events$/)
  })
})

// ── booking ──────────────────────────────────────────────────────────────────

test.describe('Event Detail – booking', () => {
  test('clicking a slot books it', async ({ page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    // Wait for slots to render — find slot cards by their availability text
    const slotCard = page.locator('text=/0\/3/').first()
    await expect(slotCard).toBeVisible()

    // Click first available slot card
    await slotCard.click()

    // Should show booking count updated
    await expect(page.locator('text=/1\/3/').first()).toBeVisible({ timeout: 5000 })
  })

  test('booked slot shows in My Bookings summary', async ({ page }) => {
    // Pre-book via API
    if (slots.length > 0) {
      await bookSlot(page, slots[0].id)
    }

    await page.goto(`/app/events/${created.event.id}`)
    // The "My Bookings" heading is inside the main content area
    await expect(page.locator('main').getByText(/my bookings/i).first()).toBeVisible({ timeout: 5000 })
  })

  test('clicking a booked slot cancels it', async ({ page }) => {
    // Pre-book via API
    if (slots.length > 0) {
      await bookSlot(page, slots[0].id)
    }

    await page.goto(`/app/events/${created.event.id}`)
    // Wait for booked state to load
    await expect(page.locator('text=/1\/3/').first()).toBeVisible({ timeout: 5000 })

    // Click to cancel (will show confirm dialog)
    page.on('dialog', (d) => d.accept())
    await page.locator('text=/1\/3/').first().click()

    // Should revert to 0 bookings
    await expect(page.locator('text=/0\/3/').first()).toBeVisible({ timeout: 5000 })
  })
})

// ── admin status changes ─────────────────────────────────────────────────────

test.describe('Event Detail – admin actions', () => {
  test('admin can change event status to archived', async ({ page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    // Click the status dropdown
    await page.getByText(/published/i).first().click()
    await page.getByText(/archived/i).click()
    await expect(page.getByText(/archived/i).first()).toBeVisible({ timeout: 5000 })
  })

  test('admin sees edit button', async ({ page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByRole('button', { name: /edit/i })).toBeVisible()
  })

  test('admin sees delete button', async ({ page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    // Delete is typically an icon button with trash icon
    const deleteBtn = page.locator('button').filter({ has: page.locator('[class*="text-destructive"]') })
    await expect(deleteBtn.first()).toBeVisible()
  })

  test('admin sees Add Slots button', async ({ page }) => {
    await page.goto(`/app/events/${created.event.id}`)
    await expect(page.getByRole('button', { name: /add slots/i })).toBeVisible()
  })

  test('admin can delete event', async ({ page }) => {
    const toDelete = await createEventWithSlots(page, { name: 'E2E Delete Me Event' })
    await publishEvent(page, toDelete.event.id)

    await page.goto(`/app/events/${toDelete.event.id}`)
    // Click the destructive delete button (icon button)
    const deleteBtn = page.locator('button.bg-destructive, button[class*="destructive"]').last()
    await deleteBtn.click()

    // Confirm in the dialog
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByRole('button', { name: /confirm|delete|yes/i }).click()

    // Should navigate back to events list
    await expect(page).toHaveURL(/\/app\/events$/, { timeout: 5000 })
  })
})
