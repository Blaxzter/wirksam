/**
 * Printing a notice people sign up from without an account: a task's "Print"
 * reuses the list of exactly that task (a paused one too) or creates one after
 * asking, a whole event's sheets share one list that outlasts a full task, and
 * a list's details print its notice. Whoever cannot share the task gets its
 * sheet without a QR code. On A4 the times stay on one line and a heading with
 * its shifts.
 *
 * Every test but the member's seeds an event of its own
 * (`helpers/shared-list-seed.ts`), so the worker's event never gains a list.
 */
import type { Locator, Page } from '@playwright/test'

import { expect, test } from '../../fixtures.js'
import {
  type TaskWithShifts,
  api,
  bookShift,
  createSharedList,
  createTaskWithShifts,
  deleteTask,
  futureDate,
  getSharedList,
  listShifts,
  uniqueName,
} from '../../helpers/api.js'
import {
  type SharedListEvent,
  removeSharedListEvent,
  seedSharedListEvent,
} from '../../helpers/shared-list-seed.js'

let seeded: SharedListEvent | undefined

test.afterEach(async ({ adminPage }) => {
  await removeSharedListEvent(adminPage, seeded)
  seeded = undefined
})

/** "Print" in the task page's ⋯ menu, where organisers find it. */
async function printFromTaskPage(page: Page, taskId: string) {
  await page.goto(`/app/tasks/${taskId}`)
  await page.getByTestId('btn-task-more').click()
  await page.getByTestId('btn-print').click()
}

const printButton = (page: Page) => page.getByRole('button', { name: 'Print', exact: true })

/** The sheet's QR code leads to the list's public page. */
async function expectListQr(
  page: Page,
  listId: string,
  email: string,
  sheet: Page | Locator = page,
) {
  const list = await getSharedList(email, listId)
  await expect(sheet.getByTestId('print-qr').getByRole('img')).toHaveAttribute(
    'alt',
    new RegExp(`/l/${list.code}$`),
  )
  return list
}

test.describe('a task’s notice', () => {
  test('reuses the open list of exactly that task', async ({ adminPage: page, adminUser }) => {
    seeded = await seedSharedListEvent(page, 'E2E Print Reuse', ['Kuchen', 'Kasse'])
    const [cake, till] = seeded.tasks.map((t) => t.task)
    // A list of both tasks is not the one: it holds more than this task.
    await createSharedList(adminUser.email, seeded.event.id, {
      title: 'Beide',
      task_ids: [cake!.id, till!.id],
    })
    const own = await createSharedList(adminUser.email, seeded.event.id, {
      title: 'Nur Kuchen',
      task_ids: [cake!.id],
    })
    // The page shows before its shifts arrive, and "Print" judges by them:
    // pressed early, it has to wait for them rather than find no free place.
    // `fallback` hands the request on to the fixture's route, which signs it.
    await page.route(/\/api\/v1\/shifts\/\?/, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1_000))
      await route.fallback()
    })

    await printFromTaskPage(page, cake!.id)

    await expect(page).toHaveURL(new RegExp(`/print/lists/${own.id}$`))
    await expect(page.getByTestId('print-content').locator('h1')).toHaveText('Nur Kuchen')
    await expectListQr(page, own.id, adminUser.email)
    await expect(page.getByText('Scan to sign up, no account needed')).toBeVisible()
  })

  test('asks once, creates a list with the defaults and prints its sheet', async ({
    adminPage: page,
    adminUser,
  }) => {
    seeded = await seedSharedListEvent(page, 'E2E Print Create')
    const { task, shifts } = seeded.tasks[0]!

    await printFromTaskPage(page, task.id)

    const dialog = page.getByTestId('shared-list-print-dialog')
    await expect(dialog).toContainText("We'll make a shared list for the notice")
    await expect(dialog.getByTestId('shared-list-print-title')).toHaveText(task.name)
    await expect(dialog.getByTestId('shared-list-setting-asked')).toHaveText('name and email')
    await dialog.getByTestId('shared-list-print-create').click()

    await expect(page).toHaveURL(/\/print\/lists\/[0-9a-f-]+$/)
    const listId = page.url().split('/').pop()!
    const list = await expectListQr(page, listId, adminUser.email)
    expect(list.task_ids).toEqual([task.id])
    expect([list.title, list.ask_email, list.show_names, list.ends_mode]).toEqual([
      task.name,
      'required',
      'none',
      'last_shift',
    ])
    // Every shift ahead, each with a line per free place (three, nobody booked).
    await expect(page.getByTestId('print-shift-free')).toHaveCount(shifts.length)
    await expect(page.getByTestId('print-shift-line')).toHaveCount(shifts.length * 3)

    await page.getByTestId('print-toggle-paper-lines').click()
    await expect(page.getByTestId('print-shift-line')).toHaveCount(shifts.length)
  })

  test('opens its paused list’s notice rather than making a second list', async ({
    adminPage: page,
    adminUser,
  }) => {
    seeded = await seedSharedListEvent(page, 'E2E Print Paused Task')
    const { task } = seeded.tasks[0]!
    const list = await createSharedList(adminUser.email, seeded.event.id, {
      title: 'Pausiert',
      task_ids: [task.id],
    })
    await api(page, 'POST', `/shared-lists/${list.id}/pause`)

    await printFromTaskPage(page, task.id)

    await expect(page).toHaveURL(new RegExp(`/print/lists/${list.id}$`))
    await expect(page.getByTestId('print-list-status')).toContainText('The list is paused.')
    await expect(page.getByTestId('print-list-fix')).toBeVisible()
    await expect(page.getByTestId('shared-list-print-dialog')).toHaveCount(0)
  })

  test('"Adjust first" opens the wizard with the task picked', async ({ adminPage: page }) => {
    seeded = await seedSharedListEvent(page, 'E2E Print Adjust')
    const { task } = seeded.tasks[0]!

    await printFromTaskPage(page, task.id)
    await page.getByTestId('shared-list-print-customize').click()

    await expect(page).toHaveURL(
      new RegExp(`/app/shared-lists/${seeded.event.id}/new\\?tasks=${task.id}$`),
    )
    await expect(page.getByTestId(`wizard-task-check-${task.id}`)).toBeVisible()
  })
})

