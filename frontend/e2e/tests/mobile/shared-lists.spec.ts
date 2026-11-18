/**
 * The shared-lists page on a phone: cards instead of the table, a ⋯ menu per
 * list instead of a row of icons, the details as a bottom sheet, a selection
 * bar that clears the bottom navigation, and nothing wider than the screen.
 */
import type { Page } from '@playwright/test'

import { expect, test } from '../../fixtures.js'
import { type SharedListDetail, createSharedList } from '../../helpers/api.js'
import {
  type SharedListEvent,
  removeSharedListEvent,
  seedSharedListEvent,
} from '../../helpers/shared-list-seed.js'

let seeded: SharedListEvent | undefined
let lists: SharedListDetail[]

test.beforeEach(async ({ adminPage, adminUser }) => {
  seeded = await seedSharedListEvent(adminPage, 'E2E Phone Lists')
  lists = []
  for (const title of ['Elternchat', 'Aushang Kita']) {
    lists.push(
      await createSharedList(adminUser.email, seeded.event.id, {
        title,
        task_ids: [seeded.tasks[0].task.id],
      }),
    )
  }
})

test.afterEach(async ({ adminPage }) => {
  await removeSharedListEvent(adminPage, seeded)
  seeded = undefined
})

async function openPage(page: Page) {
  await page.goto(`/app/shared-lists/${seeded!.event.id}`)
  await expect(page.getByTestId('shared-lists-cards')).toBeVisible()
}

test('the viewport really is a phone', async ({ adminPage }) => {
  expect(adminPage.viewportSize()?.width).toBeLessThan(768)
})

/** How far the page reaches past the screen's right edge. */
const sidewaysOverflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)

test('lists are cards with a sort control, and nothing scrolls sideways', async ({ adminPage }) => {
  // The narrowest phone the app is laid out for, narrower than the device's own.
  await adminPage.setViewportSize({ width: 375, height: 812 })
  await openPage(adminPage)

  await expect(adminPage.getByTestId('shared-lists-table')).toHaveCount(0)
  await expect(adminPage.getByTestId('sort-select')).toBeVisible()
  await expect(adminPage.getByTestId(`shared-list-row-${lists[0].id}`)).toContainText('Elternchat')
  // The filter chips scroll inside their own row instead of widening the page.
  expect(await sidewaysOverflow(adminPage)).toBeLessThanOrEqual(0)

  await adminPage.getByTestId('tab-tasks').click()
  await expect(adminPage.getByTestId(`shared-list-task-${seeded!.tasks[0].task.id}`)).toBeVisible()
  expect(await sidewaysOverflow(adminPage)).toBeLessThanOrEqual(0)
})

test('the ⋯ menu opens the list’s own page', async ({ adminPage }) => {
  await openPage(adminPage)
  const card = adminPage.getByTestId(`shared-list-row-${lists[0].id}`)

  await card.getByTestId('shared-list-menu').click()
  await adminPage.getByRole('menuitem', { name: 'Details' }).click()

  const page = adminPage.getByTestId('shared-list-detail')
  await expect(adminPage).toHaveURL(new RegExp(`/app/shared-lists/[^/]+/${lists[0].id}$`))
  await expect(page.getByTestId('shared-list-detail-title')).toHaveText('Elternchat')
  // One main action and a menu for the rest, not a block of buttons.
  await expect(page.getByTestId('shared-list-detail-pause')).toBeVisible()
  await expect(page.getByTestId('shared-list-detail-more')).toBeVisible()
  await expect(page.getByTestId('shared-list-detail-edit')).toHaveCount(0)
  expect(await sidewaysOverflow(adminPage)).toBeLessThanOrEqual(0)
})

test('the selection bar stays clear of the bottom navigation', async ({ adminPage }) => {
  await openPage(adminPage)

  await adminPage
    .getByTestId(`shared-list-row-${lists[0].id}`)
    .getByTestId('shared-list-select')
    .click()
  const bar = adminPage.getByTestId('selection-bar')
  await expect(bar).toBeVisible()
  // On a phone the actions fold into one menu.
  await expect(bar.getByTestId('selection-actions')).toBeVisible()

  const barBox = (await bar.boundingBox())!
  const navBox = (await adminPage.getByTestId('mobile-bottom-nav').boundingBox())!
  expect(barBox.y + barBox.height).toBeLessThanOrEqual(navBox.y)
})
