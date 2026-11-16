/**
 * E2E tests for the shared-list wizard (`/app/shared-lists/:eventId/new` and
 * `…/:listId/edit`).
 *
 * The rule the wizard exists for (correction (a)): a list is its tasks minus
 * one set of excluded shifts, and a day's checkbox is read off that set. So
 * taking a single shift back in on a day that was left out makes the day
 * mixed, and the list then offers exactly that shift of the day.
 *
 * Every test seeds its own published event, so nothing here touches
 * `workerEvent`; deleting the event takes its lists with it.
 */
import type { Page } from '@playwright/test'

import { expect, serverApi, test } from '../../fixtures.js'
import {
  type EventRead,
  type SharedListDetail,
  type ShiftRead,
  type TaskWithShifts,
  createEvent,
  createSharedList,
  createTaskWithShifts,
  deleteEvent,
  futureDate,
  getSharedList,
  listShifts,
  uniqueName,
} from '../../helpers/api.js'

const FIRST_DAY = futureDate(10)
const SECOND_DAY = futureDate(11)

let event: EventRead
/** Two shifts on each of the two days. */
let kitchen: TaskWithShifts
/** Two shifts on the second day only. */
let bar: TaskWithShifts
let kitchenShifts: ShiftRead[]

function isCreate(eventId: string) {
  return (r: { url(): string; request(): { method(): string } }) =>
    r.request().method() === 'POST' && r.url().endsWith(`/events/${eventId}/shared-lists`)
}

/**
 * Open the wizard and wait for the event it loads first. The view is a lazy
 * route, so on a busy dev server it can take longer to mount than an
 * assertion's default wait; the event request is the sign it has.
 */
async function openWizard(page: Page, path: string, heading: string) {
  const eventRead = page.waitForResponse(
    (r) => r.request().method() === 'GET' && r.url().endsWith(`/events/${event.id}`),
    { timeout: 15_000 },
  )
  await page.goto(path)
  await eventRead
  await expect(page.getByTestId('page-heading')).toHaveText(heading)
}

/** The day cards appear once the chosen tasks' shifts are in. */
async function waitForDays(page: Page) {
  await expect(page.getByTestId(`wizard-day-${FIRST_DAY}`)).toBeVisible()
}

/** Next stays aria-disabled until every chosen task's shifts are in and fine. */
async function goToSettings(page: Page) {
  const next = page.getByTestId('btn-step-next')
  await expect(next).toHaveAttribute('aria-disabled', 'false')
  await next.click()
  await expect(page.getByTestId('step-settings')).toHaveAttribute('data-state', 'active')
}

test.beforeEach(async ({ adminPage: page }) => {
  event = await createEvent(page, uniqueName('E2E Wizard'), 'published', 'public', {
    start: FIRST_DAY,
    end: SECOND_DAY,
  })
  const common = {
    eventId: event.id,
    status: 'published' as const,
    startTime: '10:00',
    endTime: '12:00',
    slotDuration: 60,
    peoplePerShift: 2,
  }
  kitchen = await createTaskWithShifts(page, {
    ...common,
    name: uniqueName('E2E Wizard Kitchen'),
    startDate: FIRST_DAY,
    endDate: SECOND_DAY,
  })
  bar = await createTaskWithShifts(page, {
    ...common,
    name: uniqueName('E2E Wizard Bar'),
    startDate: SECOND_DAY,
    endDate: SECOND_DAY,
  })
  kitchenShifts = await listShifts(page, kitchen.task.id)
})

test.afterEach(async ({ adminPage: page }) => {
  await deleteEvent(page, event.id).catch(() => {})
})

