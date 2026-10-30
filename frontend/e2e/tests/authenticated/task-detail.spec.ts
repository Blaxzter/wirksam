/**
 * E2E tests for Task Detail page — viewing, booking, status, admin actions.
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
    name: uniqueName('E2E Detail Task'),
    description: 'E2E test description',
    location: 'Main Hall',
    category: 'Sound',
    status: 'published',
    startTime: '09:00',
    endTime: '11:00',
    slotDuration: 60,
    peoplePerShift: 3,
  })
  shifts = await listShifts(page, created.task.id)
})

test.afterEach(async ({ adminPage: page }) => {
  await deleteTask(page, created.task.id).catch(() => {})
})

// ── page structure ───────────────────────────────────────────────────────────

test.describe('Task Detail – page structure', () => {
  test('shows task name and status', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)
    await expect(page.getByTestId('page-heading')).toContainText(created.task.name)
    await expect(page.getByTestId('task-status')).toBeVisible()
  })

  test('shows task description', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)
    await expect(page.getByText('E2E test description')).toBeVisible()
  })

  test('shows location in header', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)
    await expect(page.getByText('Main Hall')).toBeVisible()
  })

  test('shows category in header', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)
    await expect(page.getByText('Sound')).toBeVisible()
  })

  test('shows duty shifts section', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)
    await expect(page.getByTestId('section-shifts')).toBeVisible()
  })

  test('shows shift time cards', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)
    // Shifts should show time and availability count
    await expect(page.getByText('0/3', { exact: true }).first()).toBeVisible()
  })

  test('back button navigates to tasks list', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)
    await page.getByTestId('btn-back').click()
    await expect(page).toHaveURL(/\/app\/tasks$/)
  })
})

// ── booking ──────────────────────────────────────────────────────────────────

test.describe('Task Detail – booking', () => {
  test('clicking a shift books it', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)
    // Wait for shifts to render — find shift cards by their availability text
    const slotCard = page.getByText('0/3', { exact: true }).first()
    await expect(slotCard).toBeVisible()

    // Click first available shift card
    await slotCard.click()

    // Handle booking confirmation dialog if it appears
    const confirmBtn = page.getByRole('button', { name: /confirm|bestätigen/i })
    // eslint-disable-next-line playwright/no-conditional-in-test
    if (await confirmBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await confirmBtn.click()
    }

    // Should show booking count updated
    await expect(page.getByText('1/3', { exact: true }).first()).toBeVisible()
  })

  test('booked shift shows in My Bookings summary', async ({ adminPage: page }) => {
    // Pre-book via API
    // eslint-disable-next-line playwright/no-conditional-in-test
    if (shifts.length > 0) {
      await bookShift(page, shifts[0].id)
    }

    await page.goto(`/app/tasks/${created.task.id}`)
    // The "My Bookings" / "Meine Buchungen" heading is inside the main content area
    await expect(
      page
        .getByTestId('main-content')
        .getByText(/my bookings|meine buchungen/i)
        .first(),
    ).toBeVisible()
  })

  test('clicking a booked shift cancels it', async ({ adminPage: page }) => {
    // Pre-book via API
    // eslint-disable-next-line playwright/no-conditional-in-test
    if (shifts.length > 0) {
      await bookShift(page, shifts[0].id)
    }

    await page.goto(`/app/tasks/${created.task.id}`)
    // Wait for booked state to load
    await expect(page.getByText('1/3', { exact: true }).first()).toBeVisible()

    // Click to cancel
    await page.getByText('1/3', { exact: true }).first().click()

    // Handle confirmation dialog (app-level dialog, not browser dialog)
    const confirmBtn = page.getByRole('button', { name: /confirm|bestätigen/i })
    // eslint-disable-next-line playwright/no-conditional-in-test
    if (await confirmBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await confirmBtn.click()
    }

    // Should revert to 0 bookings
    await expect(page.getByText('0/3', { exact: true }).first()).toBeVisible()
  })
})

// ── admin status changes ─────────────────────────────────────────────────────

test.describe('Task Detail – admin actions', () => {
  test('admin can change task status to archived', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)
    // Click the status dropdown (inside the span wrapper)
    const statusEl = page.getByTestId('task-status')
    await expect(statusEl).toBeVisible()
    await statusEl.click()
    await page.getByText(/archived|archiviert/i).click()
    await expect(statusEl).toBeVisible()
  })

  test('admin sees edit button', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)
    await expect(page.getByTestId('btn-edit-task')).toBeVisible()
  })

  test('admin sees delete button', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)
    await expect(page.getByTestId('btn-delete-task')).toBeVisible()
  })

  test('admin sees Add Shifts button', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)
    await expect(page.getByTestId('btn-add-shifts')).toBeVisible()
  })

  test('admin can delete task', async ({ adminPage: page }) => {
    const toDelete = await createTaskWithShifts(page, { name: uniqueName('E2E Delete Me'), status: 'published' })

    await page.goto(`/app/tasks/${toDelete.task.id}`)
    await page.getByTestId('btn-delete-task').click()

    // Confirm in the dialog
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByRole('button', { name: /confirm|delete|yes|bestätigen|löschen|ja/i }).click()

    // Should navigate back to tasks list
    await expect(page).toHaveURL(/\/app\/tasks$/)
  })
})
