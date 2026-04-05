/**
 * E2E tests for Events from a member (non-admin) perspective.
 */
import { expect, test } from '../../fixtures.js'
import {
  type DutySlotRead,
  type EventWithSlots,
  createEventWithSlots,
  deleteEvent,
  listSlots,
  publishEvent,
  uniqueName,
} from '../../helpers/api.js'

let created: EventWithSlots
let slots: DutySlotRead[]
const eventName = uniqueName('E2E Member Event')

test.beforeEach(async ({ adminPage }) => {
  await adminPage.goto('/app/events')
  created = await createEventWithSlots(adminPage, {
    name: eventName,
    startTime: '10:00',
    endTime: '12:00',
    slotDuration: 60,
    peoplePerSlot: 5,
  })
  await publishEvent(adminPage, created.event.id)
  slots = await listSlots(adminPage, created.event.id)
})

test.afterEach(async ({ adminPage }) => {
  await deleteEvent(adminPage, created.event.id).catch(() => {})
})

// ── RBAC ─────────────────────────────────────────────────────────────────────

test.describe('Member – events RBAC', () => {
  test('member does not see Create Event button', async ({ memberPage: member }) => {
    await member.goto('/app/events')
    await expect(member.getByTestId('btn-create-event')).toBeHidden()
  })

  test('member does not see edit/delete buttons on event detail', async ({
    memberPage: member,
  }) => {
    await member.goto(`/app/events/${created.event.id}`)
    await expect(member.getByRole('heading', { name: created.event.name })).toBeVisible()
    await expect(member.getByTestId('btn-edit-event')).toBeHidden()
    await expect(member.getByTestId('btn-add-slots')).toBeHidden()
  })

  test('member cannot access create event page', async ({ memberPage: member }) => {
    await member.goto('/app/events/create')
    // Should redirect away since it requires admin role
    await expect(member).not.toHaveURL(/\/app\/events\/create/)
  })
})

// ── member viewing ───────────────────────────────────────────────────────────

test.describe('Member – events viewing', () => {
  test('member can see published events', async ({ memberPage: member }) => {
    await member.goto('/app/events')
    // Use search to find the event (list is paginated)
    await member.getByTestId('input-search').fill(created.event.name)
    await expect(member.getByRole('heading', { name: created.event.name })).toBeVisible()
  })

  test('member can view event detail', async ({ memberPage: member }) => {
    await member.goto(`/app/events/${created.event.id}`)
    await expect(member.getByRole('heading', { name: created.event.name })).toBeVisible()
    // Slots should be visible (dynamic data)
    await expect(member.getByText(/0\/5/).first()).toBeVisible()
  })

  test('member can book a slot', async ({ memberPage: member }) => {
    await member.goto(`/app/events/${created.event.id}`)
    await expect(member.getByText(/0\/5/).first()).toBeVisible()
    await member.getByText(/0\/5/).first().click()
    // Handle booking confirmation dialog if it appears
    const confirmBtn = member.getByRole('button', { name: /confirm|bestätigen/i })
    if (await confirmBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await confirmBtn.click()
    }
    await expect(member.getByText(/1\/5/).first()).toBeVisible()
  })
})
