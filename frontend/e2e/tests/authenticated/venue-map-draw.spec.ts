/**
 * E2E tests for drawing a venue map in the app (#185 phase 2): event settings
 * → "Map" tab → a blank plan, then rectangles, shapes, lines and texts, with
 * undo/redo, deleting, and a reload to prove it all persisted.
 *
 * Runs as a disposable organiser in an event of their own (see e2e/CLAUDE.md):
 * the sidebar's "Map" entry follows the selected event's `venue_plan_count`.
 *
 * Every gesture is checked through the API: the editor applies edits
 * optimistically, so only a read-back proves the batch went out.
 */
import type { Locator, Page } from '@playwright/test'

import { expect, test } from '../../fixtures.js'
import {
  type EventRead,
  type LocationRead,
  api,
  batchShapes,
  createEvent,
  createLocation,
  createVenuePlan,
  deleteEvent,
  futureDate,
  getPlanShapes,
  setSelectedEvent,
  uniqueName,
} from '../../helpers/api.js'

let event: EventRead
let location: LocationRead

/** The grid of a 1600×1000 canvas: 1% of the shorter side per axis. */
const GRID = { gx: 10 / 1600, gy: 10 / 1000 }

async function planId(page: Page): Promise<string> {
  const map = await api<{ plans: { id: string }[] }>(page, 'GET', `/events/${event.id}/venue-map`)
  return map.plans[0]!.id
}

/** The page point at a fraction of the canvas box, scrolled into view first. */
async function at(canvas: Locator, fx: number, fy: number) {
  // `mouse` works in viewport coordinates and never scrolls by itself.
  await canvas.scrollIntoViewIfNeeded()
  const box = await canvas.boundingBox()
  if (!box) throw new Error('editor canvas has no box')
  return { x: box.x + box.width * fx, y: box.y + box.height * fy }
}

/** Resolves once the next shape batch has been answered. */
function nextBatch(page: Page) {
  return page.waitForResponse(
    (r) => r.url().includes('/shapes/batch') && r.request().method() === 'POST',
  )
}

function onGrid(value: number, step: number) {
  return Math.abs(value / step - Math.round(value / step)) < 1e-6 / step
}

test.beforeEach(async ({ disposablePage: page }) => {
  event = await createEvent(page, uniqueName('E2E Map Draw'), 'published', 'private', {
    start: futureDate(1),
    end: futureDate(3),
  })
  await setSelectedEvent(page, event.id)
  location = await createLocation(page, event.id, { name: 'Bühne' })
})

test.afterEach(async ({ disposablePage: page }) => {
  await deleteEvent(page, event.id).catch(() => {})
})

