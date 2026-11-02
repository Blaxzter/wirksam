/**
 * Accessibility scans for the member (non-admin) role.
 *
 * A member sees a different sidebar, no admin controls and read-only variants of
 * several pages, so the admin scans do not cover this DOM. Admin-only routes are
 * not scanned here because the router bounces a member off them.
 */
import { expect, test } from '../../fixtures.js'
import { expectNoA11yViolations } from '../../helpers/a11y.js'
import {
  type TaskWithShifts,
  bookShift,
  cancelBooking,
  createTaskWithShifts,
  deleteTask,
  listShifts,
  uniqueName,
} from '../../helpers/api.js'

test.describe('a11y – member routes', () => {
  test('dashboard', async ({ memberPage: member }) => {
    await member.goto('/app/home')
    await expect(member.getByTestId('page-heading')).toBeVisible()
    // The greeting renders before the cards; scanning then would scan the
    // skeleton. The next-shift card (or its empty state) only comes with the
    // rest of the cards.
    await expect(member.getByTestId('dashboard-next-shift')).toBeVisible()
    await expectNoA11yViolations(member, { label: 'member dashboard (/app/home)' })
  })

  test('tasks list', async ({ memberPage: member }) => {
    await member.goto('/app/tasks')
    await expect(member.getByTestId('page-heading')).toBeVisible()
    await expectNoA11yViolations(member, { label: 'member tasks list (/app/tasks)' })
  })

  test('event picker', async ({ memberPage: member }) => {
    await member.goto('/app/select-event?mode=switch')
    await expect(member.getByTestId('page-heading')).toBeVisible()
    await expectNoA11yViolations(member, { label: 'member event picker (/app/select-event)' })
  })

  test('my bookings', async ({ memberPage: member }) => {
    await member.goto('/app/bookings')
    await expect(member.getByTestId('page-heading')).toBeVisible()
    await expectNoA11yViolations(member, { label: 'member bookings (/app/bookings)' })
  })

  test('availability', async ({ memberPage: member }) => {
    await member.goto('/app/availability')
    await expect(member.getByTestId('section-my-availability')).toBeVisible()
    await expectNoA11yViolations(member, { label: 'member availability (/app/availability)' })
  })

  test('settings', async ({ memberPage: member }) => {
    await member.goto('/app/settings')
    await expect(member.getByTestId('page-heading')).toBeVisible()
    await expectNoA11yViolations(member, { label: 'member settings (/app/settings)' })
  })
})

// ── The dashboard with a shift booked ───────────────────────────────────────
//
// The plain dashboard scan only ever meets the empty next-shift card. The green
// card has the riskiest colour pairs on the page (muted white on the primary
// colour, the amber countdown chip), and its tokens differ in dark mode.

test.describe('a11y – member dashboard with a booked shift', () => {
  let created: TaskWithShifts

  test.beforeEach(async ({ adminPage }) => {
    created = await createTaskWithShifts(adminPage, {
      name: uniqueName('E2E A11y Next Shift'),
      location: 'Main Gate',
      status: 'published',
      startTime: '10:00',
      endTime: '12:00',
      slotDuration: 120,
      peoplePerShift: 3,
    })
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteTask(adminPage, created.task.id).catch(() => {})
  })

  for (const colorScheme of ['light', 'dark'] as const) {
    test(`next-shift card, ${colorScheme}`, async ({ adminPage, memberPage: member }) => {
      const [shift] = await listShifts(adminPage, created.task.id)
      const booking = await bookShift(member, shift.id)
      try {
        await member.emulateMedia({ colorScheme })
        await member.goto('/app/home')
        await expect(member.getByTestId('btn-open-next-shift')).toBeVisible()
        await expect(member.getByTestId('next-shift-countdown')).toBeVisible()
        await expectNoA11yViolations(member, {
          label: `member dashboard with a booked shift, ${colorScheme}`,
        })
      } finally {
        await cancelBooking(member, booking.id).catch(() => {})
      }
    })
  }
})

// ── Task detail as seen by a member (no edit/delete controls) ────────────────

test.describe('a11y – member task detail', () => {
  let created: TaskWithShifts

  test.beforeEach(async ({ adminPage }) => {
    await adminPage.goto('/app/tasks')
    created = await createTaskWithShifts(adminPage, {
      name: uniqueName('E2E A11y Member Task'),
      description: 'Fixture for the member accessibility scan',
      status: 'published',
      startTime: '10:00',
      endTime: '12:00',
      slotDuration: 60,
      peoplePerShift: 5,
    })
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteTask(adminPage, created.task.id).catch(() => {})
  })

  test('task detail', async ({ memberPage: member }) => {
    await member.goto(`/app/tasks/${created.task.id}`)
    await expect(member.getByRole('heading', { name: created.task.name })).toBeVisible()
    await expectNoA11yViolations(member, { label: 'member task detail (/app/tasks/:id)' })
  })
})
