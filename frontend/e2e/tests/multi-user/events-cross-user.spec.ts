/**
 * Cross-user E2E tests for Tasks & Bookings.
 *
 * Admin creates task with shifts -> member books a shift -> admin sees booking count.
 */
import { expect, test } from '../../fixtures.js'
import {
  type ShiftRead,
  type TaskWithShifts,
  createTaskWithShifts,
  deleteTask,
  listShifts,
  uniqueName,
} from '../../helpers/api.js'

test.describe('Cross-user – task booking flow', () => {
  let created: TaskWithShifts
  let shift: ShiftRead

  test.beforeEach(async ({ adminPage }) => {
    await adminPage.goto('/app/tasks')
    created = await createTaskWithShifts(adminPage, {
      name: uniqueName('E2E Cross-User Booking Task'),
      status: 'published',
      startTime: '10:00',
      endTime: '12:00',
      slotDuration: 60,
      peoplePerShift: 3,
    })
    ;[shift] = await listShifts(adminPage, created.task.id)
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteTask(adminPage, created.task.id).catch(() => {})
  })

  test('member books shift, admin sees updated count', async ({
    adminPage,
    memberPage,
    memberUser,
  }) => {
    // Two people, a page load each after their own sign-in: 5 s on its own, but
    // with a full set of local workers 20-30 s, out of time at the last step.
    test.slow()

    // The tile names who is on it by first name, for everyone who sees the task.
    const firstName = memberUser.name.split(' ')[0]

    // Member navigates to the task and books the shift; a volunteer's tap on a
    // shift books it, after a confirmation.
    await memberPage.goto(`/app/tasks/${created.task.id}`)
    const memberCard = memberPage.getByTestId(`shift-card-${shift.id}`)
    await expect(memberCard).toContainText('0 of 3 · still free')
    await memberCard.click()
    await memberPage.getByTestId('btn-dialog-confirm').click()
    await expect(memberCard).toContainText(`1 of 3 · ${firstName}`)

    // Admin sees the updated booking count, and who it is, on the same shift
    await adminPage.goto(`/app/tasks/${created.task.id}`)
    const adminCard = adminPage.getByTestId(`shift-card-${shift.id}`)
    await expect(adminCard).toContainText(`1 of 3 · ${firstName}`)
  })

  test('admin-created task visible to member in tasks list', async ({ memberPage }) => {
    await memberPage.goto('/app/tasks')
    // Use search to find the task (list is paginated)
    await memberPage.getByTestId('input-search').fill(created.task.name)
    await expect(memberPage.getByRole('heading', { name: created.task.name })).toBeVisible()
  })
})
