/**
 * The management page of shared lists, as an event admin.
 *
 * Every test seeds an event of its own (`helpers/shared-list-seed.ts`), so the
 * worker's event never gains a list. Lists are created and guests sign up
 * through the API, as a group chat would; the page is what is under test.
 */
import type { Page } from '@playwright/test'

import { expect, serverApi, test } from '../../fixtures.js'
import {
  type PublicSignupResult,
  type SharedListDetail,
  createSharedList,
  getSharedList,
  guestMailLink,
  publicSignup,
} from '../../helpers/api.js'
import {
  type SharedListEvent,
  guestEmail,
  removeSharedListEvent,
  seedSharedListEvent,
} from '../../helpers/shared-list-seed.js'

let seeded: SharedListEvent | undefined

test.afterEach(async ({ adminPage }) => {
  await removeSharedListEvent(adminPage, seeded)
  seeded = undefined
})

/** Open the page of the seeded event and wait for its first page of lists. */
async function openPage(page: Page, query = '') {
  const lists = page.waitForResponse(
    (r) => /\/events\/[^/]+\/shared-lists(\?|$)/.test(r.url()) && r.request().method() === 'GET',
    { timeout: 15_000 },
  )
  await page.goto(`/app/shared-lists/${seeded!.event.id}${query}`)
  await lists
  await expect(page.getByTestId('page-heading')).toHaveText('Shared lists')
}

const row = (page: Page, id: string) => page.getByTestId(`shared-list-row-${id}`)

async function tick(page: Page, id: string) {
  await row(page, id).getByTestId('shared-list-select').click()
}

/**
 * "Remove" on one sign-up in the open details, from the keyboard; resolves to
 * the request body. Email to the person is ticked by default and stays so
 * unless `untickNotify`. The row goes, and focus goes to the section's heading.
 */
async function removeSignup(page: Page, name: string, options: { untickNotify: boolean }) {
  const detail = page.getByTestId('shared-list-detail')
  const task = seeded!.tasks[0].task.name
  const remove = detail
    .getByTestId('shared-list-signup')
    .filter({ hasText: name })
    .getByTestId('shared-list-signup-remove')
  // The button names the shift as well: the same person can be down for several.
  await expect(remove).toHaveAttribute('aria-label', new RegExp(`^Remove ${name} \\(${task}, `))
  await remove.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByTestId('shared-list-remove-dialog')
  await expect(dialog).toContainText(`Remove “${name}” from “${task}”?`)
  const notify = dialog.getByTestId('shared-list-remove-notify')
  await expect(notify).toHaveAttribute('aria-checked', 'true')
  if (options.untickNotify) await notify.click()

  const removal = page.waitForRequest((r) => r.url().endsWith('/signups/remove'))
  await dialog.getByTestId('shared-list-remove-confirm').click()
  const body = (await removal).postDataJSON() as Record<string, unknown>
  await expect(detail.getByTestId('shared-list-signup').filter({ hasText: name })).toHaveCount(0)
  await expect(detail.getByRole('heading', { name: 'Signed up through this link' })).toBeFocused()
  return body
}

async function signUp(
  list: SharedListDetail,
  name: string,
  { email = guestEmail(name), shift = 0 } = {},
): Promise<PublicSignupResult> {
  const res = await publicSignup(list.code, {
    shift_id: seeded!.tasks[0].shifts[shift].id,
    name,
    email,
    show_names: list.show_names,
    language: 'en',
  })
  expect(res.status, JSON.stringify(res.body)).toBe(201)
  return res.body as PublicSignupResult
}

/** "Ja, das bin ich" from the sign-up's mail, which pools it under its address. */
async function confirmFromMail(signup: PublicSignupResult): Promise<void> {
  const token = await guestMailLink(signup.guest_token)
  await serverApi('POST', '/public/guest-signups/confirm', '', { token })
}

