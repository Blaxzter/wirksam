/**
 * E2E tests for Tasks from a member (non-admin) perspective.
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

let created: TaskWithShifts
let shift: ShiftRead
const eventName = uniqueName('E2E Member Task')

test.beforeEach(async ({ adminPage }) => {
  await adminPage.goto('/app/tasks')
  created = await createTaskWithShifts(adminPage, {
    name: eventName,
    status: 'published',
    startTime: '10:00',
    endTime: '12:00',
    slotDuration: 60,
    peoplePerShift: 5,
  })
  ;[shift] = await listShifts(adminPage, created.task.id)
})

test.afterEach(async ({ adminPage }) => {
  await deleteTask(adminPage, created.task.id).catch(() => {})
})

// ── RBAC ─────────────────────────────────────────────────────────────────────

test.describe('Member – tasks RBAC', () => {
  test('member does not see Create Task button', async ({ memberPage: member }) => {
    await member.goto('/app/tasks')
    await expect(member.getByTestId('btn-create-task')).toBeHidden()
  })

  test('member does not see edit/delete buttons on task detail', async ({ memberPage: member }) => {
    await member.goto(`/app/tasks/${created.task.id}`)
    await expect(member.getByRole('heading', { name: created.task.name })).toBeVisible()
    await expect(member.getByTestId('btn-edit-task')).toBeHidden()
    await expect(member.getByTestId('btn-add-shifts')).toBeHidden()
  })

  test('member cannot access create task page', async ({ memberPage: member }) => {
    await member.goto('/app/tasks/create')
    // Should redirect away since it requires admin role
    await expect(member).not.toHaveURL(/\/app\/tasks\/create/)
  })
})

// ── member viewing ───────────────────────────────────────────────────────────

test.describe('Member – tasks viewing', () => {
  test('member can see published tasks', async ({ memberPage: member }) => {
    await member.goto('/app/tasks')
    // Use search to find the task (list is paginated)
    await member.getByTestId('input-search').fill(created.task.name)
    await expect(member.getByRole('heading', { name: created.task.name })).toBeVisible()
  })

  test('member can view task detail', async ({ memberPage: member }) => {
    await member.goto(`/app/tasks/${created.task.id}`)
    await expect(member.getByRole('heading', { name: created.task.name })).toBeVisible()
    await expect(member.getByTestId(`shift-card-${shift.id}`)).toContainText('0 of 5')
  })

  test('member can book a shift', async ({ memberPage: member }) => {
    await member.goto(`/app/tasks/${created.task.id}`)
    // A volunteer's tap on a shift books it, after a confirmation.
    const card = member.getByTestId(`shift-card-${shift.id}`)
    await expect(card).toContainText('0 of 5')
    await card.click()
    await member.getByTestId('btn-dialog-confirm').click()
    await expect(card).toContainText('1 of 5')
  })
})
