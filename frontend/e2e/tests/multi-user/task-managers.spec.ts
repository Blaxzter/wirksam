/**
 * E2E tests for the people in charge of a task.
 *
 * An organiser puts an event member in charge of a task from the task page.
 * That member can then edit the task and its shifts, but cannot delete or
 * publish it: the draft banner asks them to get an organiser to publish. On a
 * task that earns vouchers the shifts stay with the organisers unless the
 * event's voucher rules allow people in charge to change them.
 *
 * Someone not in the event yet is invited by typing their address into the
 * same dialog: they get an event invitation that names the task, and
 * accepting it puts them in charge.
 *
 * Each test gets its own event, and the person in charge is a disposable
 * user, so nothing leaks into the shared worker fixtures.
 */
import type { Page } from '@playwright/test'

import type { EventInvitationRead } from '../../../src/client/types.gen.js'
import { expect, test } from '../../fixtures.js'
import {
  type EventRead,
  type TaskRead,
  addMember,
  api,
  apiStatus,
  bookShift,
  createEvent,
  createTaskWithShifts,
  deleteEvent,
  deleteTask,
  futureDate,
  listShifts,
  uniqueName,
} from '../../helpers/api.js'
import { pickDate } from '../../helpers/ui.js'

let event: EventRead
let task: TaskRead
/** Tasks a test creates through the form, for the clean-up. */
let createdTaskIds: string[] = []

test.beforeEach(async ({ adminPage, disposablePage, disposableUser, disposableUserOptions }) => {
  event = await createEvent(adminPage, uniqueName('E2E In Charge'), 'published', 'private', {
    start: futureDate(1),
    end: futureDate(4),
  })
  const created = await createTaskWithShifts(adminPage, {
    name: uniqueName('E2E Bar'),
    eventId: event.id,
    status: 'draft',
    startDate: futureDate(2),
    endDate: futureDate(2),
    startTime: '10:00',
    endTime: '12:00',
    slotDuration: 60,
    peoplePerShift: 2,
  })
  task = created.task
  // The invitation tests start with someone who is in no event at all.
  if (disposableUserOptions.joinWorkerEvent !== false) {
    await addMember(adminPage, disposablePage, event.id, disposableUser.email)
  }
})

test.afterEach(async ({ adminPage }) => {
  // Tasks outlive their event, so they go first; the task takes its people
  // in charge with it.
  for (const id of createdTaskIds) await deleteTask(adminPage, id).catch(() => {})
  createdTaskIds = []
  await deleteTask(adminPage, task.id).catch(() => {})
  await deleteEvent(adminPage, event.id).catch(() => {})
})

