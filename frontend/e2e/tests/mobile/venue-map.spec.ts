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
  deleteEvent,
  deleteTask,
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
})
