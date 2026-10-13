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
  createVenuePlan,
  deleteEvent,
  deleteTask,
  getPlanShapes,
  seedMappedEvent,
  setSelectedEvent,
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
    await editor.getByTestId('plan-switcher').getByRole('button', { name: 'Skizze' }).tap()
    const canvas = editor.getByTestId('editor-canvas')
    await expect(canvas).toBeVisible()
    await expect(editor.getByTestId('draw-hint')).toBeVisible()

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
})
