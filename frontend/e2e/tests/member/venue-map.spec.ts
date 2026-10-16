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
  type LocationRead,
  type MappedEvent,
  addMember,
  apiStatus,
  batchShapes,
  createEvent,
  createLocation,
  createVenuePlan,
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
    // A helper reads the map but cannot edit it.
    await expect(page.getByTestId('map-edit')).toHaveCount(0)
    // The map fills the window: the page itself never scrolls.
    await expect
      .poll(() => page.evaluate(() => document.scrollingElement!.scrollHeight - window.innerHeight))
      .toBeLessThanOrEqual(0)
    // Nothing booked yet, so nothing is highlighted.
    await expect(pin.getByTestId('marker-highlight')).toHaveCount(0)
    // Hovering a pin names it in the app's tooltip (no native title).
    await pin.hover()
    await expect(page.getByTestId('map-pin-hint')).toContainText(location.name)
    await expect(pin.locator('title')).toHaveCount(0)

    await pin.click()
    await expect(page.getByTestId('map-pin-hint')).toHaveCount(0)
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

test.describe('Venue map – a drawn plan', () => {
  let drawn: { event: EventRead; location: LocationRead; shapeId: string }

  test.beforeEach(async ({ adminPage, disposablePage, disposableUser }) => {
    const event = await createEvent(
      adminPage,
      uniqueName('E2E Drawn Map'),
      'published',
      'private',
      {
        start: futureDate(1),
        end: futureDate(2),
      },
    )
    const location = await createLocation(adminPage, event.id, { name: uniqueName('Main Hall') })
    // A blank canvas with one room linked to the place, and no marker for it.
    const plan = await createVenuePlan(adminPage, event.id, { name: 'Building' })
    const { shapes } = await batchShapes(
      adminPage,
      plan.id,
      [
        {
          op: 'create',
          shape: {
            kind: 'rect',
            style: 'room',
            points: [
              [0.2, 0.2],
              [0.8, 0.8],
            ],
            label: 'Hall',
            location_id: location.id,
          },
        },
      ],
      0,
    )
    drawn = { event, location, shapeId: shapes[0]!.id }
    await addMember(adminPage, disposablePage, event.id, disposableUser.email)
    await setSelectedEvent(disposablePage, event.id)
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteEvent(adminPage, drawn.event.id).catch(() => {})
  })

  test('a room drawn for a place gets a pill and opens the place', async ({
    disposablePage: page,
  }) => {
    const { event, location, shapeId } = drawn
    await page.goto(`/app/map/${event.id}`)

    // A drawing alone makes it a map: the nav entry is there.
    await expect(page.getByTestId('sidebar-link-event-map')).toBeVisible()
    const room = page.getByTestId(`venue-shape-${shapeId}`)
    await expect(room).toBeVisible()
    // The place has no marker, so its area carries a pill of its own.
    await expect(page.getByTestId(`map-marker-${location.id}`)).toBeVisible()

    // Tap the room away from its pill (which sits in the middle).
    await room.locator('.vs-body').click({ position: { x: 12, y: 12 } })
    await expect(page.getByTestId('location-sheet-title')).toHaveText(location.name)
    await expect(room).toHaveAttribute('data-selected-location', 'true')
  })

  test('the drawing and the pills follow the dark theme', async ({ disposablePage: page }) => {
    const { event, location, shapeId } = drawn
    const body = page.getByTestId(`venue-shape-${shapeId}`).locator('.vs-body')
    const name = page.getByTestId(`map-marker-${location.id}`).getByTestId('marker-name')
    const fill = (el: Element) => getComputedStyle(el).fill

    await page.emulateMedia({ colorScheme: 'light' })
    await page.goto(`/app/map/${event.id}`)
    await expect(body).toBeVisible()
    const lightFill = await body.evaluate(fill)

    await page.emulateMedia({ colorScheme: 'dark' })
    await page.reload()
    await expect(body).toBeVisible()
    await expect.poll(() => body.evaluate(fill)).not.toBe(lightFill)
    // Pill text turns light on the dark pill (OKLab lightness above 0.8).
    const lightness = await name.evaluate((el) => {
      const ctx = document.createElement('canvas').getContext('2d')!
      ctx.fillStyle = getComputedStyle(el).fill
      ctx.fillRect(0, 0, 1, 1)
      const [r, g, b] = [...ctx.getImageData(0, 0, 1, 1).data].map((v) => {
        const c = v / 255
        return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
      }) as [number, number, number]
      const l = Math.cbrt(0.4122214708 * r + 0.5363015195 * g + 0.0514459929 * b)
      const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
      const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
      return 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s
    })
    expect(lightness).toBeGreaterThan(0.8)
  })
})
