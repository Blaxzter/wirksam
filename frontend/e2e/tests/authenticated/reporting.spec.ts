/**
 * E2E tests for Admin Reporting page.
 */

import { test, expect } from '../../fixtures.js'
import {
  uniqueName,
  createEventWithSlots,
  publishEvent,
  listSlots,
  bookSlot,
  deleteEvent,
  type EventWithSlots,
} from '../../helpers/api.js'

test.describe('Reporting – navigation', () => {
  test('can navigate to reporting page via URL', async ({ adminPage: page }) => {
    await page.goto('/app/admin/reporting')
    await expect(page).toHaveURL(/\/app\/admin\/reporting/)
  })

  test('sidebar shows reporting link for admin', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('sidebar-link-admin-reporting')).toBeVisible()
  })
})

test.describe('Reporting – page structure', () => {
  let created: EventWithSlots

  test.beforeEach(async ({ adminPage: page }) => {
    created = await createEventWithSlots(page, { name: uniqueName('Report') })
    await publishEvent(page, created.event.id)
    const slots = await listSlots(page, created.event.id)
    await bookSlot(page, slots[0].id)
  })

  test.afterEach(async ({ adminPage: page }) => {
    await deleteEvent(page, created?.event?.id).catch(() => {})
  })

  test('shows page heading', async ({ adminPage: page }) => {
    await page.goto('/app/admin/reporting')
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('shows overview section', async ({ adminPage: page }) => {
    await page.goto('/app/admin/reporting')
    await expect(page.getByTestId('section-overview')).toBeVisible()
  })

  test('shows export button', async ({ adminPage: page }) => {
    await page.goto('/app/admin/reporting')
    await expect(page.getByTestId('btn-export')).toBeVisible()
  })

  test('shows charts with booking data', async ({ adminPage: page }) => {
    await page.goto('/app/admin/reporting')
    await expect(page.getByTestId('section-charts')).toBeVisible()
  })
})

test.describe('Reporting – member RBAC', () => {
  test('member cannot access reporting page', async ({ memberPage: member }) => {
    await member.goto('/app/admin/reporting')
    // Should redirect away
    await expect(member).not.toHaveURL(/\/app\/admin\/reporting/)
  })
})
