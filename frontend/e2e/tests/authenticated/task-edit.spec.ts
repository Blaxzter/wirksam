/**
 * E2E tests for Task Edit and Add Shifts views.
 */
import { expect, test } from '../../fixtures.js'
import {
  type TaskRead,
  type TaskWithShifts,
  api,
  createTaskWithShifts,
  deleteTask,
  futureDate,
  listShifts,
  uniqueName,
} from '../../helpers/api.js'

let created: TaskWithShifts

test.beforeEach(async ({ adminPage: page }) => {
  await page.goto('/app/tasks')
  created = await createTaskWithShifts(page, {
    name: uniqueName('E2E Edit Task'),
    status: 'published',
    startTime: '09:00',
    endTime: '17:00',
    slotDuration: 120,
    peoplePerShift: 2,
  })
})

test.afterEach(async ({ adminPage: page }) => {
  await deleteTask(page, created.task.id).catch(() => {})
})

test.describe('Task Edit – page access', () => {
  test('can navigate to edit page via URL', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}/edit`)
    await expect(page).toHaveURL(new RegExp(`/app/tasks/${created.task.id}/edit`))
  })

  test('shows edit page heading', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}/edit`)
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('shows back button', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}/edit`)
    await expect(page.getByTestId('btn-back')).toBeVisible()
  })

  test('shows schedule configuration section', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}/edit`)
    await expect(page.getByTestId('section-schedule')).toBeVisible()
  })
})

test.describe('Task Edit – a task with several shift series', () => {
  test('an organiser renames it, and every series keeps its shifts', async ({
    adminPage: page,
  }) => {
    // A second series. Each series has its own edit for its shifts; the
    // task's own edit is where its name and description are changed.
    await api(page, 'POST', `/tasks/${created.task.id}/add-shifts`, {
      start_date: futureDate(2),
      end_date: futureDate(2),
      schedule: {
        default_start_time: '10:00:00',
        default_end_time: '12:00:00',
        shift_duration_minutes: 60,
        people_per_shift: 2,
      },
    })
    const before = await listShifts(page, created.task.id)

    await page.goto(`/app/tasks/${created.task.id}`)
    await expect(page.getByTestId('btn-edit-batch')).toHaveCount(2)
    await page.getByTestId('btn-edit-task').click()
    await expect(page).toHaveURL(new RegExp(`/app/tasks/${created.task.id}/edit$`))

    // The details only: the shifts are the series'.
    await expect(page.getByTestId('task-shifts-in-batches')).toBeVisible()
    await expect(page.getByTestId('section-schedule')).toHaveCount(0)
    const renamed = uniqueName('E2E Edit Task renamed')
    await page.getByTestId('input-task-name').fill(renamed)
    await page.locator('#task-description').fill('Bring a warm jacket.')
    await page.getByTestId('btn-submit').click()

    await expect(page).toHaveURL(new RegExp(`/app/tasks/${created.task.id}$`))
    await expect(page.getByTestId('page-heading')).toHaveText(renamed)
    const saved = await api<TaskRead>(page, 'GET', `/tasks/${created.task.id}`)
    expect(saved.description).toBe('Bring a warm jacket.')

    // Same shifts, same series, and their titles carry the new name.
    const after = await listShifts(page, created.task.id)
    expect(after.map((s) => [s.id, s.batch_id]).sort()).toEqual(
      before.map((s) => [s.id, s.batch_id]).sort(),
    )
    for (const shift of after) expect(shift.title.startsWith(`${renamed} `)).toBe(true)
  })
})

test.describe('Task Add Shifts – page access', () => {
  test('can navigate to add-shifts page via URL', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}/add-shifts`)
    await expect(page).toHaveURL(new RegExp(`/app/tasks/${created.task.id}/add-shifts`))
  })

  test('shows add-shifts heading', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}/add-shifts`)
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('shows back button', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}/add-shifts`)
    await expect(page.getByTestId('btn-back')).toBeVisible()
  })

  test("starts from the task's schedule, even a shift length the list does not offer", async ({
    adminPage: page,
  }) => {
    // Shifts of four and a half hours until seven in the evening: not one of
    // the usual lengths, and an end a 12-hour clock would write as "07:00 PM".
    const long = await createTaskWithShifts(page, {
      name: uniqueName('E2E Long Shifts'),
      status: 'published',
      startTime: '10:00',
      endTime: '19:00',
      slotDuration: 270,
      peoplePerShift: 4,
    })
    try {
      await page.goto(`/app/tasks/${long.task.id}/add-shifts`)
      const times = page.getByTestId('input-daily-window').locator('input')
      await expect(times.nth(0)).toHaveValue('10:00')
      await expect(times.nth(1)).toHaveValue('19:00')
      await expect(page.getByTestId('input-shift-duration').getByRole('combobox')).toContainText(
        '270',
      )
    } finally {
      await deleteTask(page, long.task.id).catch(() => {})
    }
  })
})

test.describe('Task Edit/Add Shifts – member RBAC', () => {
  test('member cannot access edit page', async ({ memberPage: member }) => {
    await member.goto(`/app/tasks/${created.task.id}/edit`)
    await expect(member).not.toHaveURL(/\/edit/)
  })

  test('member cannot access add-shifts page', async ({ memberPage: member }) => {
    await member.goto(`/app/tasks/${created.task.id}/add-shifts`)
    await expect(member).not.toHaveURL(/\/add-shifts/)
  })
})
