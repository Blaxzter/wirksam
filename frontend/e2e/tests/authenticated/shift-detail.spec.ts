/**
 * E2E tests for the shift-details dialog reached from the task list.
 *
 * This is the path a volunteer actually takes to take a shift — open
 * /app/tasks, press a chip in the week grid, read what the shift is, book it —
 * and it had no coverage at all until a rename left `ShiftDetailDialog`
 * declaring props nobody passed and the dialog opened empty for months. An
 * unknown prop falls through to the root element as a plain attribute and every
 * prop involved is optional, so neither vue-tsc nor ESLint has anything to say
 * about it. Only a test that reads the dialog's *contents* does.
 *
 * Hence: never assert on `dialog-shift-detail` alone. It is on `DialogContent`,
 * which renders whether or not a shift resolved — the heading and the close
 * button sit outside the `v-else-if`, so a completely empty dialog is "visible".
 */
import type { Page } from '@playwright/test'

import { expect, test } from '../../fixtures.js'
import {
  type ShiftRead,
  type TaskWithShifts,
  createTaskWithShifts,
  deleteTask,
  listShifts,
  uniqueName,
} from '../../helpers/api.js'

let created: TaskWithShifts
let shifts: ShiftRead[]
let taskName: string

test.beforeEach(async ({ adminPage: page }) => {
  taskName = uniqueName('E2E Shift Detail Task')
  created = await createTaskWithShifts(page, {
    name: taskName,
    location: 'Side Entrance',
    category: 'Welcome',
    status: 'published',
    peoplePerShift: 2,
  })
  shifts = await listShifts(page, created.task.id)
})

test.afterEach(async ({ adminPage: page }) => {
  // Takes the bookings made below with it.
  await deleteTask(page, created.task.id).catch(() => {})
})

/**
 * The list is paginated and the view mode is remembered per browser, so both
 * are pinned through the URL — `readUrlIntoStore` lets the query win over
 * localStorage, which is the only way to be sure of landing on the week grid
 * with this task in it.
 */
async function openShiftChip(page: Page, shiftId: string) {
  await page.goto(`/app/tasks?view=list&search=${encodeURIComponent(taskName)}`)
  const chip = page.getByTestId(`shift-chip-${shiftId}`)
  await expect(chip).toBeVisible()
  await chip.click()
}

test.describe('Shift details – from the task list', () => {
  test('a chip opens a dialog describing the shift it names', async ({ adminPage: page }) => {
    await openShiftChip(page, shifts[0].id)

    const dialog = page.getByTestId('dialog-shift-detail')
    // The task name arrives as its own prop, and was the other half of the
    // rename that broke: it is the dialog's heading now, and stayed blank even
    // where the shift loaded.
    await expect(dialog).toContainText(taskName)
    // Both of these come off the shift itself, so neither can be satisfied by a
    // dialog that opened over nothing — which is the whole point of this test.
    await expect(dialog).toContainText('Side Entrance')
    await expect(dialog.getByTestId('shift-roster-count')).toHaveText('0 of 2, 2 places free')
    await expect(dialog.getByTestId('shift-roster-free')).toContainText('2 places free')
  })

  test('the dialog offers the shift for booking', async ({ adminPage: page }) => {
    await openShiftChip(page, shifts[0].id)
    await expect(page.getByTestId('btn-book-shift')).toBeVisible()
  })

  test('booking from the dialog takes the shift', async ({ adminPage: page }) => {
    await openShiftChip(page, shifts[0].id)
    await page.getByTestId('btn-book-shift').click()

    // The dialog closes and the list reloads behind it, so the chip itself is
    // the honest witness that the booking landed.
    await expect(page.getByTestId('dialog-shift-detail')).toBeHidden()
    await expect(page.getByTestId(`shift-chip-${shifts[0].id}`)).toContainText('1/2')
  })

  test('a shift already taken offers cancelling instead', async ({ adminPage: page }) => {
    await openShiftChip(page, shifts[0].id)
    await page.getByTestId('btn-book-shift').click()
    await expect(page.getByTestId('dialog-shift-detail')).toBeHidden()

    await openShiftChip(page, shifts[0].id)
    await expect(page.getByTestId('btn-cancel-shift-booking')).toBeVisible()
    await expect(page.getByTestId('btn-book-shift')).toBeHidden()
  })
})