test.describe('a member’s print', () => {
  let created: TaskWithShifts | undefined

  test.afterEach(async ({ adminPage }) => {
    if (created) await deleteTask(adminPage, created.task.id).catch(() => {})
    created = undefined
  })

  test('is the task’s sheet without a QR code, and makes no list', async ({
    adminPage,
    memberPage: member,
    workerEvent,
  }) => {
    created = await createTaskWithShifts(adminPage, {
      name: uniqueName('E2E Member Print'),
      status: 'published',
      eventId: workerEvent.id,
      startTime: '09:00',
      endTime: '11:00',
      slotDuration: 60,
      peoplePerShift: 2,
    })
    // The print neither looks a list up nor creates one.
    const listCalls: string[] = []
    member.on('request', (request) => {
      if (/\/shared-lists(\/reusable)?$/.test(new URL(request.url()).pathname)) {
        listCalls.push(`${request.method()} ${request.url()}`)
      }
    })

    await member.goto(`/app/tasks/${created.task.id}`)
    await member.getByTestId('btn-print').click()

    await expect(member).toHaveURL(new RegExp(`/print/tasks/${created.task.id}$`))
    await expect(member.getByTestId('print-content')).toContainText(created.task.name)
    await expect(member.getByTestId('print-shift-line')).toHaveCount(4)
    await expect(member.getByTestId('print-qr')).toHaveCount(0)
    expect(listCalls).toEqual([])
  })
})

test.describe('the whole event’s sheets', () => {
  test('share one list, and a team-only task prints without its QR code', async ({
    adminPage: page,
    adminUser,
  }) => {
    seeded = await seedSharedListEvent(page, 'E2E Print All', ['Kuchen', 'Bar'])
    const [cake, bar] = seeded.tasks.map((t) => t.task)
    const team = await api<{ id: string }>(page, 'POST', `/events/${seeded.event.id}/teams`, {
      name: uniqueName('Thekenteam'),
    })
    await api(page, 'PATCH', `/tasks/${bar!.id}`, { team_id: team.id })

    await page.goto(`/print/events/${seeded.event.id}?mode=all`)

    const dialog = page.getByTestId('shared-list-print-dialog')
    await expect(dialog.getByTestId('shared-list-print-title')).toHaveText(
      `${seeded.event.name} – all tasks`,
    )
    await expect(dialog.getByTestId('shared-list-print-left-out')).toContainText(
      `“${bar!.name}” is for one team only.`,
    )
    await dialog.getByTestId('shared-list-print-create').click()

    await expect(page).toHaveURL(/mode=all&list=[0-9a-f-]+$/)
    // The question opened with the page: focus goes on to printing, not to the page's top.
    await expect(printButton(page)).toBeFocused()
    const listId = new URL(page.url()).searchParams.get('list')!
    const sheets = page.getByTestId('print-sheet')
    const cakeSheet = sheets.filter({ hasText: cake!.name })
    const barSheet = sheets.filter({ hasText: bar!.name })
    const list = await expectListQr(page, listId, adminUser.email, cakeSheet)
    expect(list.task_ids).toEqual([cake!.id])
    await expect(barSheet.getByTestId('print-qr')).toHaveCount(0)
    await expect(barSheet.getByTestId('print-shift-free')).toHaveCount(0)

    // Printing again finds the same list without asking.
    await page.goto(`/print/events/${seeded.event.id}?mode=all`)
    await expect(page).toHaveURL(new RegExp(`list=${listId}$`))
    await expect(page.getByTestId('shared-list-print-dialog')).toHaveCount(0)
  })

  test('keep their list once a task is full', async ({ adminPage: page }) => {
    seeded = await seedSharedListEvent(page, 'E2E Print Full')
    // One shift with one place, so a single booking fills the task.
    const { task: stall } = await createTaskWithShifts(page, {
      name: uniqueName('E2E Print Full Stand'),
      eventId: seeded.event.id,
      status: 'published',
      startDate: futureDate(2),
      endDate: futureDate(2),
      startTime: '15:00',
      endTime: '16:00',
      slotDuration: 60,
      peoplePerShift: 1,
    })
    const [only] = await listShifts(page, stall.id)
    seeded.tasks.push({ task: stall, shifts: [only!] })

    await page.goto(`/print/events/${seeded.event.id}?mode=all`)
    await page.getByTestId('shared-list-print-create').click()
    await expect(page).toHaveURL(/list=[0-9a-f-]+$/)
    const listId = new URL(page.url()).searchParams.get('list')!

    await bookShift(page, only!.id)
    await page.goto(`/print/events/${seeded.event.id}?mode=all`)

    // The same list, not a second one without the full task.
    await expect(page).toHaveURL(new RegExp(`list=${listId}$`))
    await expect(page.getByTestId('shared-list-print-dialog')).toHaveCount(0)
    const stallSheet = page.getByTestId('print-sheet').filter({ hasText: stall.name })
    await expect(stallSheet.getByTestId('print-qr')).toBeVisible()
    await expect(stallSheet.getByTestId('print-shift-free')).toHaveText('0')
  })

  test('hand focus to printing when the question is closed', async ({ adminPage: page }) => {
    seeded = await seedSharedListEvent(page, 'E2E Print Focus')

    await page.goto(`/print/events/${seeded.event.id}?mode=all`)
    const dialog = page.getByTestId('shared-list-print-dialog')
    await expect(dialog).toBeVisible()
    await page.keyboard.press('Escape')

    await expect(dialog).toHaveCount(0)
    await expect(printButton(page)).toBeFocused()
  })
})

