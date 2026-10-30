/**
 * E2E test for volunteer vouchers.
 *
 * A volunteer earns vouchers for a shift that is over, shows their code, and
 * an organiser redeems it at a place that takes vouchers by typing the code.
 * The camera is never used: the redeem page is told there is none, which is
 * also how it behaves on a phone that refuses camera access.
 *
 * Nobody can book a shift that is over, so the volunteer books a future one
 * first and the organiser then moves it to yesterday (organisers may change
 * the past). The shift's task earns nothing until after that, which is the
 * "changes also count for shifts already worked" rule.
 *
 * Each test gets its own event, and the volunteer is a disposable user, so
 * nothing leaks into the shared worker fixtures.
 */
import { expect, test } from '../../fixtures.js'
import {
  type EventRead,
  type TaskRead,
  addMember,
  api,
  bookShift,
  createEvent,
  createTaskWithShifts,
  deleteEvent,
  deleteTask,
  futureDate,
  listShifts,
  setSelectedEvent,
  uniqueName,
} from '../../helpers/api.js'

let event: EventRead
let shiftTask: TaskRead
let pointTask: TaskRead

test.beforeEach(async ({ adminPage, disposablePage, disposableUser }) => {
  event = await createEvent(adminPage, uniqueName('E2E Vouchers'), 'published', 'private', {
    start: futureDate(-1),
    end: futureDate(4),
  })
  const common = {
    eventId: event.id,
    status: 'published' as const,
    startDate: futureDate(2),
    endDate: futureDate(2),
    startTime: '10:00',
    endTime: '12:00',
    slotDuration: 120,
    peoplePerShift: 2,
  }
  shiftTask = (await createTaskWithShifts(adminPage, { ...common, name: uniqueName('E2E Bar') }))
    .task
  pointTask = (
    await createTaskWithShifts(adminPage, { ...common, name: uniqueName('E2E Food stand') })
  ).task
  await addMember(adminPage, disposablePage, event.id, disposableUser.email)
})

test.afterEach(async ({ adminPage }) => {
  // Tasks outlive their event, so they go first.
  await deleteTask(adminPage, shiftTask.id).catch(() => {})
  await deleteTask(adminPage, pointTask.id).catch(() => {})
  await deleteEvent(adminPage, event.id).catch(() => {})
})

