/**
 * E2E tests for the clone wizard (`/app/events/clone/:sourceId`).
 *
 * "Run this event again next year": a new event, the same tasks, the same shift
 * grid, moved by a single offset. The promise the screen makes in three places
 * — `clone-source-untouched`, `review-untouched` and the subtitle — is that the
 * original is left exactly as it is, so that is asserted explicitly rather than
 * assumed.
 *
 * Everything here creates its own source event instead of cloning
 * `workerEvent`: a clone copies the roster and would otherwise keep adding
 * events other workers' tests then have to page past.
 */
import { expect, test } from '../../fixtures.js'
import {
  type EventRead,
  type ShiftRead,
  type TaskRead,
  type TaskWithShifts,
  addMember,
  api,
  createEvent,
  createTaskWithShifts,
  deleteEvent,
  futureDate,
  listShifts,
  uniqueName,
} from '../../helpers/api.js'

/** The wizard's default: 52 weeks, so the weekday survives the move. */
const DEFAULT_OFFSET_DAYS = 364

/** ISO date arithmetic at UTC midnight — the same way the view does it. */
function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

/** Every task of one event. */
async function listTasks(page: import('@playwright/test').Page, eventId: string) {
  const res = await api<{ items: TaskRead[] }>(page, 'GET', `/tasks/?event_id=${eventId}&limit=200`)
  return res.items
}

