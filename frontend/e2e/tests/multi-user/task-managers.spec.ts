/**
 * E2E tests for the people in charge of a task.
 *
 * An organiser puts an event member in charge of a task from the task page.
 * That member can then edit the task and its shifts, but cannot delete or
 * publish it: the draft banner asks them to get an organiser to publish. On a
 * task that earns vouchers the shifts stay with the organisers unless the
 * event's voucher rules allow people in charge to change them.
 *
 * Each test gets its own event, and the person in charge is a disposable
 * user, so nothing leaks into the shared worker fixtures.
 */
import { expect, test } from '../../fixtures.js'
import {
  type EventRead,
  type TaskRead,
  addMember,
  api,
  apiStatus,
  createEvent,
  createTaskWithShifts,
  deleteEvent,
  deleteTask,
  futureDate,
  listShifts,
  uniqueName,
} from '../../helpers/api.js'
import { pickDate } from '../../helpers/ui.js'

let event: EventRead
let task: TaskRead

test.beforeEach(async ({ adminPage, disposablePage, disposableUser }) => {
  event = await createEvent(adminPage, uniqueName('E2E In Charge'), 'published', 'private', {
    start: futureDate(1),
    end: futureDate(4),
  })
  const created = await createTaskWithShifts(adminPage, {
    name: uniqueName('E2E Bar'),
    eventId: event.id,
    status: 'draft',
    startDate: futureDate(2),
    endDate: futureDate(2),
    startTime: '10:00',
    endTime: '12:00',
    slotDuration: 60,
    peoplePerShift: 2,
  })
  task = created.task
  await addMember(adminPage, disposablePage, event.id, disposableUser.email)
})

test.afterEach(async ({ adminPage }) => {
  // Tasks outlive their event, so they go first; the task takes its people
  // in charge with it.
  await deleteTask(adminPage, task.id).catch(() => {})
  await deleteEvent(adminPage, event.id).catch(() => {})
})

