/**
 * Accessibility scans of every major route an admin can reach.
 *
 * One scan per route: axe only sees the DOM that is actually rendered, so a
 * dashboard scan says nothing about the task wizard. Each test waits for a
 * stable element first — scanning a half-rendered page produces findings that
 * disappear on the next run.
 */
import { expect, test } from '../../fixtures.js'
import { expectNoA11yViolations } from '../../helpers/a11y.js'
import {
  type TaskWithShifts,
  addMember,
  api,
  createEvent,
  createTaskWithShifts,
  deleteEvent,
  deleteTask,
  uniqueName,
} from '../../helpers/api.js'

test.describe('a11y – admin routes', () => {
  test('dashboard', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'admin dashboard (/app/home)' })
  })

  test('tasks list', async ({ adminPage: page }) => {
    await page.goto('/app/tasks')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'admin tasks list (/app/tasks)' })
  })

  test('task create wizard', async ({ adminPage: page }) => {
    await page.goto('/app/tasks/create')
    await expect(page.getByTestId('section-task-details')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'admin task create (/app/tasks/create)' })
  })

  test('events list', async ({ adminPage: page }) => {
    await page.goto('/app/events')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expect(page.getByTestId('input-search')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'admin events list (/app/events)' })
  })

  test('event detail / settings', async ({ adminPage: page, workerEvent }) => {
    await page.goto(`/app/event-settings/${workerEvent.id}`)
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expect(page.getByTestId('tab-details')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'admin event settings (/app/event-settings/:id)' })
  })

  test('event picker', async ({ adminPage: page }) => {
    await page.goto('/app/select-event?mode=switch')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'admin event picker (/app/select-event)' })
  })

  test('my bookings', async ({ adminPage: page }) => {
    await page.goto('/app/bookings')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'admin bookings (/app/bookings)' })
  })

  test('availability', async ({ adminPage: page }) => {
    await page.goto('/app/availability')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'admin availability (/app/availability)' })
  })

  test('settings', async ({ adminPage: page }) => {
    await page.goto('/app/settings')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'admin settings (/app/settings)' })
  })

  test('admin user management', async ({ adminPage: page }) => {
    await page.goto('/app/admin/users')
    await expect(page.getByTestId('users-table')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'admin users (/app/admin/users)' })
  })
})

// The Teams page with something on it: a team with a requirement and a waiting
// request, then the review dialog. Its own event, so the worker event never
// gains a team (that would add a sidebar entry to every later scan).
test.describe('a11y – admin teams', () => {
  test('teams page and the review dialog', async ({
    adminPage: page,
    disposablePage,
    disposableUser,
  }) => {
    const event = await createEvent(page, uniqueName('E2E a11y Teams'), 'published', 'private')
    try {
      const team = await api<{ id: string }>(page, 'POST', `/events/${event.id}/teams`, {
        name: uniqueName('First aid'),
        requirements: [{ label: 'First aid course', ask_issue_date: true, valid_for_years: 2 }],
      })
      await addMember(page, disposablePage, event.id, disposableUser.email)
      await api(disposablePage, 'POST', `/events/${event.id}/teams/${team.id}/join`, {
        message: 'I did the course last spring.',
      })

      await page.goto(`/app/teams/${event.id}`)
      await expect(page.getByTestId('team-requests')).toBeVisible()
      await expectNoA11yViolations(page, { label: 'admin teams (/app/teams/:id)' })

      await page.locator('[data-testid^="btn-review-team-request-"]').click()
      await expect(page.getByTestId('team-review-dialog')).toBeVisible()
      await expectNoA11yViolations(page, { label: 'team review dialog' })
    } finally {
      await deleteEvent(page, event.id).catch(() => {})
    }
  })
})

// ── Routes that need a task to exist ─────────────────────────────────────────

test.describe('a11y – admin task detail', () => {
  let created: TaskWithShifts

  test.beforeEach(async ({ adminPage: page }) => {
    await page.goto('/app/tasks')
    created = await createTaskWithShifts(page, {
      name: uniqueName('E2E A11y Task'),
      description: 'Fixture for the accessibility scan',
      location: 'Main Hall',
      category: 'Sound',
      status: 'published',
      startTime: '10:00',
      endTime: '12:00',
      slotDuration: 60,
      peoplePerShift: 3,
    })
  })

  test.afterEach(async ({ adminPage: page }) => {
    await deleteTask(page, created.task.id).catch(() => {})
  })

  test('task detail', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)
    await expect(page.getByTestId('page-heading')).toContainText(created.task.name)
    await expect(page.getByTestId('section-shifts')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'admin task detail (/app/tasks/:id)' })
  })
})
