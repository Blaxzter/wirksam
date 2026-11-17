/**
 * Shared lists and the people in charge of tasks.
 *
 * A person in charge shares their own task and manages that list; a list that
 * also holds someone else's task is theirs to read, not to change; a plain
 * member has neither the page nor the API. Once an event admin turns sharing
 * off for people in charge, they may still pause, but not reopen or create.
 *
 * Each test seeds its own event; the person in charge is a disposable user.
 */
import { expect, test } from '../../fixtures.js'
import { API, addMember, api, apiStatus, createSharedList } from '../../helpers/api.js'
import {
  type SharedListEvent,
  removeSharedListEvent,
  seedSharedListEvent,
} from '../../helpers/shared-list-seed.js'

let seeded: SharedListEvent | undefined

test.beforeEach(async ({ adminPage, disposablePage, disposableUser }) => {
  seeded = await seedSharedListEvent(adminPage, 'E2E In Charge Lists', ['Waffeln', 'Grill'])
  await addMember(adminPage, disposablePage, seeded.event.id, disposableUser.email)
  // In charge of the first task only.
  await api(adminPage, 'POST', `/tasks/${seeded.tasks[0].task.id}/managers`, {
    user_id: disposableUser.id,
  })
})

test.afterEach(async ({ adminPage }) => {
  await removeSharedListEvent(adminPage, seeded)
  seeded = undefined
})

test('a person in charge shares their task and manages that list', async ({
  disposablePage,
  disposableUser,
}) => {
  const [waffeln] = seeded!.tasks
  const list = await createSharedList(disposableUser.email, seeded!.event.id, {
    title: 'Waffeln für alle',
    task_ids: [waffeln.task.id],
  })

  await disposablePage.goto(`/app/shared-lists/${seeded!.event.id}`)
  await expect(disposablePage.getByTestId('page-heading')).toHaveText('Shared lists')
  const row = disposablePage.getByTestId(`shared-list-row-${list.id}`)
  await expect(row).toContainText('Waffeln für alle')
  await expect(row.getByTestId('shared-list-select')).toBeEnabled()
  await expect(row.getByTestId('shared-list-pause')).toBeEnabled()

  // They see their own task only, and may share it.
  await disposablePage.getByTestId('tab-tasks').click()
  await expect(disposablePage.getByTestId('shared-list-tasks-scope')).toBeVisible()
  await expect(disposablePage.getByTestId(`shared-list-task-${waffeln.task.id}`)).toBeVisible()
  await expect(
    disposablePage.getByTestId(`shared-list-task-${seeded!.tasks[1].task.id}`),
  ).toHaveCount(0)

  await disposablePage.getByTestId('btn-share-list').click()
  await expect(disposablePage).toHaveURL(new RegExp(`/app/shared-lists/${seeded!.event.id}/new`))
})

test('a list with someone else’s task is read-only for them, and says why', async ({
  adminUser,
  disposablePage,
}) => {
  const list = await createSharedList(adminUser.email, seeded!.event.id, {
    title: 'Alles fürs Fest',
    task_ids: seeded!.tasks.map(({ task }) => task.id),
  })

  await disposablePage.goto(`/app/shared-lists/${seeded!.event.id}`)
  const row = disposablePage.getByTestId(`shared-list-row-${list.id}`)
  await expect(row).toBeVisible()
  await expect(row.getByTestId('shared-list-select')).toBeDisabled()
  await expect(row.getByTestId('shared-list-pause')).toBeDisabled()

  await row.getByTestId('shared-list-title').click()
  const detail = disposablePage.getByTestId('shared-list-detail')
  await expect(detail.getByTestId('shared-list-detail-readonly')).toContainText(
    'only the organisers can change it',
  )
  await expect(detail.getByTestId('shared-list-detail-actions')).toHaveCount(0)
  expect(await apiStatus(disposablePage, 'POST', `/shared-lists/${list.id}/pause`)).toBe(403)
})

test('a plain member has no page and no access', async ({ memberPage, workerEvent }) => {
  await expect(memberPage.getByTestId('sidebar-link-shared-lists')).toHaveCount(0)

  // `apiStatus` keeps the status only; the code says which refusal it was.
  const res = await memberPage.evaluate(async (url) => {
    const response = await fetch(url)
    return { status: response.status, body: (await response.json()) as { code?: string } }
  }, `${API}/events/${workerEvent.id}/shared-lists`)
  expect(res.status).toBe(403)
  expect(res.body.code).toBe('shared_list.forbidden')
})

test('with sharing off, a person in charge can pause but not reopen or create', async ({
  adminPage,
  disposablePage,
  disposableUser,
}) => {
  const [waffeln] = seeded!.tasks
  const list = await createSharedList(disposableUser.email, seeded!.event.id, {
    title: 'Waffeln am Samstag',
    task_ids: [waffeln.task.id],
  })

  // The admin turns sharing off for people in charge, on the page.
  await adminPage.goto(`/app/shared-lists/${seeded!.event.id}`)
  const saved = adminPage.waitForResponse(
    (r) => r.url().endsWith(`/events/${seeded!.event.id}`) && r.request().method() === 'PATCH',
  )
  await adminPage.getByTestId('shared-lists-managers-switch').click()
  await saved
  await expect(adminPage.getByTestId('shared-lists-managers-switch')).toHaveAttribute(
    'aria-checked',
    'false',
  )

  await disposablePage.goto(`/app/shared-lists/${seeded!.event.id}`)
  await expect(disposablePage.getByTestId('shared-lists-managers-off')).toBeVisible()
  await expect(disposablePage.getByTestId('btn-share-list')).toHaveCount(0)

  const row = disposablePage.getByTestId(`shared-list-row-${list.id}`)
  await row.getByTestId('shared-list-pause').click()
  await expect(row.getByTestId('shared-list-status')).toHaveAttribute('data-status', 'paused')
  await expect(row.getByTestId('shared-list-resume')).toBeDisabled()

  expect(await apiStatus(disposablePage, 'POST', `/shared-lists/${list.id}/resume`)).toBe(403)
  expect(
    await apiStatus(disposablePage, 'POST', `/events/${seeded!.event.id}/shared-lists`, {
      title: 'Noch eine',
      task_ids: [waffeln.task.id],
    }),
  ).toBe(403)
})
