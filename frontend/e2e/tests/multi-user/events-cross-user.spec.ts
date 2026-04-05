/**
 * Cross-user E2E tests for Events & Bookings.
 *
 * Admin creates event with slots -> member books a slot -> admin sees booking count.
 */
import { expect, test } from '../../fixtures.js'
import {
  type EventWithSlots,
  createEventWithSlots,
  deleteEvent,
  publishEvent,
  uniqueName,
} from '../../helpers/api.js'

test.describe('Cross-user – event booking flow', () => {
  let created: EventWithSlots

  test.beforeEach(async ({ adminPage }) => {
    await adminPage.goto('/app/events')
    created = await createEventWithSlots(adminPage, {
      name: uniqueName('E2E Cross-User Booking Event'),
      startTime: '10:00',
      endTime: '12:00',
      slotDuration: 60,
      peoplePerSlot: 3,
    })
    await publishEvent(adminPage, created.event.id)
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteEvent(adminPage, created.event.id).catch(() => {})
  })

  test('member books slot, admin sees updated count', async ({ adminPage, memberPage }) => {
    // Member navigates to event and books first slot (dynamic slot counts)
    await memberPage.goto(`/app/events/${created.event.id}`)
    await expect(memberPage.getByText(/0\/3/).first()).toBeVisible()
    await memberPage.getByText(/0\/3/).first().click()
    // Handle booking confirmation dialog if it appears
    const confirmBtn = memberPage.getByRole('button', { name: /confirm|bestätigen/i })
    if (await confirmBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await confirmBtn.click()
    }
    await expect(memberPage.getByText(/1\/3/).first()).toBeVisible()

    // Admin sees the updated booking count (dynamic slot counts)
    await adminPage.goto(`/app/events/${created.event.id}`)
    await expect(adminPage.getByText(/1\/3/).first()).toBeVisible()
  })

  test('admin-created event visible to member in events list', async ({ memberPage }) => {
    await memberPage.goto('/app/events')
    // Use search to find the event (list is paginated)
    await memberPage.getByTestId('input-search').fill(created.event.name)
    await expect(memberPage.getByRole('heading', { name: created.event.name })).toBeVisible()
  })
})
