/**
 * E2E tests for the Dashboard: the greeting header, the next-shift card, your
 * plan, and the shifts that still need people.
 *
 * The page used to be a month calendar; it is now "what you have said yes to"
 * and "where people are still missing", so these specs follow a shift from
 * being on offer to being on the hero card and in the plan.
 */
import { expect, test } from '../../fixtures.js'
import {
  type ShiftRead,
  type TaskWithShifts,
  bookShift,
  cancelBooking,
  createTaskWithShifts,
  deleteTask,
  listShifts,
  uniqueName,
} from '../../helpers/api.js'

let created: TaskWithShifts
let shifts: ShiftRead[]
let taskName: string

test.beforeEach(async ({ adminPage: page }) => {
  taskName = uniqueName('E2E Dashboard Task')
  created = await createTaskWithShifts(page, {
    name: taskName,
    location: 'Main Gate',
    status: 'published',
    // Earlier than the 10:00 default every other spec uses, so this task's
    // shifts are unambiguously the soonest thing the worker's admin is on and
    // the headline card cannot be won by a stray booking from elsewhere.
    startTime: '08:00',
    endTime: '10:00',
    slotDuration: 60,
    peoplePerShift: 3,
  })
  shifts = await listShifts(page, created.task.id)
})

test.afterEach(async ({ adminPage: page }) => {
  await deleteTask(page, created.task.id).catch(() => {})
})

test.describe('Dashboard – page structure', () => {
  test('leads with the next-shift card', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('dashboard-next-shift')).toBeVisible()
  })

  test('shows the shifts that still need people', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('dashboard-open-shifts')).toBeVisible()
  })

  test('greets you in the page header', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('dashboard-header')).toBeVisible()
    await expect(page.getByTestId('page-heading')).toHaveText(/^Good (morning|afternoon|evening)/)
  })
})

test.describe('Dashboard – shifts that need people', () => {
  test('lists a shift from a freshly published job', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(
      page.getByTestId('dashboard-open-shifts').getByText(taskName).first(),
    ).toBeVisible()
  })

  test('a shift nobody has taken is marked as such', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    const card = page
      .getByTestId('dashboard-open-shifts')
      .getByTestId('open-shift-card')
      .filter({ hasText: taskName })
      .first()
    await expect(card).toContainText('Nobody yet')
    // In words, not only as the bar.
    await expect(card).toContainText('0 of 3 filled')
  })

  test('Sign up opens the shift', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page
      .getByTestId('dashboard-open-shifts')
      .getByTestId('open-shift-card')
      .filter({ hasText: taskName })
      .first()
      .getByTestId('btn-open-shift-signup')
      .click()
    // On the contents, not the container: `dialog-shift-detail` is on
    // `DialogContent`, which renders whether or not a shift resolved, so
    // `toBeVisible()` alone passes on an empty dialog.
    await expect(page.getByTestId('dialog-shift-detail')).toContainText('Main Gate')
  })

  test('Browse shifts goes to the task list', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('btn-browse-open-shifts').click()
    await expect(page).toHaveURL(/\/app\/tasks/)
    await expect(page).toHaveURL(/hide_full=true/)
  })
})

test.describe('Dashboard – what you have said yes to', () => {
  test('a booked shift becomes the headline and leaves the offer list', async ({
    adminPage: page,
  }) => {
    const booking = await bookShift(page, shifts[0].id)
    try {
      await page.goto('/app/home')
      const hero = page.getByTestId('dashboard-next-shift')
      await expect(hero).toContainText(taskName)
      await expect(hero).toContainText('Main Gate')
      // By id: the cards show the title without its time suffix.
      await expect(
        page.getByTestId('dashboard-open-shifts').locator(`[data-shift-id="${shifts[0].id}"]`),
      ).toHaveCount(0)
    } finally {
      await cancelBooking(page, booking.id).catch(() => {})
    }
  })

  test('the headline opens the shift it names', async ({ adminPage: page }) => {
    const booking = await bookShift(page, shifts[0].id)
    try {
      await page.goto('/app/home')
      await page.getByTestId('btn-open-next-shift').click()
      // Named, so the assertion fails on a dialog that opened over nothing.
      await expect(page.getByTestId('dialog-shift-detail')).toContainText('Main Gate')
    } finally {
      await cancelBooking(page, booking.id).catch(() => {})
    }
  })

  test('the next shift says how far away it is', async ({ adminPage: page }) => {
    const booking = await bookShift(page, shifts[0].id)
    try {
      await page.goto('/app/home')
      // Not the wording: a run that straddles midnight would turn "tomorrow"
      // into "today" under the test.
      const countdown = page.getByTestId('dashboard-next-shift').getByTestId('next-shift-countdown')
      await expect(countdown).toBeVisible()
      await expect(countdown).not.toBeEmpty()
    } finally {
      await cancelBooking(page, booking.id).catch(() => {})
    }
  })

  test('every booking is in your plan, the next one marked', async ({ adminPage: page }) => {
    const first = await bookShift(page, shifts[0].id)
    const second = await bookShift(page, shifts[1].id)
    try {
      await page.goto('/app/home')
      const plan = page.getByTestId('dashboard-my-shifts')
      await expect(plan.locator(`[data-shift-id="${shifts[0].id}"]`)).toContainText('Up next')
      const later = plan.locator(`[data-shift-id="${shifts[1].id}"]`)
      await expect(later).toBeVisible()
      await expect(later.getByTestId('plan-next-badge')).toHaveCount(0)
    } finally {
      await cancelBooking(page, first.id).catch(() => {})
      await cancelBooking(page, second.id).catch(() => {})
    }
  })
})

test.describe('Dashboard – the organiser view', () => {
  test('an organiser is told which shifts have nobody on them', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('dashboard-attention')).toBeVisible()
    await expect(page.getByTestId('attention-empty')).toBeVisible()
  })

  test('the gap link leads to the task list', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('attention-empty').click()
    await expect(page).toHaveURL(/\/app\/tasks/)
  })

  test('somebody who only helps out sees none of it', async ({ memberPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('dashboard-open-shifts')).toBeVisible()
    await expect(page.getByTestId('dashboard-attention')).toHaveCount(0)
  })
})

test.describe('Dashboard – getting around', () => {
  test('Find a shift in the header opens the open shifts', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('btn-header-find-shift').click()
    await expect(page).toHaveURL(/\/app\/tasks/)
    await expect(page).toHaveURL(/hide_full=true/)
  })

  test('All bookings opens your bookings', async ({ adminPage: page }) => {
    const booking = await bookShift(page, shifts[0].id)
    try {
      await page.goto('/app/home')
      await page.getByTestId('btn-all-bookings').click()
      await expect(page).toHaveURL(/\/app\/bookings/)
    } finally {
      await cancelBooking(page, booking.id).catch(() => {})
    }
  })
})
