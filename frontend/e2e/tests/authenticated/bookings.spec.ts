/**
 * E2E tests for My Bookings page.
 */
import { expect, test } from '../../fixtures.js'
import {
  type ShiftRead,
  type TaskWithShifts,
  bookShift,
  createTaskWithShifts,
  deleteTask,
  listShifts,
  uniqueName,
} from '../../helpers/api.js'

let created: TaskWithShifts
let shifts: ShiftRead[]

test.beforeEach(async ({ adminPage: page }) => {
  await page.goto('/app/tasks')
  created = await createTaskWithShifts(page, {
    name: uniqueName('E2E Booking Task'),
    location: 'Room A',
    status: 'published',
    startTime: '10:00',
    endTime: '12:00',
    slotDuration: 60,
    peoplePerShift: 5,
  })
  shifts = await listShifts(page, created.task.id)
})

test.afterEach(async ({ adminPage: page }) => {
  await deleteTask(page, created.task.id).catch(() => {})
})

// ── navigation ───────────────────────────────────────────────────────────────

test.describe('My Bookings – navigation', () => {
  test('sidebar shows My Bookings link', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('sidebar-link-my-bookings')).toBeVisible()
  })

  test('clicking sidebar link navigates to /app/bookings', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('sidebar-link-my-bookings').click()
    await expect(page).toHaveURL(/\/app\/bookings$/)
  })
})

// ── page structure ───────────────────────────────────────────────────────────

test.describe('My Bookings – page structure', () => {
  test('shows heading', async ({ adminPage: page }) => {
    await page.goto('/app/bookings')
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('shows search input', async ({ adminPage: page }) => {
    await page.goto('/app/bookings')
    await expect(page.getByTestId('input-search')).toBeVisible()
  })

  test('shows show cancelled toggle', async ({ adminPage: page }) => {
    await page.goto('/app/bookings')
    await expect(page.getByTestId('btn-toggle-cancelled')).toBeVisible()
  })
})

// ── with bookings ────────────────────────────────────────────────────────────

test.describe('My Bookings – with data', () => {
  test('booked shift appears in bookings list', async ({ adminPage: page }) => {
    // eslint-disable-next-line playwright/no-conditional-in-test
    if (shifts.length === 0) return

    await bookShift(page, shifts[0].id)
    await page.goto('/app/bookings')

    // The task name is dynamic data — use heading role to avoid strict mode violation
    await expect(page.getByRole('heading', { name: created.task.name })).toBeVisible()
  })

  test('a booking opens its details, where it can be handed back', async ({ adminPage: page }) => {
    // eslint-disable-next-line playwright/no-conditional-in-test
    if (shifts.length === 0) return

    await bookShift(page, shifts[0].id)
    await page.goto('/app/bookings')

    // The whole card is the way in; the task's name is its link.
    const card = page.getByTestId('booking-card').filter({ hasText: created.task.name })
    await expect(card).toContainText('Confirmed')
    await card.getByRole('link', { name: created.task.name }).click()

    await expect(page).toHaveURL(/\/app\/bookings\/[0-9a-f-]{36}$/)
    await expect(page.getByTestId('btn-cancel-booking')).toBeVisible()
  })
})

// ── filter switching ─────────────────────────────────────────────────────────

test.describe('My Bookings – filters', () => {
  test('show cancelled toggle can be activated', async ({ adminPage: page }) => {
    await page.goto('/app/bookings')
    await page.getByTestId('btn-toggle-cancelled').click()
    // Page should remain functional
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })
})

// ── grouping ─────────────────────────────────────────────────────────────────

test.describe('My Bookings – grouping', () => {
  test('the list is arranged by date, task or place, one at a time', async ({
    adminPage: page,
  }) => {
    // eslint-disable-next-line playwright/no-conditional-in-test
    if (shifts.length === 0) return

    await bookShift(page, shifts[0].id)
    await page.goto('/app/bookings')

    const byDate = page.getByTestId('btn-event-date')
    const byTask = page.getByTestId('btn-event-task')
    await expect(byDate).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('btn-event-location')).toBeVisible()

    await byTask.click()
    await expect(byTask).toHaveAttribute('aria-pressed', 'true')
    await expect(byDate).toHaveAttribute('aria-pressed', 'false')
    // Grouped by task: the task's name heads its group.
    await expect(page.getByRole('heading', { level: 2, name: created.task.name })).toBeVisible()

    // Back to the plain list, so the next test starts from the default.
    await byDate.click()
    await expect(byDate).toHaveAttribute('aria-pressed', 'true')
  })
})