test('a volunteer shows their code and an organiser redeems it at a stand', async ({
  adminPage,
  disposablePage,
  disposableUser,
}) => {
  // The volunteer books a shift while it is still ahead; the organiser then
  // moves it to yesterday, so it is over without anyone booking a past shift.
  const [shift] = await listShifts(adminPage, shiftTask.id)
  await bookShift(disposablePage, shift.id)
  await api(adminPage, 'PATCH', `/shifts/${shift.id}`, { date: futureDate(-1) })

  // The organiser sets two vouchers per shift from the task page...
  await adminPage.goto(`/app/tasks/${shiftTask.id}`)
  await adminPage.getByTestId('btn-task-more').click()
  await adminPage.getByTestId('btn-task-vouchers').click()
  const settings = adminPage.getByTestId('task-voucher-settings-dialog')
  await expect(settings).toBeVisible()
  await settings.getByTestId('btn-voucher-per-shift-increase').click()
  await settings.getByTestId('btn-voucher-per-shift-increase').click()
  await settings.getByTestId('btn-save-task-vouchers').click()
  await expect(settings).toBeHidden()
  await expect(adminPage.getByTestId('task-vouchers-per-shift')).toContainText(
    '2 vouchers per shift',
  )

  // ...and makes the other task a place that takes them.
  await adminPage.goto(`/app/tasks/${pointTask.id}`)
  await adminPage.getByTestId('btn-task-more').click()
  await adminPage.getByTestId('btn-task-vouchers').click()
  await expect(settings).toBeVisible()
  await settings.getByTestId('voucher-is-point').click()
  await settings.getByTestId('btn-save-task-vouchers').click()
  await expect(settings).toBeHidden()
  await expect(adminPage.getByTestId('task-voucher-point')).toBeVisible()

  // Only now does the volunteer's session start in this event, so it reads
  // the event with vouchers switched on. From there on, in-app navigation.
  await setSelectedEvent(disposablePage, event.id)
  await disposablePage.goto('/app/home')
  const card = disposablePage.getByTestId('my-vouchers-card')
  await expect(card).toBeVisible()
  await card.getByTestId('btn-my-vouchers-details').click()
  await expect(disposablePage).toHaveURL(new RegExp(`/app/vouchers/${event.id}`))
  const balance = disposablePage.getByTestId('my-vouchers-balance')
  await expect(balance.getByTestId('voucher-available')).toHaveText('2')

  await balance.getByTestId('btn-show-voucher-code').click()
  const codeDialog = disposablePage.getByTestId('voucher-code-dialog')
  const codeText = codeDialog.getByTestId('voucher-code-text')
  await expect(codeText).toHaveText(/^[2-9A-HJKMNP-Z]{3}-[2-9A-HJKMNP-Z]{3}$/)
  const code = (await codeText.textContent())!.trim()

  // The organiser opens the redeem page from the stand. No camera here, so
  // the page says so and opens the typing field by itself.
  await adminPage.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: () => Promise.reject(new DOMException('No camera', 'NotFoundError')),
      },
    })
  })
  await adminPage.goto(`/app/tasks/${pointTask.id}`)
  await adminPage.getByTestId('btn-redeem-vouchers').click()
  await expect(adminPage).toHaveURL(/\/app\/vouchers\/redeem\//)
  await expect(adminPage.getByTestId('voucher-scanner-error')).toBeVisible()

  await adminPage.getByTestId('voucher-code-input').fill(code)
  await adminPage.getByTestId('btn-voucher-check').click()
  const confirm = adminPage.getByTestId('voucher-redeem-confirm')
  await expect(confirm.getByTestId('voucher-redeem-available')).toContainText('has 2 vouchers')
  await confirm.getByTestId('btn-voucher-redeem').click()
  await expect(confirm.getByTestId('voucher-redeem-success')).toContainText(
    `1 redeemed for ${disposableUser.name}. 1 left.`,
  )

  // The volunteer's screen follows within a couple of seconds, with what is left.
  const used = codeDialog.getByTestId('voucher-code-used')
  await expect(used).toContainText(`1 voucher used at ${pointTask.name}`, { timeout: 10_000 })
  await expect(used.getByTestId('voucher-code-left')).toHaveText('1 voucher available')
  await expect(codeDialog.getByTestId('btn-voucher-code-new')).toBeVisible()

  // Showing the same code again at the stand says where it went, and stays.
  await confirm.getByTestId('btn-voucher-next').click()
  await expect(confirm).toBeHidden()
  await adminPage.getByTestId('voucher-code-input').fill(code)
  await adminPage.getByTestId('btn-voucher-check').click()
  await expect(adminPage.getByTestId('voucher-check-problem')).toContainText(
    `Already redeemed: 1 voucher at ${pointTask.name}`,
  )
})

test('a refused camera says so, and a bad code is explained next to the field', async ({
  adminPage,
}) => {
  await api(adminPage, 'PATCH', `/tasks/${pointTask.id}`, { is_voucher_point: true })

  // The browser refuses the camera. qr-scanner reports that as "Camera not
  // found.", so the page asks the permission what happened.
  await adminPage.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: () => Promise.reject(new DOMException('Refused', 'NotAllowedError')),
      },
    })
    Object.defineProperty(navigator, 'permissions', {
      configurable: true,
      value: { query: () => Promise.resolve({ state: 'denied' }) },
    })
  })
  await adminPage.goto(`/app/vouchers/redeem/${event.id}?task=${pointTask.id}`)
  await expect(adminPage.getByTestId('voucher-scanner-error')).toContainText(
    'Camera access was refused',
  )

  // The typing field opened by itself; a code nobody issued is explained in
  // place rather than in a toast, until the next keystroke.
  const problem = adminPage.getByTestId('voucher-check-problem')
  await adminPage.getByTestId('voucher-code-input').fill('K7M4QX')
  await adminPage.getByTestId('btn-voucher-check').click()
  await expect(problem).toContainText("This code isn't valid")
  await adminPage.getByTestId('voucher-code-input').fill('K7M4Q')
  await expect(problem).toBeHidden()
})
