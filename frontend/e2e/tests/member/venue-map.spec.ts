/**
 * E2E tests for the venue map as a helper sees it (#185): `/app/map/:eventId`.
 *
 * The worker admin seeds an event of its own; a disposable participant joins
 * it, because joining, selecting the event and booking are all mutations the
 * shared `memberUser` must not carry into later tests (see e2e/CLAUDE.md).
 */
import { expect, test } from '../../fixtures.js'
import {
  type EventRead,
  type MappedEvent,
  addMember,
  apiStatus,
  createEvent,
  deleteEvent,
  deleteTask,
  futureDate,
  seedMappedEvent,
  setSelectedEvent,
  uniqueName,
} from '../../helpers/api.js'

let seeded: MappedEvent

test.beforeEach(async ({ adminPage, disposablePage, disposableUser }) => {
  seeded = await seedMappedEvent(adminPage)
  await addMember(adminPage, disposablePage, seeded.event.id, disposableUser.email)
  await setSelectedEvent(disposablePage, seeded.event.id)
})

test.afterEach(async ({ adminPage }) => {
  // Takes the booking made below with it.
  await deleteTask(adminPage, seeded.task.id).catch(() => {})
  await deleteEvent(adminPage, seeded.event.id).catch(() => {})
})

test.describe('Venue map – helper view', () => {
  test('tap a pin, read the place, book a shift there', async ({ disposablePage: page }) => {
    const { location, shift, task } = seeded

    await page.goto('/app/home')
    await page.getByTestId('sidebar-link-event-map').click()
    await expect(page).toHaveURL(/\/app\/map/)

    const pin = page.getByTestId(`map-marker-${location.id}`)
    await expect(pin).toBeVisible()
    // Nothing booked yet, so nothing is highlighted.
    await expect(pin.getByTestId('marker-highlight')).toHaveCount(0)

    await pin.click()
    const sheet = page.getByTestId('location-sheet')
    await expect(sheet.getByTestId('location-sheet-title')).toHaveText(location.name)
    await expect(sheet.getByTestId('location-description-body').locator('strong')).toHaveText(
      'back door',
    )
    await expect(sheet.getByTestId(`sheet-shift-${shift.id}`)).toContainText(task.name)
    await expect(page).toHaveURL(new RegExp(`location=${location.id}`))

    await sheet.getByTestId(`sheet-book-${shift.id}`).click()
    await expect(sheet.getByTestId(`sheet-booked-${shift.id}`)).toBeVisible()
    await expect(sheet.getByTestId(`sheet-book-${shift.id}`)).toHaveCount(0)

    // Closing the sheet drops `?location=` again.
    await page.keyboard.press('Escape')
    await expect(sheet).toBeHidden()
    await expect(page).not.toHaveURL(/location=/)

    // The place of a booked shift is ringed — unless "My shifts" is off.
    await expect(pin.getByTestId('marker-highlight')).toBeVisible()
    await page.getByTestId('map-my-shifts').click()
    await expect(pin.getByTestId('marker-highlight')).toHaveCount(0)
  })

  test('search finds a place and zooms to it', async ({ disposablePage: page }) => {
    const { event, location } = seeded

    await page.goto(`/app/map/${event.id}`)
    // The plan's own <svg>, not the icons nested inside its pins.
    const svg = page.getByTestId('venue-map-canvas').locator(':scope > svg')
    await expect(page.getByTestId(`map-marker-${location.id}`)).toBeVisible()
    const width = async () => Number(((await svg.getAttribute('viewBox')) ?? '').split(/\s+/)[2])
    const fittedWidth = await width()

    await page.getByTestId('map-search').fill(location.name.slice(0, 8))
    await page.getByTestId(`map-search-result-location-${location.id}`).click()

    await expect(page.getByTestId('location-sheet-title')).toHaveText(location.name)
    // Focused at 3×: the view box shrinks to a third of the fitted width.
    await expect.poll(width).toBeLessThan(fittedWidth / 2)
  })

  test('a deep link opens the place’s sheet', async ({ disposablePage: page }) => {
    const { event, location, plan } = seeded
    await page.goto(`/app/map/${event.id}?plan=${plan.id}&location=${location.id}`)
    await expect(page.getByTestId('location-sheet-title')).toHaveText(location.name)
  })
})

test.describe('Venue map – nothing to show', () => {
  let empty: EventRead

  test.beforeEach(async ({ adminPage, disposablePage, disposableUser }) => {
    empty = await createEvent(adminPage, uniqueName('E2E No Map'), 'published', 'private', {
      start: futureDate(1),
      end: futureDate(2),
    })
    await addMember(adminPage, disposablePage, empty.id, disposableUser.email)
    await setSelectedEvent(disposablePage, empty.id)
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteEvent(adminPage, empty.id).catch(() => {})
  })

  test('an event without plans shows the empty state and no nav entry', async ({
    disposablePage: page,
  }) => {
    await page.goto(`/app/map/${empty.id}`)
    await expect(page.getByTestId('map-empty')).toBeVisible()
    // Only organisers are sent to the editor.
    await expect(page.getByTestId('map-go-to-editor')).toHaveCount(0)
    await expect(page.getByTestId('sidebar-link-event-map')).toHaveCount(0)
  })

  test('someone outside the event cannot read its map', async ({ memberPage }) => {
    // 404, not 403: a private event must not be probed by id.
    expect(await apiStatus(memberPage, 'GET', `/events/${seeded.event.id}/venue-map`)).toBe(404)
  })
})