test.describe('a page of 25 lists', () => {
  let lists: SharedListDetail[]

  test.beforeEach(async ({ adminPage, adminUser }) => {
    seeded = await seedSharedListEvent(adminPage, 'E2E Many Lists')
    const taskId = seeded.tasks[0].task.id
    lists = []
    for (let i = 1; i <= 25; i += 1) {
      lists.push(
        await createSharedList(adminUser.email, seeded.event.id, {
          title: `Liste ${String(i).padStart(2, '0')}`,
          task_ids: [taskId],
        }),
      )
    }
  })

  test('the sidebar leads to the page, and the chips count the lists', async ({ adminPage }) => {
    await adminPage.getByTestId('sidebar-link-shared-lists').click()
    // The router commits the URL once the lazy page has loaded, which on a
    // busy dev server takes longer than an assertion's default wait.
    await expect(adminPage).toHaveURL(/\/app\/shared-lists/, { timeout: 15_000 })
    await expect(adminPage.getByTestId('page-heading')).toHaveText('Shared lists')

    await openPage(adminPage)
    await expect(adminPage.getByTestId('filter-chip-active')).toContainText('25')
    await expect(adminPage.getByTestId('filter-chip-live')).toContainText('25')
    await expect(adminPage.getByTestId('filter-chip-ended')).toContainText('0')
    await expect(adminPage.getByTestId('tab-links-count')).toHaveText('25')
  })

  test('counts the lists on the Links tab when the page opens on another tab', async ({
    adminPage,
  }) => {
    const overview = adminPage.waitForResponse((r) => r.url().endsWith('/shared-lists/overview'), {
      timeout: 15_000,
    })
    await adminPage.goto(`/app/shared-lists/${seeded!.event.id}?tab=preview`)
    await overview
    await expect(adminPage.getByTestId('tab-links-count')).toHaveText('25')
  })

  test('sorts by title both ways, on the server', async ({ adminPage }) => {
    await openPage(adminPage)
    const firstTitle = adminPage
      .getByTestId('shared-lists-table')
      .getByTestId('shared-list-title')
      .first()

    await adminPage.getByTestId('sort-title').click()
    await expect(adminPage).toHaveURL(/sort=title/)
    await expect(firstTitle).toHaveText('Liste 01')
    await expect(adminPage.getByTestId('sort-title').locator('xpath=..')).toHaveAttribute(
      'aria-sort',
      'ascending',
    )

    await adminPage.getByTestId('sort-title').click()
    await expect(adminPage).toHaveURL(/dir=desc/)
    await expect(firstTitle).toHaveText('Liste 25')
  })

  test('the second page has the rest, and turning the page clears the selection', async ({
    adminPage,
  }) => {
    await openPage(adminPage, '?sort=title')
    await tick(adminPage, lists[0].id)
    await expect(adminPage.getByTestId('selection-bar')).toBeVisible()

    await adminPage
      .getByTestId('list-pagination')
      .getByRole('button', { name: 'Page 2 of 2' })
      .click()

    await expect(adminPage).toHaveURL(/page=2/)
    await expect(
      adminPage.getByTestId('shared-lists-table').getByTestId('shared-list-title'),
    ).toHaveCount(5)
    await expect(adminPage.getByTestId('selection-bar')).toHaveCount(0)
  })
})

