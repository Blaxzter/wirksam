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

  test('member books shift, admin sees updated count', async ({ adminPage, memberPage }) => {
    // By the card's test id: a bare getByText(/0\/3/) also matches the task's
    // date range in the header whenever it reads 10/30 or 10/31.
    await memberPage.goto(`/app/tasks/${created.task.id}`)
    const memberCard = memberPage.getByTestId(`shift-card-${shift.id}`)
    await expect(memberCard).toContainText('0/3')
    await memberCard.click()
    await memberPage.getByTestId('btn-dialog-confirm').click()
    await expect(memberCard).toContainText('1/3')

    // Admin sees the updated booking count
    await adminPage.goto(`/app/tasks/${created.task.id}`)
    await expect(adminPage.getByTestId(`shift-card-${shift.id}`)).toContainText('1/3')
  })

  test('admin-created task visible to member in tasks list', async ({ memberPage }) => {
    await memberPage.goto('/app/tasks')
    // Use search to find the task (list is paginated)
    await memberPage.getByTestId('input-search').fill(created.task.name)
    await expect(memberPage.getByRole('heading', { name: created.task.name })).toBeVisible()
  })
})
