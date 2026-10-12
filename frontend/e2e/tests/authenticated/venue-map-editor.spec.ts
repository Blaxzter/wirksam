/**
 * E2E tests for the venue map editor (#185): event settings → "Map" tab.
 *
 * Runs as a disposable organiser in an event of their own, selected, because
 * the sidebar's "Map" entry follows the selected event's `venue_plan_count`
 * and the shared `adminUser` must not be repointed (see e2e/CLAUDE.md).
 *
 * Pins are checked through the API after each gesture: the editor updates its
 * own copy optimistically, so only a read-back proves the request went out.
 */
import type { Locator, Page } from '@playwright/test'

import { expect, test } from '../../fixtures.js'
import {
  type EventRead,
  FLOORPLAN_PATH,
  type LocationRead,
  type VenueMarkerRead,
  api,
  createEvent,
  createLocation,
  deleteEvent,
  futureDate,
  setSelectedEvent,
  uniqueName,
} from '../../helpers/api.js'

let event: EventRead
let location: LocationRead

async function readMarkers(page: Page): Promise<VenueMarkerRead[]> {
  const map = await api<{ plans: { markers?: VenueMarkerRead[] }[] }>(
    page,
    'GET',
    `/events/${event.id}/venue-map`,
  )
  return map.plans.flatMap((p) => p.markers ?? [])
}

/** Click the plan at a fraction of its box (clear of the zoom buttons and banner). */
async function clickCanvasAt(canvas: Locator, fx: number, fy: number) {
  const box = await canvas.boundingBox()
  if (!box) throw new Error('editor canvas has no box')
  await canvas.page().mouse.click(box.x + box.width * fx, box.y + box.height * fy)
}

test.beforeEach(async ({ disposablePage: page }) => {
  event = await createEvent(page, uniqueName('E2E Map Editor'), 'published', 'private', {
    start: futureDate(1),
    end: futureDate(3),
  })
  await setSelectedEvent(page, event.id)
  location = await createLocation(page, event.id, { name: 'Main Stage' })
})

test.afterEach(async ({ disposablePage: page }) => {
  await deleteEvent(page, event.id).catch(() => {})
})

test.describe('Venue map editor', () => {
  test('add a plan, upload a picture, place and drag pins', async ({ disposablePage: page }) => {
    await page.goto(`/app/event-settings/${event.id}?tab=map`)
    const editor = page.getByTestId('venue-map-editor')
    // No plan with a picture yet, so the nav has no "Map" entry.
    await expect(editor.getByTestId('map-editor-empty')).toBeVisible()
    await expect(page.getByTestId('sidebar-link-event-map')).toHaveCount(0)

    // ── Add a plan ──
    await editor.getByTestId('plan-add').click()
    await page.getByTestId('plan-name-input').fill('Grounds')
    await page.getByTestId('plan-name-save').click()
    await expect(editor.getByTestId('plan-upload-zone')).toBeVisible()
    // A plan without a picture still does not count.
    await expect(page.getByTestId('sidebar-link-event-map')).toHaveCount(0)

    // ── Upload the picture ──
    await editor.getByTestId('plan-upload-input').first().setInputFiles(FLOORPLAN_PATH)
    const canvas = editor.getByTestId('editor-canvas')
    await expect(canvas).toBeVisible()
    await expect(canvas.locator('image')).toHaveAttribute('href', /^blob:/)
    await expect(canvas).not.toHaveAttribute('aria-busy', 'true')
    await expect(page.getByTestId('sidebar-link-event-map')).toBeVisible()

    // ── Place the location by clicking on the plan ──
    await editor.getByTestId(`palette-location-${location.id}`).click()
    await expect(editor.getByTestId('placement-banner')).toContainText('Main Stage')
    await clickCanvasAt(canvas, 0.3, 0.5)
    const pin = canvas.getByTestId(`map-marker-${location.id}`)
    await expect(pin).toBeVisible()
    await expect(editor.getByTestId('placement-banner')).toHaveCount(0)
    // Placed locations leave the palette.
    await expect(editor.getByTestId(`palette-location-${location.id}`)).toHaveCount(0)

    const [placed] = await readMarkers(page)
    expect(placed.location_id).toBe(location.id)
    expect(placed.kind).toBe('location')

    // ── Drag it ──
    const box = (await pin.boundingBox())!
    const from = { x: box.x + box.width / 2, y: box.y + box.height / 2 }
    const saved = page.waitForResponse(
      (r) => r.url().includes(`/venue-markers/${placed.id}`) && r.request().method() === 'PATCH',
    )
    await page.mouse.move(from.x, from.y)
    await page.mouse.down()
    await page.mouse.move(from.x + 60, from.y - 40, { steps: 8 })
    await page.mouse.move(from.x + 120, from.y - 80, { steps: 8 })
    await page.mouse.up()
    expect((await saved).ok()).toBe(true)

    const [moved] = await readMarkers(page)
    expect(moved.id).toBe(placed.id)
    expect(moved.x).toBeGreaterThan(placed.x)
    expect(moved.y).toBeLessThan(placed.y)

    // ── A generic pin ──
    await editor.getByTestId('palette-kind-first_aid').click()
    await expect(editor.getByTestId('placement-banner')).toBeVisible()
    await clickCanvasAt(canvas, 0.7, 0.6)
    await expect(editor.getByTestId('marker-panel')).toBeVisible()
    await expect(editor.getByTestId('marker-kind')).toHaveValue('first_aid')

    const markers = await readMarkers(page)
    expect(markers).toHaveLength(2)
    const firstAid = markers.find((m) => m.kind === 'first_aid')
    expect(firstAid?.location_id).toBeNull()
    expect(firstAid?.x).toBeGreaterThan(0.5)
  })
})
