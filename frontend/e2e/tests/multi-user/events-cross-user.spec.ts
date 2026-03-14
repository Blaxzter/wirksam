/**
 * Cross-user E2E tests for Events & Bookings.
 *
 * Admin creates event with slots → member books a slot → admin sees booking count.
 */

import { expect, test } from '@playwright/test'
import {
  type EventWithSlots,
  createEventWithSlots,
  deleteEvent,
  publishEvent,
} from '../../helpers/api'

test.describe('Cross-user – event booking flow', () => {
  let created: EventWithSlots

  test.beforeEach(async ({ browser }) => {
    const adminCtx = await browser.newContext({ storageState: 'e2e/.auth/user.json' })
    const adminPage = await adminCtx.newPage()
    await adminPage.goto('/app/events')
    created = await createEventWithSlots(adminPage, {
      name: 'E2E Cross-User Booking Event',
      startTime: '10:00',
      endTime: '12:00',
      slotDuration: 60,
      peoplePerSlot: 3,
    })
    await publishEvent(adminPage, created.event.id)
    await adminCtx.close()
  })

  test.afterEach(async ({ browser }) => {
    const adminCtx = await browser.newContext({ storageState: 'e2e/.auth/user.json' })
    const adminPage = await adminCtx.newPage()
    await adminPage.goto('/app/events')
    await deleteEvent(adminPage, created.event.id).catch(() => {})
    await adminCtx.close()
  })

  test('member books slot, admin sees updated count', async ({ browser }) => {
    const adminCtx = await browser.newContext({ storageState: 'e2e/.auth/user.json' })
    const memberCtx = await browser.newContext({ storageState: 'e2e/.auth/member.json' })
    const adminPage = await adminCtx.newPage()
    const memberPage = await memberCtx.newPage()

    try {
      // Member navigates to event and books first slot
      await memberPage.goto(`/app/events/${created.event.id}`)
      await expect(memberPage.getByText(/0\/3/).first()).toBeVisible()
      await memberPage.getByText(/0\/3/).first().click()
      await expect(memberPage.getByText(/1\/3/).first()).toBeVisible({ timeout: 5000 })

      // Admin sees the updated booking count
      await adminPage.goto(`/app/events/${created.event.id}`)
      await expect(adminPage.getByText(/1\/3/).first()).toBeVisible({ timeout: 5000 })
    } finally {
      await adminCtx.close()
      await memberCtx.close()
    }
  })

  test('admin-created event visible to member in events list', async ({ browser }) => {
    const memberCtx = await browser.newContext({ storageState: 'e2e/.auth/member.json' })
    const memberPage = await memberCtx.newPage()

    try {
      await memberPage.goto('/app/events')
      await expect(memberPage.getByText(created.event.name)).toBeVisible()
    } finally {
      await memberCtx.close()
    }
  })
})
