/**
 * E2E tests for Event Edit and Add Slots views.
 */
import { expect, test } from '../../fixtures.js'
import {
  type EventWithSlots,
  createEventWithSlots,
  deleteEvent,
  publishEvent,
  uniqueName,
} from '../../helpers/api.js'

let created: EventWithSlots

test.beforeEach(async ({ adminPage: page }) => {
  await page.goto('/app/events')
  created = await createEventWithSlots(page, {
    name: uniqueName('E2E Edit Event'),
    startTime: '09:00',
    endTime: '17:00',
    slotDuration: 120,
    peoplePerSlot: 2,
  })
  await publishEvent(page, created.event.id)
})

test.afterEach(async ({ adminPage: page }) => {
  await deleteEvent(page, created.event.id).catch(() => {})
})

test.describe('Event Edit – page access', () => {
  test('can navigate to edit page via URL', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}/edit`)
    await expect(page).toHaveURL(new RegExp(`/app/events/${created.event.id}/edit`))
  })

  test('shows edit page heading', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}/edit`)
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('shows back button', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}/edit`)
    await expect(page.getByTestId('btn-back')).toBeVisible()
  })

  test('shows schedule configuration section', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}/edit`)
    await expect(page.getByTestId('section-schedule')).toBeVisible()
  })
})

test.describe('Event Add Slots – page access', () => {
  test('can navigate to add-slots page via URL', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}/add-slots`)
    await expect(page).toHaveURL(new RegExp(`/app/events/${created.event.id}/add-slots`))
  })

  test('shows add-slots heading', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}/add-slots`)
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('shows back button', async ({ adminPage: page }) => {
    await page.goto(`/app/events/${created.event.id}/add-slots`)
    await expect(page.getByTestId('btn-back')).toBeVisible()
  })
})

test.describe('Event Edit/Add Slots – member RBAC', () => {
  test('member cannot access edit page', async ({ memberPage: member }) => {
    await member.goto(`/app/events/${created.event.id}/edit`)
    await expect(member).not.toHaveURL(/\/edit/)
  })

  test('member cannot access add-slots page', async ({ memberPage: member }) => {
    await member.goto(`/app/events/${created.event.id}/add-slots`)
    await expect(member).not.toHaveURL(/\/add-slots/)
  })
})