test.describe('Shared list wizard', () => {
  test('a shift taken back in on a left-out day makes the day mixed, and only it goes on the list', async ({
    adminPage: page,
  }) => {
    await openWizard(page, `/app/shared-lists/${event.id}/new`, 'Share a list')

    await page.getByTestId(`wizard-task-check-${kitchen.task.id}`).click()
    await page.getByTestId(`wizard-task-check-${bar.task.id}`).click()
    await waitForDays(page)

    const firstDay = page.getByTestId(`wizard-day-${FIRST_DAY}`)
    await expect(firstDay).toHaveAttribute('data-state', 'checked')
    await page.getByTestId(`wizard-day-check-${FIRST_DAY}`).click()
    await expect(firstDay).toHaveAttribute('data-state', 'unchecked')
    await expect(page.getByTestId(`wizard-day-${SECOND_DAY}`)).toHaveAttribute(
      'data-state',
      'checked',
    )

    const [kept, dropped] = kitchenShifts.filter((s) => s.date === FIRST_DAY)
    await page.getByTestId(`wizard-task-shifts-toggle-${kitchen.task.id}`).click()
    await expect(page.getByTestId(`wizard-shift-check-${kept.id}`)).toHaveAttribute(
      'aria-checked',
      'false',
    )
    await page.getByTestId(`wizard-shift-check-${kept.id}`).click()
    await expect(firstDay).toHaveAttribute('data-state', 'indeterminate')
    await expect(page.getByTestId(`wizard-day-check-${FIRST_DAY}`)).toHaveAttribute(
      'aria-checked',
      'mixed',
    )

    await goToSettings(page)
    await expect(page.getByTestId('wizard-step-position')).toHaveText('Step 2 of 3')
    const [response] = await Promise.all([
      page.waitForResponse(isCreate(event.id)),
      page.getByTestId('btn-submit').click(),
    ])
    expect(response.status()).toBe(201)
    const list = (await response.json()) as SharedListDetail
    expect(list.task_ids).toEqual([kitchen.task.id, bar.task.id])
    expect(list.excluded_shift_ids).toEqual([dropped.id])
  })

  test('sets no limit per person by default, then opens the list with link, text and QR code', async ({
    adminPage: page,
  }) => {
    await openWizard(page, `/app/shared-lists/${event.id}/new`, 'Share a list')
    await page.getByTestId(`wizard-task-check-${kitchen.task.id}`).click()
    await waitForDays(page)
    await goToSettings(page)

    await expect(page.getByTestId('wizard-max-per')).toHaveText('as many as are free')
    await expect(page.getByTestId('wizard-title')).toHaveValue(
      `${kitchen.task.name}: who can help?`,
    )

    const [response] = await Promise.all([
      page.waitForResponse(isCreate(event.id)),
      page.getByTestId('btn-submit').click(),
    ])
    expect(response.status()).toBe(201)
    const list = (await response.json()) as SharedListDetail
    expect(list.max_per_person).toBeNull()

    await expect(page.getByTestId('wizard-step-position')).toHaveText('Step 3 of 3')
    await expect(page.getByTestId('wizard-share-success')).toBeVisible()
    await expect(page.getByTestId('wizard-share-link')).toHaveValue(new RegExp(`/l/${list.code}$`))
    const text = page.getByTestId('wizard-share-message')
    await expect(text).toHaveValue(new RegExp(`“${event.name}”`))
    await expect(text).toHaveValue(new RegExp(`/l/${list.code}$`))
    await expect(page.getByTestId('wizard-share-qr')).toBeVisible()
  })

  test('Back from the new list’s notice returns to the lists, not to the wizard', async ({
    adminPage: page,
  }) => {
    await page.goto(`/app/shared-lists/${event.id}`)
    await page.getByTestId('btn-share-list').click()
    await expect(page.getByTestId('page-heading')).toHaveText('Share a list')
    await page.getByTestId(`wizard-task-check-${kitchen.task.id}`).click()
    await waitForDays(page)
    await goToSettings(page)
    const [response] = await Promise.all([
      page.waitForResponse(isCreate(event.id)),
      page.getByTestId('btn-submit').click(),
    ])
    const list = (await response.json()) as SharedListDetail

    await page.getByTestId('wizard-print-notice').click()
    await expect(page).toHaveURL(new RegExp(`/print/lists/${list.id}$`))
    await page.goBack()

    // An empty wizard here would share the same task a second time.
    await expect(page).toHaveURL(new RegExp(`/app/shared-lists/${event.id}$`))
    await expect(page.getByTestId('shared-lists-page')).toContainText(list.title)
  })

  test('editing keeps the link', async ({ adminPage: page, adminUser }) => {
    const list = await createSharedList(adminUser.email, event.id, {
      title: uniqueName('E2E Wizard List'),
      task_ids: [kitchen.task.id],
    })

    await openWizard(page, `/app/shared-lists/${event.id}/${list.id}/edit`, 'Edit list')
    await waitForDays(page)
    await goToSettings(page)
    await expect(page.getByTestId('wizard-step-position')).toHaveText('Step 2 of 2')
    await expect(page.getByTestId('wizard-title')).toHaveValue(list.title)

    const title = uniqueName('E2E Wizard Renamed')
    await page.getByTestId('wizard-title').fill(title)
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) => r.request().method() === 'PATCH' && r.url().endsWith(`/shared-lists/${list.id}`),
      ),
      page.getByTestId('btn-submit').click(),
    ])
    expect(response.status()).toBe(200)
    expect(response.request().postDataJSON()).toEqual({ title })

    // Back on the lists page, which takes it from there.
    await expect(page).toHaveURL(new RegExp(`/app/shared-lists/${event.id}(\\?|$)`))
    const after = await getSharedList(adminUser.email, list.id)
    expect(after.title).toBe(title)
    expect(after.code).toBe(list.code)
  })

  test('an ended list can be shared again as a new one', async ({ adminPage: page, adminUser }) => {
    const source = await createSharedList(adminUser.email, event.id, {
      title: uniqueName('E2E Wizard Ended'),
      task_ids: [kitchen.task.id, bar.task.id],
    })
    await serverApi('POST', `/shared-lists/${source.id}/end`, adminUser.email)

    await openWizard(page, `/app/shared-lists/${event.id}/new?from=${source.id}`, 'Share a list')
    await expect(page.getByTestId(`wizard-picked-${kitchen.task.id}`)).toBeVisible()
    await expect(page.getByTestId(`wizard-picked-${bar.task.id}`)).toBeVisible()
    await waitForDays(page)
    await goToSettings(page)
    await expect(page.getByTestId('wizard-title')).toHaveValue(source.title)

    const [response] = await Promise.all([
      page.waitForResponse(isCreate(event.id)),
      page.getByTestId('btn-submit').click(),
    ])
    expect(response.status()).toBe(201)
    const copy = (await response.json()) as SharedListDetail
    expect(copy.id).not.toBe(source.id)
    expect(copy.code).not.toBe(source.code)
    expect(copy.task_ids).toEqual(source.task_ids)
    expect((await getSharedList(adminUser.email, source.id)).status).toBe('ended')
  })
})
