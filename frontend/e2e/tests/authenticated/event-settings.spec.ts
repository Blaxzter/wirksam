/**
 * E2E tests for /app/event-settings — the former "Details" and "Management"
 * tabs from the removed /app/events/:id page, promoted to a top-level route
 * that reads from the user's selected_event_id (or an explicit ?eventId=).
 */
import { expect, test } from '../../fixtures.js'
import {
  type EventRead,
  type TaskRead,
  api,
  createTaskWithShifts,
  createEvent,
  deleteTask,
  deleteEvent,
  futureDate,
  uniqueName,
} from '../../helpers/api.js'

// ── Edit event details ───────────────────────────────────────────────────────

test.describe('Event Settings – details tab', () => {
  let event: EventRead

  test.beforeEach(async ({ adminPage: page }) => {
    event = await createEvent(page, uniqueName('E2E Edit'))
  })

  test.afterEach(async ({ adminPage: page }) => {
    await deleteEvent(page, event.id).catch(() => {})
  })

  test('details tab is the default view', async ({ adminPage: page }) => {
    await page.goto(`/app/event-settings/${event.id}`)
    await expect(page.getByTestId('tab-details')).toBeVisible()
    await expect(page.getByRole('textbox').first()).toBeVisible()
  })

  test('edit form is pre-filled with the target event data', async ({ adminPage: page }) => {
    await page.goto(`/app/event-settings/${event.id}`)
    await expect(page.locator('input').first()).toHaveValue(event.name)
  })

  test('can update event name via edit form', async ({ adminPage: page }) => {
    await page.goto(`/app/event-settings/${event.id}`)

    const newName = uniqueName('E2E Renamed')
    await page.locator('input').first().fill(newName)
    await page.getByRole('button', { name: /save|speichern/i }).click()

    // Name is persisted — subtitle under the heading shows the event name
    await expect(page.getByText(newName).first()).toBeVisible()
  })

  test('can update event description', async ({ adminPage: page }) => {
    await page.goto(`/app/event-settings/${event.id}`)
    await page.locator('textarea').first().fill('Updated via E2E test')

    // Wait for the PATCH to settle before reading back — clicking save and
    // GETing immediately races the request and intermittently sees the old
    // (null) description.
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes(`/events/${event.id}`) &&
          resp.request().method() === 'PATCH' &&
          resp.ok(),
      ),
      page.getByRole('button', { name: /save|speichern/i }).click(),
    ])

    const updated = await api<EventRead>(page, 'GET', `/events/${event.id}`)
    expect(updated.description).toBe('Updated via E2E test')
  })

  test('a draft can be published and made public', async ({ adminPage: page }) => {
    const draft = await createEvent(page, uniqueName('E2E Draft'), 'draft')
    try {
      await page.goto(`/app/event-settings/${draft.id}`)
      await expect(page.getByTestId('btn-event-status-draft')).toHaveAttribute(
        'aria-pressed',
        'true',
      )

      await page.getByTestId('btn-visibility-public').click()
      await expect(page.getByTestId('public-unpublished-note')).toBeVisible()
      await page.getByTestId('btn-event-status-published').click()
      await expect(page.getByTestId('public-unpublished-note')).toBeHidden()

      await Promise.all([
        page.waitForResponse(
          (resp) =>
            resp.url().includes(`/events/${draft.id}`) &&
            resp.request().method() === 'PATCH' &&
            resp.ok(),
        ),
        page.getByRole('button', { name: /save|speichern/i }).click(),
      ])

      const updated = await api<EventRead>(page, 'GET', `/events/${draft.id}`)
      expect(updated.status).toBe('published')
      expect(updated.visibility).toBe('public')
    } finally {
      await deleteEvent(page, draft.id).catch(() => {})
    }
  })

  test('falls back to selected event when no eventId query is provided', async ({
    adminPage: page,
    workerEvent,
  }) => {
    await page.goto('/app/event-settings')
    await expect(page.locator('input').first()).toHaveValue(workerEvent.name)
  })
})

// ── Edit with tasks (date constraints) ──────────────────────────────────────