test.describe('Event clone wizard', () => {
  let source: EventRead
  let taskKept: TaskWithShifts
  let taskDropped: TaskWithShifts
  let keptShifts: ShiftRead[]
  /** Events the test created and must take away again. */
  let created: string[]

  test.beforeEach(async ({ adminPage: page }) => {
    created = []
    source = await createEvent(page, uniqueName('E2E Clone Source'))
    created.push(source.id)

    // Both inside the source window, so the copy lands inside the new one.
    taskKept = await createTaskWithShifts(page, {
      name: uniqueName('E2E Clone Kitchen'),
      eventId: source.id,
      startDate: source.start_date,
      endDate: source.start_date,
      startTime: '10:00',
      endTime: '12:00',
      slotDuration: 60,
      peoplePerShift: 2,
      location: 'Main hall',
    })
    taskDropped = await createTaskWithShifts(page, {
      name: uniqueName('E2E Clone Door'),
      eventId: source.id,
      startDate: source.end_date,
      endDate: source.end_date,
      startTime: '09:00',
      endTime: '11:00',
      slotDuration: 60,
      peoplePerShift: 1,
    })
    keptShifts = await listShifts(page, taskKept.task.id)
  })

  test.afterEach(async ({ adminPage: page }) => {
    for (const id of created) {
      await deleteEvent(page, id).catch(() => {})
    }
  })

  test('event admin reaches the wizard from the events overview', async ({ adminPage: page }) => {
    await page.goto('/app/events')
    // The active list is paginated and every worker is creating events into the
    // same table, so scope to this test's own event before touching a row.
    await page.getByTestId('input-search').fill(source.name)
    const row = page.getByTestId('admin-event-row').filter({ hasText: source.name })
    await expect(row).toHaveCount(1)

    await row.getByTestId('btn-clone-event-row').click()
    await expect(page).toHaveURL(new RegExp(`/app/events/clone/${source.id}$`))

    // The source, summarised: name, dates, how much is coming across, and the
    // promise that none of it moves.
    const summary = page.getByTestId('clone-source-summary')
    await expect(summary).toContainText(source.name)
    await expect(summary).toContainText('2 tasks')
    await expect(page.getByTestId('clone-source-untouched')).toContainText(source.name)

    // Prefilled from the source: "<name> (copy)", 364 days later, whole weeks.
    await expect(page.getByTestId('input-clone-name')).toHaveValue(`${source.name} (copy)`)
    const offset = page.getByTestId('clone-offset-summary')
    await expect(offset).toContainText(`${DEFAULT_OFFSET_DAYS} days later`)
    await expect(offset).toContainText('same day of the week')
  })

  test('picking tasks and walking the steps creates the copy', async ({ adminPage: page }) => {
    const copyName = uniqueName('E2E Cloned Event')
    await page.goto(`/app/events/clone/${source.id}`)
    await expect(page.getByTestId('input-clone-name')).toHaveValue(`${source.name} (copy)`)

    // (a) When — keep the prefilled dates, give the copy a findable name.
    await page.getByTestId('input-clone-name').fill(copyName)
    // The wizard shows one step at a time now: the stepper is the map, and the
    // card's own footer is what moves it on.
    await expect(page.getByTestId('clone-stepper')).toBeVisible()
    await expect(page.getByTestId('step-when')).toHaveAttribute('data-state', 'active')
    await page.getByTestId('btn-step-next').click()

    // (b) What to bring across — everything is picked by default; drop one.
    const tasksSection = page.getByTestId('section-tasks')
    await expect(tasksSection.getByTestId(`check-task-${taskKept.task.id}`)).toBeVisible()
    const droppedBox = tasksSection
      .getByTestId(`check-task-${taskDropped.task.id}`)
      .locator('[data-slot="checkbox"]')
    await expect(droppedBox).toHaveAttribute('data-state', 'checked')
    await droppedBox.click()
    await expect(droppedBox).toHaveAttribute('data-state', 'unchecked')
    await page.getByTestId('btn-step-next').click()

    // (c) Check each task — only the kept one is offered, and it is clean.
    const adjustSection = page.getByTestId('section-adjust')
    await expect(adjustSection.getByTestId(`btn-adjust-task-${taskKept.task.id}`)).toBeVisible()
    await expect(adjustSection.getByTestId(`btn-adjust-task-${taskDropped.task.id}`)).toHaveCount(0)
    await expect(adjustSection.getByTestId('badge-adjust-problems')).toHaveCount(0)

    // A step already behind you is a way back — and the step just left is
    // ticked off rather than merely unvisited.
    await expect(page.getByTestId('step-tasks')).toHaveAttribute('data-state', 'completed')
    await page.getByTestId('step-tasks').click()
    await expect(tasksSection.getByTestId(`check-task-${taskKept.task.id}`)).toBeVisible()
    await page.getByTestId('btn-step-next').click()
    await expect(adjustSection.getByTestId(`btn-adjust-task-${taskKept.task.id}`)).toBeVisible()
    await page.getByTestId('btn-step-next').click()

    // (d) Tell people — the source has only the cloner on it, so there is
    // nobody to write to and the switch is not offered at all.
    const announceSection = page.getByTestId('section-announce')
    await expect(announceSection.getByTestId('announce-nobody')).toBeVisible()
    await page.getByTestId('btn-step-next').click()

    // (e) Look it over.
    const reviewSection = page.getByTestId('section-review')
    await expect(reviewSection.getByTestId('review-untouched')).toContainText(source.name)
    await expect(reviewSection.getByTestId('review-shift-total')).toHaveText(
      String(keptShifts.length),
    )
    await expect(reviewSection.getByTestId(`review-task-${taskKept.task.id}`)).toBeVisible()
    await expect(reviewSection.getByTestId(`review-task-${taskDropped.task.id}`)).toHaveCount(0)

    const [response] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes(`/events/${source.id}/clone`) && r.request().method() === 'POST',
      ),
      page.getByTestId('btn-submit').click(),
    ])
    expect(response.status()).toBe(201)
    const clone = (await response.json()) as {
      event: EventRead
      tasks_created: number
      shifts_created: number
    }
    created.push(clone.event.id)

    // The wizard hands the organiser straight to the new event's settings.
    await expect(page).toHaveURL(new RegExp(`/app/event-settings/${clone.event.id}`))

    // ── the new event, read back from the API ──────────────────────────────
    const copy = await api<EventRead>(page, 'GET', `/events/${clone.event.id}`)
    expect(copy.name).toBe(copyName)
    expect(copy.start_date).toBe(addDays(source.start_date, DEFAULT_OFFSET_DAYS))
    expect(copy.end_date).toBe(addDays(source.end_date, DEFAULT_OFFSET_DAYS))
    // A clone always starts as a draft — publishing is a separate act.
    expect(copy.status).toBe('draft')

    const copiedTasks = await listTasks(page, copy.id)
    expect(copiedTasks.map((t) => t.name)).toEqual([taskKept.task.name])
    const copiedTask = copiedTasks[0]
    expect(copiedTask.start_date).toBe(addDays(taskKept.task.start_date, DEFAULT_OFFSET_DAYS))
    expect(copiedTask.end_date).toBe(addDays(taskKept.task.end_date, DEFAULT_OFFSET_DAYS))

    // "Keep last time's shifts" is the default mode: same grid, new dates.
    const copiedShifts = await listShifts(page, copiedTask.id)
    expect(copiedShifts).toHaveLength(keptShifts.length)
    expect(clone.shifts_created).toBe(keptShifts.length)
    expect(clone.tasks_created).toBe(1)
    expect([...copiedShifts].map((s) => s.date).sort()).toEqual(
      [...keptShifts].map((s) => addDays(s.date, DEFAULT_OFFSET_DAYS)).sort(),
    )
  })

  test('the source event is left exactly as it was', async ({ adminPage: page }) => {
    const before = await api<EventRead>(page, 'GET', `/events/${source.id}`)
    const tasksBefore = await listTasks(page, source.id)
    const droppedShiftsBefore = await listShifts(page, taskDropped.task.id)

    await page.goto(`/app/events/clone/${source.id}`)
    await expect(page.getByTestId('input-clone-name')).toHaveValue(`${source.name} (copy)`)
    await page.getByTestId('input-clone-name').fill(uniqueName('E2E Clone Untouched'))
    for (const step of ['when', 'tasks', 'adjust', 'announce']) {
      await expect(page.getByTestId(`step-${step}`)).toHaveAttribute('data-state', 'active')
      await page.getByTestId('btn-step-next').click()
    }

    const [response] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes(`/events/${source.id}/clone`) && r.request().method() === 'POST',
      ),
      page.getByTestId('btn-submit').click(),
    ])
    const clone = (await response.json()) as { event: EventRead }
    created.push(clone.event.id)
    await expect(page).toHaveURL(new RegExp(`/app/event-settings/${clone.event.id}`))

    // Same dates, same name, same status, same task count, same shifts.
    const after = await api<EventRead>(page, 'GET', `/events/${source.id}`)
    expect(after.name).toBe(before.name)
    expect(after.start_date).toBe(before.start_date)
    expect(after.end_date).toBe(before.end_date)
    expect(after.status).toBe(before.status)
    expect(after.visibility).toBe(before.visibility)

    const tasksAfter = await listTasks(page, source.id)
    expect(tasksAfter).toHaveLength(tasksBefore.length)
    expect([...tasksAfter].map((t) => t.id).sort()).toEqual(
      [...tasksBefore].map((t) => t.id).sort(),
    )
    for (const task of tasksAfter) {
      const original = tasksBefore.find((t) => t.id === task.id)
      expect(original).toBeDefined()
      expect(task.start_date).toBe(original?.start_date)
      expect(task.end_date).toBe(original?.end_date)
    }

    expect(await listShifts(page, taskKept.task.id)).toHaveLength(keptShifts.length)
    expect(await listShifts(page, taskDropped.task.id)).toHaveLength(droppedShiftsBefore.length)
  })

  test('an event admin who is not the platform superadmin may open it', async ({
    adminPage: page,
    disposableUser,
    disposablePage: organiser,
  }) => {
    // `adminUser` holds the platform `admin` role, for which `canManageEvent`
    // answers yes about every event in the database — so the guard on this
    // screen is only really exercised by an account whose sole claim is the
    // membership row. Cloning is a mutation, so the invitee is disposable.
    await addMember(page, organiser, source.id, disposableUser.email, 'admin')

    await organiser.goto('/app/events')
    await organiser.getByTestId('input-search').fill(source.name)
    const row = organiser.getByTestId('admin-event-row').filter({ hasText: source.name })
    await expect(row).toHaveCount(1)

    await row.getByTestId('btn-clone-event-row').click()
    await expect(organiser).toHaveURL(new RegExp(`/app/events/clone/${source.id}$`))
    await expect(organiser.getByTestId('clone-source-summary')).toContainText(source.name)
    await expect(organiser.getByTestId('input-clone-name')).toHaveValue(`${source.name} (copy)`)
  })
})

