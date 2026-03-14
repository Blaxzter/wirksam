/**
 * E2E tests for Events from a member (non-admin) perspective.
 */

import { expect, test } from '@playwright/test'
import {
  type DutySlotRead,
  type EventWithSlots,
  createEventWithSlots,
  deleteEvent,
  listSlots,
  publishEvent,
} from '../../helpers/api'

const MEMBER_STATE = 'e2e/.auth/member.json'

let created: EventWithSlots
let slots: DutySlotRead[]

test.beforeEach(async ({ page }) => {
  // Admin creates the event
  await page.goto('/app/events')
  created = await createEventWithSlots(page, {
    name: 'E2E Member Event Test',
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

// ── RBAC ─────────────────────────────────────────────────────────────────────

test.describe('Member – events RBAC', () => {
  test('member does not see Create Event button', async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: MEMBER_STATE })
    const member = await ctx.newPage()
    try {
      await member.goto('/app/events')
      await expect(member.getByRole('button', { name: /create/i })).toBeHidden()
    } finally {
      await ctx.close()
    }
  })

  test('member does not see edit/delete buttons on event detail', async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: MEMBER_STATE })
    const member = await ctx.newPage()
    try {
      await member.goto(`/app/events/${created.event.id}`)
      await expect(member.getByRole('heading', { name: created.event.name })).toBeVisible()
      await expect(member.getByRole('button', { name: /edit/i })).toBeHidden()
      await expect(member.getByRole('button', { name: /add slots/i })).toBeHidden()
    } finally {
      await ctx.close()
    }
  })

  test('member cannot access create event page', async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: MEMBER_STATE })
    const member = await ctx.newPage()
    try {
      await member.goto('/app/events/create')
      // Should redirect away since it requires admin role
      await expect(member).not.toHaveURL(/\/app\/events\/create/, { timeout: 5000 })
    } finally {
      await ctx.close()
    }
  })
})

// ── member viewing ───────────────────────────────────────────────────────────

test.describe('Member – events viewing', () => {
  test('member can see published events', async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: MEMBER_STATE })
    const member = await ctx.newPage()
    try {
      await member.goto('/app/events')
      await expect(member.getByText(created.event.name)).toBeVisible()
    } finally {
      await ctx.close()
    }
  })

  test('member can view event detail', async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: MEMBER_STATE })
    const member = await ctx.newPage()
    try {
      await member.goto(`/app/events/${created.event.id}`)
      await expect(member.getByRole('heading', { name: created.event.name })).toBeVisible()
      // Slots should be visible
      await expect(member.getByText(/0\/5/).first()).toBeVisible()
    } finally {
      await ctx.close()
    }
  })

  test('member can book a slot', async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: MEMBER_STATE })
    const member = await ctx.newPage()
    try {
      await member.goto(`/app/events/${created.event.id}`)
      await expect(member.getByText(/0\/5/).first()).toBeVisible()
      await member.getByText(/0\/5/).first().click()
      await expect(member.getByText(/1\/5/).first()).toBeVisible({ timeout: 5000 })
    } finally {
      await ctx.close()
    }
  })
})