test.describe('one event, a few lists', () => {
  let lists: SharedListDetail[]

  test.beforeEach(async ({ adminPage, adminUser }) => {
    seeded = await seedSharedListEvent(adminPage, 'E2E Few Lists', ['Kuchen', 'Kasse'])
    const [kuchen] = seeded.tasks
    lists = []
    for (const title of ['Eltern', 'Aushang', 'Verein']) {
      lists.push(
        await createSharedList(adminUser.email, seeded.event.id, {
          title,
          task_ids: [kuchen.task.id],
        }),
      )
    }
  })

  test('pauses, resumes and ends ticked lists together', async ({ adminPage, adminUser }) => {
    await openPage(adminPage)
    const [a, b] = lists

    await tick(adminPage, a.id)
    await tick(adminPage, b.id)
    await adminPage.getByTestId('selection-action-pause').click()
    await expect(adminPage.getByText('2 lists paused.')).toBeVisible()
    await expect(row(adminPage, a.id).getByTestId('shared-list-status')).toHaveAttribute(
      'data-status',
      'paused',
    )

    await tick(adminPage, a.id)
    await tick(adminPage, b.id)
    await adminPage.getByTestId('selection-action-resume').click()
    await expect(adminPage.getByText('2 lists are open again.')).toBeVisible()

    await tick(adminPage, a.id)
    await tick(adminPage, b.id)
    await adminPage.getByTestId('selection-action-end').click()
    await expect(adminPage.getByTestId('selection-confirm')).toContainText('End 2 lists?')
    await adminPage.getByTestId('shared-lists-bulk-end-confirm').click()

    await expect(adminPage.getByText('2 lists ended.')).toBeVisible()
    await expect(row(adminPage, a.id)).toHaveCount(0)
    await expect(adminPage.getByTestId('filter-chip-ended')).toContainText('2')
    expect((await getSharedList(adminUser.email, a.id)).effective_status).toBe('ended')
  })

  test('copies the link, renews it, and ends the list from its details', async ({ adminPage }) => {
    await adminPage.context().grantPermissions(['clipboard-read', 'clipboard-write'])
    const [list] = lists
    await openPage(adminPage)

    await row(adminPage, list.id).getByTestId('shared-list-title').click()
    const detail = adminPage.getByTestId('shared-list-detail')
    await expect(detail).toBeVisible()
    await expect(adminPage).toHaveURL(new RegExp(`list=${list.id}`))

    await detail.getByTestId('shared-list-link-copy').click()
    await expect(adminPage.getByText('Link copied.')).toBeVisible()
    const copied = await adminPage.evaluate(() => navigator.clipboard.readText())
    expect(copied).toMatch(new RegExp(`/l/${list.code}$`))

    const rotated = adminPage.waitForResponse((r) =>
      r.url().endsWith(`/shared-lists/${list.id}/rotate`),
    )
    await detail.getByTestId('shared-list-detail-rotate').click()
    await adminPage.getByTestId('btn-dialog-confirm').click()
    await rotated
    await expect(detail.getByTestId('shared-list-url')).not.toContainText(list.code)
    const old = await publicSignup(list.code, {
      shift_id: seeded!.tasks[0].shifts[0].id,
      name: 'Too Late',
      show_names: 'none',
    })
    expect(old.status).toBe(404)

    await detail.getByTestId('shared-list-detail-end').click()
    await adminPage.getByTestId('btn-dialog-confirm').click()
    await expect(detail.getByTestId('shared-list-status')).toHaveAttribute('data-status', 'ended')
    await expect(detail.getByTestId('shared-list-detail-share-again')).toBeVisible()
  })

  test('takes a sign-up off, with and without telling them by email', async ({ adminPage }) => {
    const [list] = lists
    await signUp(list, 'Mia Quiet')
    await signUp(list, 'Ben Told')
    await openPage(adminPage, `?list=${list.id}`)

    const detail = adminPage.getByTestId('shared-list-detail')
    const signups = detail.getByTestId('shared-list-signup')
    await expect(signups).toHaveCount(2)
    // The figures keep their height in a details box tall enough to scroll.
    await expect(detail.getByTestId('shared-list-figure-signups')).toHaveText('2')
    const figures = await detail.getByTestId('shared-list-figures').boundingBox()
    expect(figures!.height).toBeGreaterThan(40)

    // Telling them is on until it is turned off, as for spam.
    expect(await removeSignup(adminPage, 'Mia Quiet', { untickNotify: true })).toMatchObject({
      notify: false,
    })
    expect(await removeSignup(adminPage, 'Ben Told', { untickNotify: false })).toMatchObject({
      notify: true,
    })
    await expect(signups).toHaveCount(0)

    await expect(detail.getByTestId('shared-list-signups-empty')).toBeVisible()
    await expect(detail.getByTestId('shared-list-figure-signups')).toHaveText('0')
  })

  test('deleting the data of a confirmed address names the sign-ups that go along', async ({
    adminPage,
  }) => {
    // One family address, two people, both sign-ups confirmed into one account.
    const [list] = lists
    const email = guestEmail('pool family')
    await confirmFromMail(await signUp(list, 'Xaver Pool', { email }))
    await confirmFromMail(await signUp(list, 'Yvonne Pool', { email, shift: 1 }))
    await openPage(adminPage, `?list=${list.id}`)

    const detail = adminPage.getByTestId('shared-list-detail')
    const signups = detail.getByTestId('shared-list-signup')
    await expect(signups).toHaveCount(2)
    await signups
      .filter({ hasText: 'Yvonne Pool' })
      .getByTestId('shared-list-signup-remove')
      .click()
    const dialog = adminPage.getByTestId('shared-list-remove-dialog')
    await expect(dialog.getByTestId('shared-list-remove-erase-pooled')).toHaveText(
      "1 more sign-up is confirmed under the same email address, maybe someone else's. It is deleted too.",
    )
    await dialog.getByTestId('shared-list-remove-erase').click()
    await dialog.getByTestId('shared-list-remove-confirm').click()

    await expect(adminPage.getByText('2 sign-ups removed.')).toBeVisible()
    await expect(signups).toHaveCount(0)
  })

  test('"this and all newer ones" takes the later sign-ups off', async ({ adminPage }) => {
    const [list] = lists
    await signUp(list, 'Anna First')
    await signUp(list, 'Bert Second')
    await signUp(list, 'Cleo Third')
    await openPage(adminPage, `?list=${list.id}`)

    const signups = adminPage.getByTestId('shared-list-detail').getByTestId('shared-list-signup')
    await expect(signups).toHaveCount(3)

    await signups.filter({ hasText: 'Bert Second' }).getByTestId('shared-list-signup-menu').click()
    await adminPage.getByTestId('shared-list-signup-remove-since').click()
    const dialog = adminPage.getByTestId('shared-list-remove-dialog')
    await expect(dialog).toContainText('Remove this sign-up and all newer ones?')
    await dialog.getByTestId('shared-list-remove-notify').click()
    await dialog.getByTestId('shared-list-remove-confirm').click()

    await expect(adminPage.getByText('2 sign-ups removed.')).toBeVisible()
    await expect(signups).toHaveCount(1)
    await expect(signups.first()).toContainText('Anna First')
  })

  test('keeps keyboard focus on the control that was used', async ({ adminPage }) => {
    const [list] = lists
    await openPage(adminPage)
    const listRow = row(adminPage, list.id)

    // A row's pause turns into resume in place.
    await listRow.getByTestId('shared-list-pause').focus()
    await adminPage.keyboard.press('Enter')
    await expect(listRow.getByTestId('shared-list-resume')).toBeFocused()

    // Clearing the selection from its bar hands focus back to the table.
    await listRow.getByTestId('shared-list-select').focus()
    await adminPage.keyboard.press('Space')
    await adminPage.getByTestId('selection-clear').focus()
    await adminPage.keyboard.press('Enter')
    await expect(adminPage.getByTestId('selection-bar')).toHaveCount(0)
    await expect(adminPage.getByTestId('shared-lists-select-all')).toBeFocused()

    // In the details, too, and the dialog keeps it.
    await listRow.getByTestId('shared-list-title').click()
    const detail = adminPage.getByTestId('shared-list-detail')
    await detail.getByTestId('shared-list-detail-resume').focus()
    await adminPage.keyboard.press('Enter')
    await expect(detail.getByTestId('shared-list-detail-pause')).toBeFocused()
  })

  test('the tasks tab names the task whose places no open list offers', async ({ adminPage }) => {
    const [kuchen, kasse] = seeded!.tasks
    await openPage(adminPage)

    await expect(adminPage.getByTestId('unshared-tasks-notice')).toContainText(kasse.task.name)
    await adminPage.getByTestId('unshared-tasks-show').click()

    await expect(adminPage).toHaveURL(/tab=tasks/)
    await expect(adminPage.getByTestId('filter-chip-todo')).toHaveAttribute('aria-pressed', 'true')
    await expect(adminPage.getByTestId(`shared-list-task-${kasse.task.id}`)).toBeVisible()
    await expect(adminPage.getByTestId(`shared-list-task-${kuchen.task.id}`)).toHaveCount(0)

    await adminPage.getByTestId('filter-chip-all').click()
    await expect(
      adminPage.getByTestId(`shared-list-task-${kuchen.task.id}`).getByTestId('task-list-chip'),
    ).toHaveCount(3)
  })
})
