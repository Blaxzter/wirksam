/**
 * The venue map on a phone (Pixel 7): reached from the user menu, since the
 * bottom nav has no room for it, and a tapped place opens as a bottom sheet.
 *
 * Same seeding as `member/venue-map.spec.ts`: the worker admin owns the event
 * and a disposable participant joins and selects it.
 */
import { expect, test } from '../../fixtures.js'
import {
  type MappedEvent,
  addMember,
  api,
  batchShapes,
  createVenuePlan,
  deleteEvent,
  deleteTask,
  getPlanShapes,
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
  await deleteTask(adminPage, seeded.task.id).catch(() => {})
  await deleteEvent(adminPage, seeded.event.id).catch(() => {})
})

test.describe('Venue map – on a phone', () => {
  test('the user menu leads to the map', async ({ disposablePage: page }) => {
    expect(page.viewportSize()?.width).toBeLessThan(768)

    await page.goto('/app/home')
    await page.getByTestId('mobile-user-menu').click()
    await page.getByTestId('mobile-user-venue-map').click()

    await expect(page).toHaveURL(/\/app\/map/)
    await expect(page.getByTestId(`map-marker-${seeded.location.id}`)).toBeVisible()
  })

  test('a tapped place opens as a bottom sheet', async ({ disposablePage: page }) => {
    await page.goto(`/app/map/${seeded.event.id}`)
    await expect(page.getByTestId(`map-marker-${seeded.location.id}`)).toBeVisible()
    // The map fills the screen: the page itself never scrolls.
    await expect
      .poll(() => page.evaluate(() => document.scrollingElement!.scrollHeight - window.innerHeight))
      .toBeLessThanOrEqual(0)
    await page.getByTestId(`map-marker-${seeded.location.id}`).tap()

    const sheet = page.getByTestId('location-sheet')
    await expect(sheet).toHaveAttribute('data-slot', 'drawer-content')
    await expect(sheet.getByTestId('location-sheet-title')).toHaveText(seeded.location.name)
    await expect(sheet.getByTestId(`sheet-book-${seeded.shift.id}`)).toBeVisible()

    // Wait out the slide-up, then check it is a full-width sheet on the bottom edge.
    const viewport = page.viewportSize()!
    await expect
      .poll(async () => {
        const box = await sheet.boundingBox()
        return box ? Math.round(box.y + box.height) : null
      })
      .toBe(viewport.height)
    const box = (await sheet.boundingBox())!
    expect(Math.round(box.x)).toBe(0)
    expect(Math.round(box.width)).toBe(viewport.width)
  })

  test('an organiser draws a shape by tapping, finished with "Close shape"', async ({
    adminPage: page,
  }) => {
    // The worker admin owns this (per-test) event; a blank plan of its own.
    const plan = await createVenuePlan(page, seeded.event.id, { name: 'Skizze', canvas: 'square' })
    await page.goto(`/app/event-settings/${seeded.event.id}?tab=map`)
    const editor = page.getByTestId('venue-map-editor')
    // Plans are a menu on a phone; chips would be cut off.
    await editor.getByTestId('plan-switcher-menu').tap()
    await page.getByTestId(`plan-switcher-option-${plan.id}`).tap()
    await expect(editor.getByTestId('plan-switcher-menu')).toHaveText('Skizze')
    const canvas = editor.getByTestId('editor-canvas')
    await expect(canvas).toBeVisible()
    await expect(editor.getByTestId('draw-hint')).toBeVisible()

    // Every tool fits the width (redo and snapping sit in "More"), touch-sized.
    const viewport = page.viewportSize()!
    const more = (await editor.getByTestId('tool-more').boundingBox())!
    expect(more.x + more.width).toBeLessThanOrEqual(viewport.width)
    expect(more.height).toBeGreaterThanOrEqual(40)

    // "More" opens on screen, next to its button (a menu behind a hint once
    // opened off the top of the page).
    await editor.getByTestId('tool-more').tap()
    await expect(page.getByTestId('tool-snap-menu')).toBeVisible()
    const snap = (await page.getByTestId('tool-snap-menu').boundingBox())!
    expect(snap.y).toBeGreaterThanOrEqual(0)
    expect(snap.y + snap.height).toBeLessThanOrEqual(viewport.height)
    expect(snap.x).toBeGreaterThanOrEqual(0)
    expect(snap.x + snap.width).toBeLessThanOrEqual(viewport.width)
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('tool-snap-menu')).toHaveCount(0)

    // The side panel is a sheet over the plan, shut until asked for.
    const panel = editor.getByTestId('editor-panel')
    await expect(panel).toBeHidden()
    await editor.getByTestId('editor-sheet-open').tap()
    await expect(panel.getByTestId('marker-palette')).toBeVisible()
    await panel.getByTestId('editor-sheet-close').tap()
    await expect(panel).toBeHidden()

    await editor.getByTestId('tool-polygon').tap()
    const box = (await canvas.boundingBox())!
    for (const [fx, fy] of [
      [0.3, 0.3],
      [0.7, 0.3],
      [0.5, 0.6],
    ] as const) {
      await canvas.tap({ position: { x: box.width * fx, y: box.height * fy } })
    }
    const bar = editor.getByTestId('draw-bar')
    await expect(bar).toBeVisible()
    const saved = page.waitForResponse(
      (r) => r.url().includes(`/venue-plans/${plan.id}/shapes/batch`) && r.ok(),
    )
    await bar.getByTestId('draw-close').tap()
    await saved

    const { shapes } = await getPlanShapes(page, plan.id)
    expect(shapes).toHaveLength(1)
    expect(shapes[0]).toMatchObject({ kind: 'polygon', style: 'area' })
    expect(shapes[0]!.points).toHaveLength(3)
    await expect(canvas.getByTestId(`venue-shape-${shapes[0]!.id}`)).toBeVisible()
  })

  test('an organiser starts a plan from a template and manages it in the sheet', async ({
    adminPage: page,
  }) => {
    // The worker admin is shared: its template is made here and always removed.
    const source = await createVenuePlan(page, seeded.event.id, { name: 'Quelle' })
    await batchShapes(page, source.id, [
      {
        op: 'create',
        shape: {
          id: crypto.randomUUID(),
          kind: 'rect',
          style: 'stage',
          points: [
            [0.2, 0.2],
            [0.6, 0.6],
          ],
        },
      },
    ])
    const name = uniqueName('Vorlage')
    const template = await api<{ id: string }>(
      page,
      'POST',
      `/venue-plans/${source.id}/save-as-template`,
      { name },
    )
    try {
      await page.goto(`/app/event-settings/${seeded.event.id}?tab=map`)
      const editor = page.getByTestId('venue-map-editor')
      await expect(editor.getByTestId('editor-canvas')).toBeVisible()

      await editor.getByTestId('plan-add').tap()
      await page.getByTestId('plan-create-template').tap()
      const card = page.getByTestId(`template-card-${template.id}`)
      await expect(card).toBeVisible()
      // Two cards per row inside the bottom sheet, never wider than the screen.
      const viewport = page.viewportSize()!
      const cardBox = (await card.boundingBox())!
      expect(cardBox.width).toBeLessThan(viewport.width / 2)
      expect(cardBox.x + cardBox.width).toBeLessThanOrEqual(viewport.width)

      // Rename in a second sheet on top of the first.
      await card.getByTestId('template-actions').tap()
      await page.getByTestId('template-rename').tap()
      const renamed = `${name} neu`
      await page.getByTestId('template-name-input').fill(renamed)
      await page.getByTestId('template-name-save').tap()
      await expect(page.getByTestId('template-name-dialog')).toHaveCount(0)
      await expect(card).toContainText(renamed)

      await card.locator('label').tap()
      await expect(page.getByTestId('plan-name-input')).toHaveValue(renamed)
      await page.getByTestId('plan-name-save').tap()
      await expect(
        editor.getByTestId('plan-switcher').getByRole('button', { name: renamed }),
      ).toBeVisible()

      // Delete it again, after the confirmation.
      await editor.getByTestId('plan-add').tap()
      await page.getByTestId('plan-create-template').tap()
      await card.getByTestId('template-actions').tap()
      await page.getByTestId('template-delete').tap()
      await page.getByTestId('btn-dialog-confirm').tap()
      await expect(card).toHaveCount(0)
    } finally {
      await api(page, 'DELETE', `/venue-templates/${template.id}`).catch(() => {})
    }
  })
})