test.describe('Event Settings – date constraints', () => {
  let event: EventRead
  let task: TaskRead

  test.beforeEach(async ({ adminPage: page }) => {
    event = await api<EventRead>(page, 'POST', '/events/', {
      name: uniqueName('E2E Constrained'),
      status: 'published',
      start_date: futureDate(30),
      end_date: futureDate(34),
    })
    const created = await createTaskWithShifts(page, {
      name: uniqueName('E2E Constraint Task'),
      startDate: futureDate(31),
      endDate: futureDate(32),
      eventId: event.id,
    })
    task = created.task
  })

  test.afterEach(async ({ adminPage: page }) => {
    await deleteTask(page, task?.id).catch(() => {})
    await deleteEvent(page, event.id).catch(() => {})
  })

  test('shows calendar legend when tasks exist', async ({ adminPage: page }) => {
    await page.goto(`/app/event-settings/${event.id}`)
    // Legend labels use the "task" noun (Task start / Task end / Task day)
    await expect(page.getByText(/task.?start|veranstaltungs.?beginn/i)).toBeVisible()
  })

  test('shows task boundary hints', async ({ adminPage: page }) => {
    await page.goto(`/app/event-settings/${event.id}`)
    await expect(page.getByText(/earliest|früheste/i)).toBeVisible()
  })

  test('shows shift-dates card when tasks exist', async ({ adminPage: page }) => {
    await page.goto(`/app/event-settings/${event.id}`)
    await expect(
      page.getByRole('heading', { name: /shift dates|termine verschieben/i }),
    ).toBeVisible()
  })

  test('API rejects end_date before earliest task start', async ({ adminPage: page }) => {
    try {
      await api(page, 'PATCH', `/events/${event.id}`, { end_date: futureDate(29) })
      expect(true, 'Expected 422 but request succeeded').toBe(false)
    } catch (e) {
      // eslint-disable-next-line playwright/no-conditional-expect
      expect(String(e)).toContain('422')
    }
  })
})

// ── Shift dates ──────────────────────────────────────────────────────────────

test.describe('Event Settings – shift dates', () => {
  let event: EventRead
  let task: TaskRead

  test.beforeEach(async ({ adminPage: page }) => {
    event = await api<EventRead>(page, 'POST', '/events/', {
      name: uniqueName('E2E Shift'),
      status: 'published',
      start_date: futureDate(30),
      end_date: futureDate(34),
    })
    const created = await createTaskWithShifts(page, {
      name: uniqueName('E2E Shift Task'),
      startDate: futureDate(31),
      endDate: futureDate(32),
      eventId: event.id,
    })
    task = created.task
  })

  test.afterEach(async ({ adminPage: page }) => {
    await deleteTask(page, task?.id).catch(() => {})
    await deleteEvent(page, event.id).catch(() => {})
  })

  test('shift-dates API shifts event start forward', async ({ adminPage: page }) => {
    const newStart = futureDate(37)
    const shifted = await api<EventRead>(page, 'POST', `/events/${event.id}/shift-dates`, {
      new_start_date: newStart,
    })
    expect(shifted.start_date).toBe(newStart)
  })

  test('shift-dates API shifts task dates along with the event', async ({ adminPage: page }) => {
    const originalTaskStart = task.start_date
    await api(page, 'POST', `/events/${event.id}/shift-dates`, {
      new_start_date: futureDate(37),
    })

    const updatedTask = await api<TaskRead>(page, 'GET', `/tasks/${task.id}`)
    expect(updatedTask.start_date).not.toBe(originalTaskStart)
  })

  test('shift-dates with same start date is a no-op', async ({ adminPage: page }) => {
    const shifted = await api<EventRead>(page, 'POST', `/events/${event.id}/shift-dates`, {
      new_start_date: event.start_date,
    })
    expect(shifted.start_date).toBe(event.start_date)
    expect(shifted.end_date).toBe(event.end_date)
  })

  test('shift-dates card is hidden when the event has no tasks', async ({ adminPage: page }) => {
    const emptyEvent = await createEvent(page, uniqueName('E2E Empty Shift'))
    try {
      await page.goto(`/app/event-settings/${emptyEvent.id}`)
      await expect(page.getByText(/shift dates|termine verschieben/i)).toBeHidden()
    } finally {
      await deleteEvent(page, emptyEvent.id)
    }
  })
})

// ── Member restrictions ─────────────────────────────────────────────────────

test.describe('Event Settings – member restrictions', () => {
  let event: EventRead

  test.beforeEach(async ({ adminPage: page }) => {
    event = await createEvent(page, uniqueName('E2E Member Edit'))
  })

  test.afterEach(async ({ adminPage: page }) => {
    await deleteEvent(page, event.id).catch(() => {})
  })

  test('a non-member cannot see the event settings content', async ({
    memberPage: member,
  }) => {
    // The route itself is open — access is decided per event. This event was
    // created by the admin and the member was never invited, so it is 404 to
    // them and no editing surface renders.
    await member.goto(`/app/event-settings/${event.id}`)
    await expect(member.getByTestId('section-event-members')).toBeHidden()
    await expect(member.getByTestId('tab-people')).toBeHidden()
  })

  test('member cannot shift dates via API', async ({ memberPage: member }) => {
    try {
      await api(member, 'POST', `/events/${event.id}/shift-dates`, {
        new_start_date: futureDate(40),
      })
      expect(true, 'Expected 403 but request succeeded').toBe(false)
    } catch (e) {
      // eslint-disable-next-line playwright/no-conditional-expect
      expect(String(e)).toContain('403')
    }
  })
})