test('an organiser puts a member in charge from the task page', async ({
  adminPage,
  disposableUser,
}) => {
  await adminPage.goto(`/app/tasks/${task.id}`)
  await adminPage.getByTestId('btn-task-more').click()
  await adminPage.getByTestId('btn-task-managers').click()

  const dialog = adminPage.getByTestId('task-managers-dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog.getByTestId('task-managers-empty')).toBeVisible()

  // Picking is the action: the highlighted match is added on Enter.
  const search = dialog.getByTestId('task-add-manager')
  await search.click()
  await search.fill(disposableUser.name)
  await expect(adminPage.getByTestId(`task-add-manager-option-${disposableUser.id}`)).toBeVisible()
  await search.press('Enter')

  await expect(dialog.getByTestId(`task-manager-row-${disposableUser.id}`)).toBeVisible()
  await expect(adminPage.getByTestId('task-managers')).toContainText(disposableUser.name)

  const saved = await api<TaskRead>(adminPage, 'GET', `/tasks/${task.id}`)
  expect(saved.managers?.map((m) => m.user_id)).toEqual([disposableUser.id])
})

test('a person in charge edits the task and adds a shift, but cannot delete or publish it', async ({
  adminPage,
  disposablePage,
  disposableUser,
}) => {
  await api(adminPage, 'POST', `/tasks/${task.id}/managers`, { user_id: disposableUser.id })
  const shiftsBefore = (await listShifts(adminPage, task.id)).length

  await disposablePage.goto(`/app/tasks/${task.id}`)
  await expect(disposablePage.getByTestId('page-heading')).toHaveText(task.name)

  // A draft they can see, but only an organiser can publish.
  await expect(disposablePage.getByTestId('task-draft-banner')).toContainText(
    'Ask an organiser to publish it',
  )
  await expect(disposablePage.getByTestId('task-you-are-in-charge')).toBeVisible()
  await expect(disposablePage.getByTestId('btn-edit-task')).toBeVisible()
  await expect(disposablePage.getByTestId('btn-delete-task')).toHaveCount(0)
  expect(
    await apiStatus(disposablePage, 'PATCH', `/tasks/${task.id}`, { status: 'published' }),
  ).toBe(403)

  // Rename it. The team is the organisers' call, so that card is not offered.
  const renamed = uniqueName('E2E Bar renamed')
  await disposablePage.getByTestId('btn-edit-task').click()
  await expect(disposablePage).toHaveURL(new RegExp(`/app/tasks/${task.id}/edit`))
  await expect(disposablePage.getByTestId('section-schedule')).toBeVisible()
  await expect(disposablePage.getByTestId('section-who-can-book')).toHaveCount(0)
  await disposablePage.getByTestId('input-task-name').fill(renamed)
  await disposablePage.getByTestId('btn-submit').click()
  await expect(disposablePage).toHaveURL(new RegExp(`/app/tasks/${task.id}$`))
  await expect(disposablePage.getByTestId('page-heading')).toHaveText(renamed)

  // Add a single shift on another day of the task.
  await disposablePage.getByTestId('btn-add-shifts').click()
  await disposablePage.getByTestId('btn-add-single-shift').click()
  const dialog = disposablePage.getByTestId('dialog-create-shift')
  await expect(dialog).toBeVisible()
  await dialog.getByTestId('input-shift-title').fill('Late shift')
  await pickDate(dialog.getByRole('button', { name: 'Pick a date' }), futureDate(2))
  await dialog.getByTestId('btn-create-shift').click()
  await expect(dialog).toBeHidden()

  await expect
    .poll(async () => (await listShifts(adminPage, task.id)).length)
    .toBe(shiftsBefore + 1)
})

test('the shifts of a voucher task stay with the organisers until the event lets people in charge change them', async ({
  adminPage,
  disposablePage,
  disposableUser,
}) => {
  // A second batch of shifts. Each batch then has its own edit, which changes
  // shifts, so the task's own edit has to stay for the details.
  await api(adminPage, 'POST', `/tasks/${task.id}/add-shifts`, {
    start_date: futureDate(3),
    end_date: futureDate(3),
    schedule: {
      default_start_time: '14:00:00',
      default_end_time: '16:00:00',
      shift_duration_minutes: 60,
      people_per_shift: 2,
    },
  })
  await api(adminPage, 'PATCH', `/tasks/${task.id}`, { vouchers_per_shift: 2 })
  await api(adminPage, 'POST', `/tasks/${task.id}/managers`, { user_id: disposableUser.id })

  // The details are still theirs; the shifts are not, and the page says why.
  await disposablePage.goto(`/app/tasks/${task.id}`)
  await expect(disposablePage.getByTestId('page-heading')).toHaveText(task.name)
  await expect(disposablePage.getByTestId('task-voucher-shifts-locked')).toBeVisible()
  await expect(disposablePage.getByTestId('btn-add-shifts')).toHaveCount(0)
  await expect(disposablePage.getByTestId('btn-edit-task')).toBeVisible()

  // Editing offers the details only, and saving them leaves the shifts alone.
  const shiftsBefore = (await listShifts(adminPage, task.id)).length
  const renamed = uniqueName('E2E Bar renamed')
  await disposablePage.getByTestId('btn-edit-task').click()
  await expect(disposablePage).toHaveURL(new RegExp(`/app/tasks/${task.id}/edit`))
  await expect(disposablePage.getByTestId('task-voucher-shifts-locked')).toBeVisible()
  await expect(disposablePage.getByTestId('section-schedule')).toHaveCount(0)
  await disposablePage.getByTestId('input-task-name').fill(renamed)
  await disposablePage.getByTestId('btn-submit').click()
  await expect(disposablePage).toHaveURL(new RegExp(`/app/tasks/${task.id}$`))
  await expect(disposablePage.getByTestId('page-heading')).toHaveText(renamed)
  expect((await listShifts(adminPage, task.id))).toHaveLength(shiftsBefore)

  // The organiser allows it in the event's voucher rules.
  await adminPage.goto(`/app/event-settings/${event.id}?tab=vouchers`)
  const rules = adminPage.getByTestId('section-event-voucher-rules')
  await expect(rules).toBeVisible()
  await expect(rules.getByTestId('voucher-manual-on_shift')).toHaveAttribute(
    'data-state',
    'checked',
  )
  await rules.getByTestId('switch-managers-edit-voucher-shifts').click()
  await rules.getByTestId('btn-save-voucher-rules').click()
  await expect(adminPage.locator('[data-sonner-toast]')).toContainText('Voucher rules saved.')
  const saved = await api<EventRead>(adminPage, 'GET', `/events/${event.id}`)
  expect(saved.managers_edit_voucher_shifts).toBe(true)

  await disposablePage.reload()
  await expect(disposablePage.getByTestId('page-heading')).toHaveText(renamed)
  await expect(disposablePage.getByTestId('btn-add-shifts')).toBeVisible()
  await expect(disposablePage.getByTestId('task-voucher-shifts-locked')).toHaveCount(0)
  // With the shifts theirs again, each batch's own edit takes over.
  await expect(disposablePage.getByTestId('btn-edit-task')).toHaveCount(0)
})
