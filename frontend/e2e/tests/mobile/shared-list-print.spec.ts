/**
 * Printing a notice on a phone: "Print" in the task page's ⋯ sheet asks in a
 * bottom sheet, and the notice it opens fits the narrowest phone, its columns
 * scrolling inside the sheet rather than the page. The whole event's question
 * opens with its page, and closing it hands focus to printing.
 */
import type { Page } from '@playwright/test'

import { expect, test } from '../../fixtures.js'
import {
  type SharedListEvent,
  removeSharedListEvent,
  seedSharedListEvent,
} from '../../helpers/shared-list-seed.js'

let seeded: SharedListEvent | undefined

test.afterEach(async ({ adminPage }) => {
  await removeSharedListEvent(adminPage, seeded)
  seeded = undefined
})

/** How far the page reaches past the screen's right edge. */
const sidewaysOverflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)

test('the ⋯ sheet asks in a bottom sheet, and the notice fits a phone', async ({
  adminPage: page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 })
  seeded = await seedSharedListEvent(page, 'E2E Phone Print')
  const { task, shifts } = seeded.tasks[0]!

  await page.goto(`/app/tasks/${task.id}`)
  await page.getByTestId('btn-task-more').click()
  await page.getByTestId('task-more-sheet').getByTestId('btn-print-mobile').click()

  const dialog = page.getByTestId('shared-list-print-dialog')
  await expect(dialog).toHaveAttribute('data-slot', 'drawer-content')
  await expect(dialog.getByTestId('shared-list-print-title')).toHaveText(task.name)
  await dialog.getByTestId('shared-list-print-create').click()

  await expect(page).toHaveURL(/\/print\/lists\/[0-9a-f-]+$/)
  await expect(page.getByTestId('print-qr').getByRole('img')).toBeVisible()
  await expect(page.getByTestId('print-shift-free')).toHaveCount(shifts.length)
  expect(await sidewaysOverflow(page)).toBeLessThanOrEqual(0)
})

test('closing the whole event’s bottom sheet hands focus to printing', async ({
  adminPage: page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 })
  seeded = await seedSharedListEvent(page, 'E2E Phone Print All')

  await page.goto(`/print/events/${seeded.event.id}?mode=all`)
  const dialog = page.getByTestId('shared-list-print-dialog')
  await expect(dialog).toHaveAttribute('data-slot', 'drawer-content')
  await dialog.getByRole('button', { name: 'Close' }).click()

  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Print', exact: true })).toBeFocused()
  expect(await sidewaysOverflow(page)).toBeLessThanOrEqual(0)
})
