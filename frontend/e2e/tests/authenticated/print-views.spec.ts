/**
 * E2E smoke tests for Print views.
 */
import { expect, test } from '../../fixtures.js'
import {
  type EventGroupRead,
  type EventWithSlots,
  createEventWithSlots,
  createGroup,
  deleteEvent,
  deleteGroup,
  publishEvent,
  uniqueName,
} from '../../helpers/api.js'

let created: EventWithSlots
let group: EventGroupRead

test.beforeEach(async ({ adminPage: page }) => {
  await page.goto('/app/events')
  group = await createGroup(page, uniqueName('E2E Print Group'))
  created = await createEventWithSlots(page, {
    name: uniqueName('E2E Print Event'),
    startTime: '09:00',
    endTime: '12:00',
    slotDuration: 60,
    peoplePerSlot: 2,
    eventGroupId: group.id,
  })
  await publishEvent(page, created.event.id)
})

test.afterEach(async ({ adminPage: page }) => {
  await deleteEvent(page, created.event.id).catch(() => {})
  await deleteGroup(page, group.id).catch(() => {})
})

test.describe('Print Event – smoke', () => {
  test('print event page loads', async ({ adminPage: page }) => {
    await page.goto(`/print/events/${created.event.id}`)
    await expect(page).toHaveURL(new RegExp(`/print/events/${created.event.id}`))
  })

  test('shows print toolbar', async ({ adminPage: page }) => {
    await page.goto(`/print/events/${created.event.id}`)
    await expect(page.getByTestId('print-toolbar')).toBeVisible()
  })

  test('shows print content', async ({ adminPage: page }) => {
    await page.goto(`/print/events/${created.event.id}`)
    await expect(page.getByTestId('print-content')).toBeVisible()
  })

  test('shows event name in print content', async ({ adminPage: page }) => {
    await page.goto(`/print/events/${created.event.id}`)
    // Dynamic event name from fixture
    await expect(page.getByText(created.event.name).first()).toBeVisible()
  })
})

test.describe('Print Event Group – smoke', () => {
  test('print event group page loads', async ({ adminPage: page }) => {
    await page.goto(`/print/event-groups/${group.id}`)
    await expect(page).toHaveURL(new RegExp(`/print/event-groups/${group.id}`))
  })

  test('shows print toolbar for group', async ({ adminPage: page }) => {
    await page.goto(`/print/event-groups/${group.id}`)
    await expect(page.getByTestId('print-toolbar')).toBeVisible()
  })

  test('shows group name in print content', async ({ adminPage: page }) => {
    await page.goto(`/print/event-groups/${group.id}`)
    // Dynamic group name from fixture
    await expect(page.getByText(group.name)).toBeVisible()
  })
})