// ── refusals ──────────────────────────────────────────────────────────────────

test.describe('Event clone wizard – who may not open it', () => {
  test('a plain participant is bounced off the wizard', async ({
    adminPage: admin,
    memberPage: member,
  }) => {
    const source = await createEvent(admin, uniqueName('E2E Clone Denied'))
    try {
      // `requiresEventManager`: this account runs no event at all, so the
      // router never lets the screen mount.
      await member.goto(`/app/events/clone/${source.id}`)
      await expect(member).toHaveURL(/\/app\/home/)
      await expect(member.getByTestId('clone-source-summary')).toHaveCount(0)
    } finally {
      await deleteEvent(admin, source.id).catch(() => {})
    }
  })

  test('running some other event does not open the wizard for this one', async ({
    adminPage: admin,
    disposablePage: outsider,
  }) => {
    const source = await createEvent(admin, uniqueName('E2E Clone Outsider'))
    // Creating an event makes this account its owner, which satisfies
    // `requiresEventManager` — the view's own `canManageEvent(sourceId)` check
    // is the only thing left standing between them and someone else's event.
    const own = await api<EventRead>(outsider, 'POST', '/events/', {
      name: uniqueName('E2E Clone Outsider Own'),
      status: 'draft',
      visibility: 'private',
      start_date: futureDate(10),
      end_date: futureDate(12),
    })
    try {
      await outsider.goto(`/app/events/clone/${source.id}`)
      await expect(outsider).toHaveURL(/\/app\/events$/)
      await expect(outsider.getByTestId('clone-source-summary')).toHaveCount(0)
    } finally {
      await deleteEvent(outsider, own.id).catch(() => {})
      await deleteEvent(admin, source.id).catch(() => {})
    }
  })
})