test.describe('a notice on A4', () => {
  test('keeps each task’s heading with its shifts and the times on one line', async ({
    adminPage: page,
    adminUser,
  }) => {
    seeded = await seedSharedListEvent(page, 'E2E Print A4', ['Kuchen', 'Kasse'])
    const taskIds = seeded.tasks.map(({ task }) => task.id)
    // Vouchers add the last column, which squeezed the times.
    for (const id of taskIds) await api(page, 'PATCH', `/tasks/${id}`, { vouchers_per_shift: 2 })
    const list = await createSharedList(adminUser.email, seeded.event.id, {
      title: 'Aushang',
      task_ids: taskIds,
    })

    // An A4 page less its 10 mm margins, in CSS pixels.
    await page.setViewportSize({ width: 718, height: 1000 })
    await page.emulateMedia({ media: 'print' })
    await page.goto(`/print/lists/${list.id}`)

    const headings = page.getByTestId('print-content').locator('section h2')
    await expect(headings).toHaveCount(2)
    for (const heading of await headings.all()) {
      await expect(heading).toHaveCSS('break-after', 'avoid')
    }
    const times = page.getByTestId('print-shift-time')
    await expect(times.first()).toHaveText(/\d{2}:\d{2} [AP]M/)
    const lines = await times.evaluateAll((cells) =>
      cells.map((cell) => {
        const range = document.createRange()
        range.selectNodeContents(cell)
        return new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size
      }),
    )
    expect(lines.length).toBeGreaterThan(0)
    expect(lines.filter((count) => count > 1)).toEqual([])
  })
})

test.describe('a list’s details', () => {
  test('"Print notice" opens the list’s sheet', async ({ adminPage: page, adminUser }) => {
    seeded = await seedSharedListEvent(page, 'E2E Print Detail')
    const list = await createSharedList(adminUser.email, seeded.event.id, {
      title: 'Aushang Kuchen',
      intro: 'Trag dich ein!',
      task_ids: [seeded.tasks[0]!.task.id],
    })

    await page.goto(`/app/shared-lists/${seeded.event.id}/${list.id}`)
    await page.getByTestId('shared-list-detail').getByTestId('shared-list-link-print').click()

    await expect(page).toHaveURL(new RegExp(`/print/lists/${list.id}$`))
    await expect(page.getByTestId('print-content')).toContainText('Trag dich ein!')
    await expectListQr(page, list.id, adminUser.email)
  })

  test('a paused list offers to resume instead of printing', async ({
    adminPage: page,
    adminUser,
  }) => {
    seeded = await seedSharedListEvent(page, 'E2E Print Paused')
    const list = await createSharedList(adminUser.email, seeded.event.id, {
      title: 'Pausiert',
      task_ids: [seeded.tasks[0]!.task.id],
    })
    await api(page, 'POST', `/shared-lists/${list.id}/pause`)

    await page.goto(`/print/lists/${list.id}`)
    const status = page.getByTestId('print-list-status')
    await expect(status).toContainText('The list is paused.')
    await expect(page.getByRole('button', { name: 'Print', exact: true })).toBeDisabled()

    await status.getByTestId('print-list-fix').click()
    await expect(page.getByTestId('print-list-status')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Print', exact: true })).toBeEnabled()
    await expectListQr(page, list.id, adminUser.email)
  })
})
