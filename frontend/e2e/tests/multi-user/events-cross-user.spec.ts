/**
 * Cross-user E2E tests for Tasks & Bookings.
 *
 * Admin creates task with shifts -> member books a shift -> admin sees booking count.
 */
import { expect, test } from '../../fixtures.js'
import {
  type TaskWithShifts,
  createTaskWithShifts,
  deleteTask,
  uniqueName,
} from '../../helpers/api.js'

test.describe('Cross-user – task booking flow', () => {
  let created: TaskWithShifts

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
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteTask(adminPage, created.task.id).catch(() => {})
  })

  test('member books shift, admin sees updated count', async ({
    adminPage,
    memberPage,
    memberUser,
  }) => {
    // The tile names who is on it by first name, for everyone who sees the task.
    const firstName = memberUser.name.split(' ')[0]

    // Member navigates to the task and books the first shift; a volunteer's
    // tap on a shift books it, after a confirmation.
    await memberPage.goto(`/app/tasks/${created.task.id}`)
    const memberCard = memberPage.locator('[data-testid^="shift-card-"]').first()
    await expect(memberCard).toContainText('0 of 3 · still free')
    await memberCard.click()
    await memberPage.getByTestId('btn-dialog-confirm').click()
    await expect(memberCard).toContainText(`1 of 3 · ${firstName}`)

    // Admin sees the updated booking count, and who it is, on the same (first) shift
    await adminPage.goto(`/app/tasks/${created.task.id}`)
    const adminCard = adminPage.locator('[data-testid^="shift-card-"]').first()
    await expect(adminCard).toContainText(`1 of 3 · ${firstName}`)
  })

  test('admin-created task visible to member in tasks list', async ({ memberPage }) => {
    await memberPage.goto('/app/tasks')
    // Use search to find the task (list is paginated)
    await memberPage.getByTestId('input-search').fill(created.task.name)
    await expect(memberPage.getByRole('heading', { name: created.task.name })).toBeVisible()
  })
})