test('an organiser puts a member in charge from the task page', async ({
  adminPage,
  disposableUser,
}) => {
  await adminPage.goto(`/app/tasks/${task.id}`)
  await adminPage.getByTestId('btn-task-more').click()
  await adminPage.getByTestId('btn-task-managers').click()

  const dialog = adminPage.getByTestId('task-managers-dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog.getByTestId('task-managers-empty')).toBeVisible()

  // Picking is the action: the highlighted match is added on Enter.
  const search = dialog.getByTestId('task-add-manager')
  await search.click()
  await search.fill(disposableUser.name)
  await expect(adminPage.getByTestId(`task-add-manager-option-${disposableUser.id}`)).toBeVisible()
  await search.press('Enter')

  await expect(dialog.getByTestId(`task-manager-row-${disposableUser.id}`)).toBeVisible()
  await expect(adminPage.getByTestId('task-managers')).toContainText(disposableUser.name)

  const saved = await api<TaskRead>(adminPage, 'GET', `/tasks/${task.id}`)
  expect(saved.managers?.map((m) => m.user_id)).toEqual([disposableUser.id])
})

test('a person in charge edits the task and adds a shift, but cannot delete or publish it', async ({
  adminPage,
  disposablePage,
  disposableUser,
}) => {
  await api(adminPage, 'POST', `/tasks/${task.id}/managers`, { user_id: disposableUser.id })
  const shiftsBefore = (await listShifts(adminPage, task.id)).length

  await disposablePage.goto(`/app/tasks/${task.id}`)
  await expect(disposablePage.getByTestId('page-heading')).toHaveText(task.name)

  // A draft they can see, but only an organiser can publish.
  await expect(disposablePage.getByTestId('task-draft-banner')).toContainText(
    'The organisers can publish it.',
  )
  await expect(disposablePage.getByTestId('task-you-are-in-charge')).toBeVisible()
  await expect(disposablePage.getByTestId('btn-edit-task')).toBeVisible()
  await expect(disposablePage.getByTestId('btn-delete-task')).toHaveCount(0)
  expect(
    await apiStatus(disposablePage, 'PATCH', `/tasks/${task.id}`, { status: 'published' }),
  ).toBe(403)

  // Rename it. The team is the organisers' call, so that card is not offered.
  const renamed = uniqueName('E2E Bar renamed')
  await disposablePage.getByTestId('btn-edit-task').click()
  await expect(disposablePage).toHaveURL(new RegExp(`/app/tasks/${task.id}/edit`))
  await expect(disposablePage.getByTestId('section-schedule')).toBeVisible()
  await expect(disposablePage.getByTestId('section-who-can-book')).toHaveCount(0)
  await disposablePage.getByTestId('input-task-name').fill(renamed)
  await disposablePage.getByTestId('btn-submit').click()
  await expect(disposablePage).toHaveURL(new RegExp(`/app/tasks/${task.id}$`))
  await expect(disposablePage.getByTestId('page-heading')).toHaveText(renamed)

  // Add a single shift on another day of the task.
  await disposablePage.getByTestId('btn-add-shifts').click()
  await disposablePage.getByTestId('btn-add-single-shift').click()
  const dialog = disposablePage.getByTestId('dialog-create-shift')
  await expect(dialog).toBeVisible()
  await dialog.getByTestId('input-shift-title').fill('Late shift')
  await pickDate(dialog.getByRole('button', { name: 'Pick a date' }), futureDate(2))
  await dialog.getByTestId('btn-create-shift').click()
  await expect(dialog).toBeHidden()

  await expect
    .poll(async () => (await listShifts(adminPage, task.id)).length)
    .toBe(shiftsBefore + 1)
})

test('the shifts of a voucher task stay with the organisers until the event lets people in charge change them', async ({
  adminPage,
  disposablePage,
  disposableUser,
}) => {
  // Two people through the task page, its edit form, the event's settings and
  // a reload: with a full set of local workers this nears the default 30
  // seconds.
  test.slow()

  // A second batch of shifts. Each batch then has its own edit, which changes
  // shifts, so the task's own edit has to stay for the details.
  await api(adminPage, 'POST', `/tasks/${task.id}/add-shifts`, {
    start_date: futureDate(3),
    end_date: futureDate(3),
    schedule: {
      default_start_time: '14:00:00',
      default_end_time: '16:00:00',
      shift_duration_minutes: 60,
      people_per_shift: 2,
    },
  })
  await api(adminPage, 'PATCH', `/tasks/${task.id}`, { vouchers_per_shift: 2 })
  await api(adminPage, 'POST', `/tasks/${task.id}/managers`, { user_id: disposableUser.id })

  // The details are still theirs; the shifts are not, and the page says why.
  await disposablePage.goto(`/app/tasks/${task.id}`)
  await expect(disposablePage.getByTestId('page-heading')).toHaveText(task.name)
  await expect(disposablePage.getByTestId('task-voucher-shifts-locked')).toBeVisible()
  await expect(disposablePage.getByTestId('btn-add-shifts')).toHaveCount(0)
  await expect(disposablePage.getByTestId('btn-edit-task')).toBeVisible()

  // Editing offers the details only, and saving them leaves the shifts alone.
  const shiftsBefore = (await listShifts(adminPage, task.id)).length
  const renamed = uniqueName('E2E Bar renamed')
  await disposablePage.getByTestId('btn-edit-task').click()
  await expect(disposablePage).toHaveURL(new RegExp(`/app/tasks/${task.id}/edit`))
  await expect(disposablePage.getByTestId('task-voucher-shifts-locked')).toBeVisible()
  await expect(disposablePage.getByTestId('section-schedule')).toHaveCount(0)
  await disposablePage.getByTestId('input-task-name').fill(renamed)
  await disposablePage.getByTestId('btn-submit').click()
  await expect(disposablePage).toHaveURL(new RegExp(`/app/tasks/${task.id}$`))
  await expect(disposablePage.getByTestId('page-heading')).toHaveText(renamed)
  expect(await listShifts(adminPage, task.id)).toHaveLength(shiftsBefore)

  // The organiser allows it in the event's voucher rules.
  await adminPage.goto(`/app/event-settings/${event.id}?tab=vouchers`)
  const rules = adminPage.getByTestId('section-event-voucher-rules')
  await expect(rules).toBeVisible()
  await expect(rules.getByTestId('voucher-manual-on_shift')).toHaveAttribute(
    'data-state',
    'checked',
  )
  await rules.getByTestId('switch-managers-edit-voucher-shifts').click()
  await rules.getByTestId('btn-save-voucher-rules').click()
  await expect(adminPage.locator('[data-sonner-toast]')).toContainText('Voucher rules saved.')
  const saved = await api<EventRead>(adminPage, 'GET', `/events/${event.id}`)
  expect(saved.managers_edit_voucher_shifts).toBe(true)

  await disposablePage.reload()
  await expect(disposablePage.getByTestId('page-heading')).toHaveText(renamed)
  await expect(disposablePage.getByTestId('btn-add-shifts')).toBeVisible()
  await expect(disposablePage.getByTestId('task-voucher-shifts-locked')).toHaveCount(0)
  // With the shifts theirs again, each batch's own edit takes over.
  await expect(disposablePage.getByTestId('btn-edit-task')).toHaveCount(0)
})

test('a person in charge opens a shift and sees who is on it and how to reach them', async ({
  adminPage,
  adminUser,
  disposablePage,
  disposableUser,
}) => {
  await api(adminPage, 'POST', `/tasks/${task.id}/managers`, { user_id: disposableUser.id })
  const [shift] = await listShifts(adminPage, task.id)
  const booking = await bookShift(adminPage, shift.id)
  await api(adminPage, 'PATCH', `/bookings/${booking.id}`, { notes: 'Bringing the till key.' })

  await disposablePage.goto(`/app/tasks/${task.id}`)
  await disposablePage.getByTestId(`shift-card-${shift.id}`).click()

  const dialog = disposablePage.getByTestId('dialog-shift-detail')
  await expect(dialog.getByTestId('shift-in-charge-names')).toHaveText('You')
  await expect(dialog.getByTestId('shift-roster-count')).toHaveText('1 of 2, 1 place free')

  // The organiser's booking, with what only those who run the task get to see.
  const row = dialog.getByTestId('shift-roster-entry')
  await expect(row).toHaveCount(1)
  await expect(row.getByTestId('shift-roster-note')).toHaveText('Bringing the till key.')
  await expect(row.getByTestId('shift-roster-email')).toHaveAttribute(
    'href',
    `mailto:${adminUser.email}`,
  )
  await expect(dialog.getByTestId('shift-roster-free')).toContainText('1 place free')

  // And they can take a place themselves.
  await expect(dialog.getByTestId('btn-book-shift')).toHaveText('Sign me up')
})

test('a person in charge steps down from the task page', async ({
  adminPage,
  disposablePage,
  disposableUser,
}) => {
  await api(adminPage, 'POST', `/tasks/${task.id}/managers`, { user_id: disposableUser.id })

  await disposablePage.goto(`/app/tasks/${task.id}`)
  await expect(disposablePage.getByTestId('task-you-are-in-charge')).toBeVisible()
  await disposablePage.getByTestId('btn-task-step-down').click()
  const confirm = disposablePage.getByRole('dialog')
  await expect(confirm).toContainText('Step down?')
  // The task is a draft, so it drops out of sight as well; the prompt says so.
  await expect(confirm).toContainText("It isn't published")
  await disposablePage.getByTestId('btn-dialog-confirm').click()

  await expect(disposablePage).toHaveURL(/\/app\/tasks$/)
  const saved = await api<TaskRead>(adminPage, 'GET', `/tasks/${task.id}`)
  expect(saved.managers ?? []).toEqual([])
})

/** Open the task's "People in charge" dialog as the organiser. */
async function openManagersDialog(adminPage: Page) {
  await adminPage.goto(`/app/tasks/${task.id}`)
  await adminPage.getByTestId('btn-task-more').click()
  await adminPage.getByTestId('btn-task-managers').click()
  const dialog = adminPage.getByTestId('task-managers-dialog')
  await expect(dialog).toBeVisible()
  return dialog
}

test.describe('inviting by e-mail', () => {
  test.use({ disposableUserOptions: { joinWorkerEvent: false } })

  test('an organiser invites an address, and its owner accepts and is in charge of the task', async ({
    adminPage,
    disposablePage,
    disposableUser,
  }) => {
    const dialog = await openManagersDialog(adminPage)

    // An address no member has is offered as an invitation; Enter sends it.
    const search = dialog.getByTestId('task-add-manager')
    await search.click()
    await search.fill(disposableUser.email)
    await expect(adminPage.getByTestId('task-add-manager-invite')).toBeVisible()
    await search.press('Enter')

    await expect(dialog.getByTestId('task-managers-status')).toContainText(
      `Invitation sent to ${disposableUser.email}`,
    )
    const row = dialog.getByTestId(`task-manager-invitation-${disposableUser.email}`)
    await expect(row).toContainText('Invited')
    // The task page lists it under "In charge" too, waiting for an answer.
    await expect(
      adminPage.getByTestId(`task-in-charge-invitation-${disposableUser.email}`),
    ).toContainText('Waiting for them to accept')

    // The invitation is an ordinary event invitation that names the task.
    const invitations = await api<EventInvitationRead[]>(
      adminPage,
      'GET',
      `/events/${event.id}/invitations`,
    )
    const invitation = invitations.find((i) => i.email === disposableUser.email)
    expect(invitation?.tasks?.map((t) => t.name)).toEqual([task.name])

    // The invitee sees the task on the invitation and lands on it, in charge.
    await disposablePage.goto(`/invite/${invitation!.token}`)
    await expect(disposablePage.getByTestId('invite-tasks')).toContainText(task.name)
    await disposablePage.getByTestId('btn-accept-invite').click()
    await expect(disposablePage).toHaveURL(new RegExp(`/app/tasks/${task.id}$`))
    await expect(disposablePage.getByTestId('page-heading')).toHaveText(task.name)
    await expect(disposablePage.getByTestId('task-you-are-in-charge')).toBeVisible()

    const saved = await api<TaskRead>(adminPage, 'GET', `/tasks/${task.id}`)
    expect(saved.managers?.map((m) => m.user_id)).toEqual([disposableUser.id])
  })

  test('an organiser withdraws an invitation to be in charge', async ({ adminPage }) => {
    const email = `e2e-withdraw-${Date.now()}-${Math.random().toString(36).slice(2, 6)}@test.example.com`
    await api(adminPage, 'POST', `/tasks/${task.id}/managers/invite`, { email })

    const dialog = await openManagersDialog(adminPage)
    const row = dialog.getByTestId(`task-manager-invitation-${email}`)
    await expect(row).toBeVisible()
    await row.getByTestId('btn-invitation-withdraw').click()
    await adminPage.getByTestId('btn-dialog-confirm').click()

    await expect(row).toHaveCount(0)
    await expect(dialog.getByTestId('task-managers-status')).toContainText('Invitation withdrawn.')
    await expect(dialog.getByTestId('task-managers-empty')).toBeVisible()
    expect(
      await api<unknown[]>(adminPage, 'GET', `/tasks/${task.id}/managers/invitations`),
    ).toEqual([])
  })

  test('an organiser puts an invited address in charge once it has joined the event another way', async ({
    adminPage,
    disposablePage,
    disposableUser,
  }) => {
    await api(adminPage, 'POST', `/tasks/${task.id}/managers/invite`, {
      email: disposableUser.email,
    })
    // A share link makes them a member and leaves the task invitation open.
    const link = await api<{ token: string }>(
      adminPage,
      'POST',
      `/events/${event.id}/invitations`,
      { role: 'member' },
    )
    await api(disposablePage, 'POST', `/invitations/${link.token}/accept`)

    const dialog = await openManagersDialog(adminPage)
    const row = dialog.getByTestId(`task-manager-invitation-${disposableUser.email}`)
    await expect(row).toContainText('Already in the event now')
    await row.getByTestId('btn-invitation-add-now').click()

    await expect(dialog.getByTestId(`task-manager-row-${disposableUser.id}`)).toBeVisible()
    await expect(row).toHaveCount(0)
    const saved = await api<TaskRead>(adminPage, 'GET', `/tasks/${task.id}`)
    expect(saved.managers?.map((m) => m.user_id)).toEqual([disposableUser.id])
  })

  test('an organiser invites an address while creating a task', async ({ adminPage }) => {
    const stamp = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    const email = `e2e-create-${stamp}@test.example.com`
    const dropped = `e2e-dropped-${stamp}@test.example.com`
    // Passes the picker's loose check; the server refuses the underscore.
    const refused = `e2e-refused-${stamp}@ex_ample.de`
    const name = uniqueName('E2E Bar invite')

    await adminPage.goto(`/app/tasks/create?eventId=${event.id}`)
    await adminPage.getByTestId('input-task-name').fill(name)
    await adminPage
      .getByTestId('section-task-details')
      .getByRole('button', { name: 'Next', exact: true })
      .click()

    // A typed address no member has becomes an "invited" chip.
    const managers = adminPage.getByTestId('section-task-managers')
    const search = managers.getByTestId('task-create-manager')
    const invite = async (address: string) => {
      await search.click()
      await search.fill(address)
      await expect(adminPage.getByTestId('task-create-manager-invite')).toBeVisible()
      await search.press('Enter')
    }
    await invite(email)
    await expect(managers.getByTestId(`task-create-manager-email-${email}`)).toContainText(
      'will be invited',
    )
    // The same address again, in other letters, is not a second chip.
    await invite(email.toUpperCase())
    // One added by mistake comes off again.
    await invite(dropped)
    await managers.getByRole('button', { name: `Remove the invitation to ${dropped}` }).click()
    await expect(managers.getByTestId(/^task-create-manager-email-/)).toHaveCount(1)
    await invite(refused)

    const next = (section: string) =>
      adminPage.getByTestId(section).getByRole('button', { name: 'Next', exact: true }).click()
    await next('section-event')
    await pickDate(
      adminPage.getByTestId('section-task-dates').getByRole('button', { name: 'Pick a date' }),
      futureDate(2),
    )
    await next('section-task-dates')
    await next('section-schedule')
    await adminPage.getByTestId('btn-submit').click()

    // The refused address is named, its chip marked, and nothing is created.
    await expect(adminPage.locator('[data-sonner-toast]')).toContainText([
      `This e-mail address can't be used: ${refused}`,
    ])
    const refusedChip = managers.getByTestId(`task-create-manager-email-${refused}`)
    await expect(refusedChip).toHaveAttribute('data-refused', 'true')
    await expect(adminPage).toHaveURL(/\/app\/tasks\/create/)
    await managers.getByRole('button', { name: `Remove the invitation to ${refused}` }).click()
    await expect(refusedChip).toHaveCount(0)

    await next('section-event')
    await next('section-task-dates')
    await next('section-schedule')
    await adminPage.getByTestId('btn-submit').click()

    await expect(adminPage).toHaveURL(/\/app\/tasks\/[0-9a-f-]{36}$/)
    const createdId = adminPage.url().split('/').at(-1)!
    createdTaskIds.push(createdId)
    await expect(adminPage.locator('[data-sonner-toast]')).toContainText(['Invitation sent'])

    // One invitation, to the address that stayed, naming the new task.
    const invitations = await api<EventInvitationRead[]>(
      adminPage,
      'GET',
      `/events/${event.id}/invitations`,
    )
    const sent = invitations.filter((i) => i.tasks?.some((t) => t.task_id === createdId))
    expect(sent.map((i) => i.email)).toEqual([email])
    expect(invitations.some((i) => i.email === dropped)).toBe(false)
  })
})
