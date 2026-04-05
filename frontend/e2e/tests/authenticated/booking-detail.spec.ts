/**
 * E2E tests for Booking Detail view.
 */
import { expect, test } from '../../fixtures.js'
import {
  type BookingRead,
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
let booking: BookingRead

test.beforeEach(async ({ adminPage: page }) => {
  await page.goto('/app/events')
  created = await createEventWithSlots(page, {
    name: uniqueName('E2E Booking Detail Event'),
    startTime: '10:00',
    endTime: '12:00',
    slotDuration: 60,
    peoplePerSlot: 5,
  })
  await publishEvent(page, created.event.id)
  slots = await listSlots(page, created.event.id)
  if (slots.length > 0) {
    booking = await bookSlot(page, slots[0].id)
  }
})

test.afterEach(async ({ adminPage: page }) => {
  await deleteEvent(page, created.event.id).catch(() => {})
})

test.describe('Booking Detail – navigation', () => {
  test('can navigate to booking detail via URL', async ({ adminPage: page }) => {
    if (!booking) return
    await page.goto(`/app/bookings/${booking.id}`)
    await expect(page).toHaveURL(new RegExp(`/app/bookings/${booking.id}`))
  })

  test('shows back button', async ({ adminPage: page }) => {
    if (!booking) return
    await page.goto(`/app/bookings/${booking.id}`)
    await expect(page.getByTestId('btn-back')).toBeVisible()
  })
})

test.describe('Booking Detail – page structure', () => {
  test('shows page heading', async ({ adminPage: page }) => {
    if (!booking) return
    await page.goto(`/app/bookings/${booking.id}`)
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('shows booking status badge', async ({ adminPage: page }) => {
    if (!booking) return
    await page.goto(`/app/bookings/${booking.id}`)
    await expect(page.getByTestId('booking-status')).toBeVisible()
  })

  test('shows slot info section', async ({ adminPage: page }) => {
    if (!booking) return
    await page.goto(`/app/bookings/${booking.id}`)
    await expect(page.getByTestId('section-slot-info')).toBeVisible()
  })

  test('shows reminders section', async ({ adminPage: page }) => {
    if (!booking) return
    await page.goto(`/app/bookings/${booking.id}`)
    await expect(page.getByTestId('section-reminders')).toBeVisible()
  })
})

test.describe('Booking Detail – actions', () => {
  test('shows cancel button for confirmed booking', async ({ adminPage: page }) => {
    if (!booking) return
    await page.goto(`/app/bookings/${booking.id}`)
    await expect(page.getByTestId('btn-cancel-booking')).toBeVisible()
  })
})
