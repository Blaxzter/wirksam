/**
 * E2E tests for event locations (#182): managed in the event settings, picked
 * on the task forms, shown on task and shift details, and used as a feed filter.
 *
 * Every test runs as a disposable organiser in an event of its own. The feed
 * and the task form follow the *selected* event, and repointing the shared
 * `adminUser` at a throwaway event would poison every later test in the worker
 * (see e2e/CLAUDE.md), so the disposable account selects its own event instead.
 */
import type { Page } from '@playwright/test'

import { expect, test } from '../../fixtures.js'
import {
  type EventRead,
  type LocationRead,
  createEvent,
  createLocation,
  createTaskWithShifts,
  deleteEvent,
  deleteTask,
  futureDate,
  listShifts,
  setSelectedEvent,
  uniqueName,
} from '../../helpers/api.js'

let event: EventRead
const taskIds: string[] = []

/** Create an event starting tomorrow and make it the organiser's selected one. */
async function setUpOwnEvent(page: Page): Promise<EventRead> {
  const created = await createEvent(page, uniqueName('E2E Locations'), 'published', 'private', {
    start: futureDate(1),
    end: futureDate(5),
  })
  await setSelectedEvent(page, created.id)
  return created
}

async function createLocatedTask(page: Page, name: string, locationId?: string) {
  const created = await createTaskWithShifts(page, {
    name,
    eventId: event.id,
    status: 'published',
    locationId,
    startDate: futureDate(1),
    endDate: futureDate(1),
    startTime: '10:00',
    endTime: '11:00',
    slotDuration: 60,
  })
  taskIds.push(created.task.id)
  return created
}

test.beforeEach(async ({ disposablePage: page }) => {
  event = await setUpOwnEvent(page)
})

test.afterEach(async ({ disposablePage: page }) => {
  // Tasks outlive their event (the FK is SET NULL), so they go first.
  for (const id of taskIds.splice(0)) await deleteTask(page, id).catch(() => {})
  await deleteEvent(page, event.id).catch(() => {})
})

test.describe('Locations – event settings', () => {
  test('an organiser adds a location with a Markdown description', async ({
    disposablePage: page,
  }) => {
    await page.goto(`/app/event-settings/${event.id}?tab=locations`)
    const section = page.getByTestId('section-event-locations')
    await expect(section.getByTestId('locations-empty')).toBeVisible()

    await section.getByTestId('btn-add-location').click()
    const dialog = page.getByTestId('location-form-dialog')
    await dialog.getByTestId('location-form-name').fill('Main Stage')
    await dialog
      .getByTestId('location-form-description')
      .fill('Behind the **big tent**, next to the bar.')
    await dialog.getByTestId('location-form-address').fill('Festival Road 1')
    await dialog.getByTestId('location-form-save').click()
    await expect(dialog).toBeHidden()

    const row = section.locator('[data-testid^="location-row-"]').filter({ hasText: 'Main Stage' })
    await expect(row).toHaveCount(1)
    await expect(section.getByTestId('locations-empty')).toHaveCount(0)
  })

  test('the task form offers the event’s locations', async ({ disposablePage: page }) => {
    const location = await createLocation(page, event.id, { name: 'Ticket Booth' })

    // `?eventId=` preselects the event, which is what makes its locations
    // available to the picker.
    await page.goto(`/app/tasks/create?eventId=${event.id}`)
    const picker = page.getByTestId('location-picker')
    await picker.click()
    await page.getByTestId(`location-option-${location.id}`).click()
    await expect(picker).toContainText('Ticket Booth')
    await expect(page.getByTestId('location-custom-input')).toHaveCount(0)

    // "Other" switches to free text and keeps the name as a starting point.
    await picker.click()
    await page.getByTestId('location-option-custom').click()
    await expect(page.getByTestId('location-custom-input')).toHaveValue('Ticket Booth')
  })
})

test.describe('Locations – where they show up', () => {
  let location: LocationRead

  test.beforeEach(async ({ disposablePage: page }) => {
    location = await createLocation(page, event.id, {
      name: uniqueName('Info Point'),
      description: 'Ask for **Anna** at the counter.',
      contact: 'Anna, 0123 456',
    })
  })

  test('task details show the linked location', async ({ disposablePage: page }) => {
    const { task } = await createLocatedTask(page, uniqueName('E2E Located Task'), location.id)
    expect(task.location_id).toBe(location.id)
    expect(task.location).toBe(location.name)

    await page.goto(`/app/tasks/${task.id}`)
    await expect(page.getByTestId('page-heading')).toContainText(task.name)
    await expect(page.getByText(location.name).first()).toBeVisible()
    // No plan yet, so no mini-map — but an organiser gets the details link.
    await expect(page.getByTestId('btn-task-location-details')).toBeVisible()
  })

  test('the feed filter narrows the list to one location', async ({ disposablePage: page }) => {
    const here = await createLocatedTask(page, uniqueName('E2E Filter Here'), location.id)
    const elsewhere = await createLocatedTask(page, uniqueName('E2E Filter Elsewhere'))

    await page.goto('/app/tasks?view=list')
    const content = page.getByTestId('main-content')
    await expect(content.getByText(here.task.name)).toBeVisible()
    await expect(content.getByText(elsewhere.task.name)).toBeVisible()

    await page.getByRole('button', { name: /filters/i }).click()
    await page.getByTestId('filter-location').click()
    await page.getByTestId(`filter-location-option-${location.id}`).click()

    await expect(page).toHaveURL(new RegExp(`location=${location.id}`))
    await expect(content.getByText(here.task.name)).toBeVisible()
    await expect(content.getByText(elsewhere.task.name)).toBeHidden()
  })

  test('shift details render the location’s description', async ({ disposablePage: page }) => {
    const { task } = await createLocatedTask(page, uniqueName('E2E Shift Location'), location.id)
    const [shift] = await listShifts(page, task.id)
    expect(shift.location_id).toBe(location.id)

    await page.goto(`/app/tasks?view=list&search=${encodeURIComponent(task.name)}`)
    await page.getByTestId(`shift-chip-${shift.id}`).click()

    const details = page.getByTestId('dialog-shift-detail').getByTestId('shift-location-details')
    await expect(details).toBeVisible()
    // Short descriptions start open; the Markdown is rendered, not shown raw.
    const body = details.getByTestId('location-description-body')
    await expect(body.locator('strong')).toHaveText('Anna')
    await expect(body).not.toContainText('**')
    await expect(details).toContainText('Anna, 0123 456')
    // No plan with a pin, so no mini-map.
    await expect(page.getByTestId('shift-mini-map')).toHaveCount(0)
  })
})