test.describe('Drawing a venue map', () => {
  test('draw, label, link, undo, redo, delete — and it persists', async ({
    disposablePage: page,
  }) => {
    await page.goto(`/app/event-settings/${event.id}?tab=map`)
    const editor = page.getByTestId('venue-map-editor')

    // ── A blank landscape plan ──
    await editor.getByTestId('plan-add').click()
    await page.getByTestId('plan-name-input').fill('Gelände')
    await page.getByTestId('plan-aspect-landscape').click()
    await page.getByTestId('plan-name-save').click()
    const canvas = editor.getByTestId('editor-canvas')
    await expect(canvas).toBeVisible()
    await expect(editor.getByTestId('tool-rect')).toHaveAttribute('aria-pressed', 'true')
    await expect(editor.getByTestId('draw-hint')).toBeVisible()
    // The dialog is gone (a modal dialog blocks pointer events until it is).
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page.locator('body')).not.toHaveCSS('pointer-events', 'none')
    const id = await planId(page)

    // ── A rectangle by dragging ──
    const a = await at(canvas, 0.15, 0.2)
    const b = await at(canvas, 0.4, 0.55)
    let saved = nextBatch(page)
    await page.mouse.move(a.x, a.y)
    await page.mouse.down()
    await page.mouse.move((a.x + b.x) / 2, (a.y + b.y) / 2, { steps: 5 })
    await page.mouse.move(b.x, b.y, { steps: 5 })
    await page.mouse.up()
    expect((await saved).ok()).toBe(true)
    await expect(editor.getByTestId('shape-inspector')).toBeVisible()

    // Style, label and link, each its own saved step.
    saved = nextBatch(page)
    await editor.getByTestId('style-stage').click()
    await saved
    saved = nextBatch(page)
    await editor.getByTestId('shape-label').fill('Bühne')
    await editor.getByTestId('shape-label').press('Enter')
    await saved
    saved = nextBatch(page)
    await editor.getByTestId('shape-link').selectOption(location.id)
    await saved

    let { shapes } = await getPlanShapes(page, id)
    expect(shapes).toHaveLength(1)
    const rect = shapes[0]!
    expect(rect).toMatchObject({
      kind: 'rect',
      style: 'stage',
      label: 'Bühne',
      location_id: location.id,
    })
    for (const [x, y] of rect.points) {
      expect(onGrid(x!, GRID.gx), `x ${x}`).toBe(true)
      expect(onGrid(y!, GRID.gy), `y ${y}`).toBe(true)
    }
    // The first drawing makes the map count: the nav shows "Map".
    await expect(page.getByTestId('sidebar-link-event-map')).toBeVisible()

    // ── A shape (polygon) by four clicks and Enter ──
    await editor.getByTestId('tool-polygon').click()
    for (const [fx, fy] of [
      [0.6, 0.2],
      [0.85, 0.2],
      [0.85, 0.45],
      [0.6, 0.45],
    ] as const) {
      const p = await at(canvas, fx, fy)
      await page.mouse.click(p.x, p.y)
    }
    saved = nextBatch(page)
    await page.keyboard.press('Enter')
    await saved

    // ── A line by three clicks, the last a double click ──
    await editor.getByTestId('tool-path').click()
    const l1 = await at(canvas, 0.1, 0.75)
    const l2 = await at(canvas, 0.4, 0.8)
    const l3 = await at(canvas, 0.7, 0.75)
    await page.mouse.click(l1.x, l1.y)
    await page.mouse.click(l2.x, l2.y)
    saved = nextBatch(page)
    await page.mouse.dblclick(l3.x, l3.y)
    await saved

    // ── A text by a click and typing ──
    await editor.getByTestId('tool-label').click()
    const t = await at(canvas, 0.5, 0.65)
    await page.mouse.click(t.x, t.y)
    const text = editor.getByTestId('label-draft-input')
    await expect(text).toBeFocused()
    saved = nextBatch(page)
    await text.fill('Kasse')
    await text.press('Enter')
    await saved

    ;({ shapes } = await getPlanShapes(page, id))
    expect(shapes.map((s) => s.kind).sort()).toEqual(['label', 'path', 'polygon', 'rect'])
    expect(shapes.find((s) => s.kind === 'polygon')!.points).toHaveLength(4)
    expect(shapes.find((s) => s.kind === 'path')!.points).toHaveLength(3)
    const label = shapes.find((s) => s.kind === 'label')!
    expect(label.label).toBe('Kasse')

    // ── Undo removes the text, redo brings it back under the same id ──
    await editor.getByTestId('tool-select').click()
    saved = nextBatch(page)
    await page.keyboard.press('Control+z')
    await saved
    ;({ shapes } = await getPlanShapes(page, id))
    expect(shapes).toHaveLength(3)
    expect(shapes.some((s) => s.id === label.id)).toBe(false)

    saved = nextBatch(page)
    await page.keyboard.press('Control+Shift+z')
    await saved
    ;({ shapes } = await getPlanShapes(page, id))
    expect(shapes).toHaveLength(4)
    expect(shapes.find((s) => s.kind === 'label')!.id).toBe(label.id)

    // ── Delete the rectangle with the Delete key ──
    const r = await at(canvas, 0.2, 0.3)
    await page.mouse.click(r.x, r.y)
    await expect(editor.getByTestId('shape-inspector')).toBeVisible()
    saved = nextBatch(page)
    await page.keyboard.press('Delete')
    await saved
    ;({ shapes } = await getPlanShapes(page, id))
    expect(shapes).toHaveLength(3)
    expect(shapes.some((s) => s.id === rect.id)).toBe(false)

    // ── It all survives a reload ──
    await page.reload()
    await expect(page.getByTestId('editor-canvas')).toBeVisible()
    for (const s of shapes) {
      await expect(page.getByTestId(`venue-shape-${s.id}`)).toHaveCount(1)
    }
    await expect(page.getByTestId(`venue-shape-${rect.id}`)).toHaveCount(0)
  })

  test('edit in place on the map page: the second plan, a new corner, back to the map', async ({
    disposablePage: page,
  }) => {
    // Two drawn plans (an empty one is no map yet); the area to edit is on the second.
    const first = await createVenuePlan(page, event.id, { name: 'Halle' })
    await batchShapes(page, first.id, [
      {
        op: 'create',
        shape: {
          kind: 'rect',
          style: 'building',
          points: [
            [0.1, 0.1],
            [0.9, 0.9],
          ],
        },
      },
    ])
    const plan = await createVenuePlan(page, event.id, { name: 'Wiese', canvas: 'square' })
    const { shapes: seededShapes } = await batchShapes(page, plan.id, [
      {
        op: 'create',
        shape: {
          kind: 'polygon',
          style: 'green',
          points: [
            [0.2, 0.2],
            [0.8, 0.2],
            [0.8, 0.8],
            [0.2, 0.8],
          ],
          label: 'Spielwiese',
          location_id: location.id,
        },
      },
    ])
    const area = seededShapes[0]!

    await page.goto(`/app/map/${event.id}`)
    await page.getByTestId('plan-switcher').getByText('Wiese', { exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`plan=${plan.id}`))

    // The editor opens on the plan the map was showing.
    await page.getByTestId('map-edit').click()
    const editor = page.getByTestId('venue-map-editor')
    await expect(editor.getByTestId(`venue-shape-${area.id}`)).toBeVisible()

    // Select the area, then pull the "+" on its top edge out into a new corner.
    await editor.getByTestId('tool-select').click()
    const box = (await editor.getByTestId(`venue-shape-${area.id}`).boundingBox())!
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
    await expect(editor.getByTestId('shape-inspector')).toBeVisible()
    await expect(editor.locator('[data-handle^="vertex:"]')).toHaveCount(4)

    const plus = (await editor.locator('[data-handle="insert:0"]').boundingBox())!
    const from = { x: plus.x + plus.width / 2, y: plus.y + plus.height / 2 }
    const saved = nextBatch(page)
    await page.mouse.move(from.x, from.y)
    await page.mouse.down()
    await page.mouse.move(from.x, from.y - 20, { steps: 4 })
    await page.mouse.move(from.x, from.y - 40, { steps: 4 })
    await page.mouse.up()
    expect((await saved).ok()).toBe(true)
    // The handle under the pointer became a corner; the area stays selected.
    await expect(editor.getByTestId('shape-inspector')).toBeVisible()
    await expect(editor.locator('[data-handle^="vertex:"]')).toHaveCount(5)

    const { shapes } = await getPlanShapes(page, plan.id)
    const edited = shapes.find((s) => s.id === area.id)!
    expect(edited.points).toHaveLength(5)
    // Pulled upwards, onto the grid.
    expect(edited.points[1]![1]).toBeLessThan(0.2)

    // "Done" comes back to the same plan, not the first one.
    await page.getByTestId('map-edit-done').click()
    await expect(editor).toHaveCount(0)
    await expect(page).toHaveURL(new RegExp(`plan=${plan.id}`))
    const drawn = page.getByTestId(`venue-shape-${area.id}`)
    await expect(drawn).toBeVisible()

    // Tapping the linked area opens its place.
    const viewBox = (await drawn.boundingBox())!
    await page.mouse.click(viewBox.x + viewBox.width * 0.3, viewBox.y + viewBox.height * 0.7)
    await expect(page).toHaveURL(new RegExp(`location=${location.id}`))
  })
})
