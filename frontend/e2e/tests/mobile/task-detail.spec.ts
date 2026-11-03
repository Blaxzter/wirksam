/**
 * The task page on a phone (Pixel 7).
 *
 * Below desktop width an organiser's ⋯ and "Add shifts" open bottom sheets
 * instead of menus, the vouchers card comes before "In charge", and a tap on a
 * shift opens it, as it does for them on a desktop.
 */
import { expect, test } from '../../fixtures.js'
import {
  type ShiftRead,
  type TaskWithShifts,
  api,
  createTaskWithShifts,
  deleteTask,
  listShifts,
  uniqueName,
} from '../../helpers/api.js'

let created: TaskWithShifts
let shifts: ShiftRead[]

test.beforeEach(async ({ adminPage: page }) => {
  created = await createTaskWithShifts(page, {
    name: uniqueName('E2E Mobile Task Page'),
    status: 'published',
    startTime: '10:00',
    endTime: '12:00',
    slotDuration: 60,
    peoplePerShift: 3,
  })
  await api(page, 'PATCH', `/tasks/${created.task.id}`, { vouchers_per_shift: 2 })
  shifts = await listShifts(page, created.task.id)
})

test.afterEach(async ({ adminPage: page }) => {
  await deleteTask(page, created.task.id).catch(() => {})
})

test.describe('Task page – on a phone', () => {
  test("the organiser's ⋯ opens a sheet whose rows open the task's dialogs", async ({
    adminPage: page,
  }) => {
    expect(page.viewportSize()?.width).toBeLessThan(768)
    await page.goto(`/app/tasks/${created.task.id}`)

    await page.getByTestId('btn-task-more').click()
    const sheet = page.getByTestId('task-more-sheet')
    await expect(sheet).toBeVisible()
    await expect(sheet).toHaveAttribute('data-slot', 'drawer-content')
    await expect(sheet).toContainText(created.task.name)
    for (const row of [
      'btn-task-managers-mobile',
      'btn-task-vouchers-mobile',
      'btn-print-mobile',
      'btn-delete-task-mobile',
    ]) {
      await expect(sheet.getByTestId(row)).toBeVisible()
    }

    await sheet.getByTestId('btn-task-managers-mobile').click()
    await expect(sheet).toBeHidden()
    await expect(page.getByTestId('task-managers-dialog')).toBeVisible()
  })

  test('closing the sheet, or a dialog one of its rows opened, puts focus back on ⋯', async ({
    adminPage: page,
  }) => {
    // reka's sheet only hands focus back to a trigger of its own, and these
    // open through v-model: without the fix focus dropped to <body>.
    await page.goto(`/app/tasks/${created.task.id}`)
    const more = page.getByTestId('btn-task-more')
    const sheet = page.getByTestId('task-more-sheet')

    await more.focus()
    await page.keyboard.press('Enter')
    await sheet.getByTestId('btn-task-vouchers-mobile').focus()
    await page.keyboard.press('Enter')
    const dialog = page.getByTestId('task-voucher-settings-dialog')
    await expect(dialog).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(more).toBeFocused()

    await page.keyboard.press('Enter')
    await sheet.getByRole('button', { name: 'Cancel' }).click()
    await expect(sheet).toBeHidden()
    await expect(more).toBeFocused()
  })

  test('"Add shifts" opens a sheet with both ways to add them', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)

    await page.getByTestId('btn-add-shifts').click()
    const sheet = page.getByTestId('task-add-shifts-sheet')
    await expect(sheet.getByTestId('btn-add-shift-batch-mobile')).toBeVisible()
    await sheet.getByTestId('btn-add-single-shift-mobile').click()

    await expect(sheet).toBeHidden()
    await expect(page.getByTestId('dialog-create-shift')).toBeVisible()
  })

  test('the vouchers card comes first, and a tap on a shift opens it', async ({
    adminPage: page,
  }) => {
    await page.goto(`/app/tasks/${created.task.id}`)

    const vouchers = page.getByTestId('task-vouchers-card')
    const inCharge = page.getByTestId('task-in-charge-card')
    await expect(vouchers.getByTestId('task-vouchers-per-shift')).toContainText('2 per shift')
    const [v, c] = [(await vouchers.boundingBox())!, (await inCharge.boundingBox())!]
    expect(v.y).toBeLessThan(c.y)

    // On a phone the badge carries the count.
    const card = page.getByTestId(`shift-card-${shifts[0].id}`)
    await expect(card).toContainText('Nobody yet')
    await card.click()
    await expect(page.getByTestId('dialog-shift-detail')).toHaveAttribute(
      'data-slot',
      'drawer-content',
    )
  })
})
