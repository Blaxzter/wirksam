/**
 * The dashboard and the bottom nav on a phone (Pixel 7).
 *
 * The bottom nav starts with a Home tab now, so the More sheet no longer lists
 * the dashboard; and below desktop width the open shifts stop at four cards,
 * with the link under them counting the rest.
 */
import { expect, test } from '../../fixtures.js'
import {
  type TaskWithShifts,
  createTaskWithShifts,
  deleteTask,
  uniqueName,
} from '../../helpers/api.js'

let created: TaskWithShifts

test.beforeEach(async ({ adminPage: page }) => {
  // Six one-hour shifts nobody has taken, so the event has more open shifts
  // than a phone shows.
  created = await createTaskWithShifts(page, {
    name: uniqueName('E2E Mobile Dashboard Task'),
    location: 'Main Gate',
    status: 'published',
    startTime: '08:00',
    endTime: '14:00',
    slotDuration: 60,
    peoplePerShift: 2,
  })
})

test.afterEach(async ({ adminPage: page }) => {
  await deleteTask(page, created.task.id).catch(() => {})
})

test.describe('Dashboard – on a phone', () => {
  test('the bottom nav starts with Home and marks the current page', async ({
    adminPage: page,
  }) => {
    expect(page.viewportSize()?.width).toBeLessThan(768)

    await page.goto('/app/home')
    const nav = page.getByTestId('mobile-bottom-nav')
    await expect(nav.locator('a, button').first()).toHaveAttribute('data-testid', 'mobile-nav-home')
    await expect(page.getByTestId('mobile-nav-home')).toHaveAttribute('aria-current', 'page')

    await page.getByTestId('mobile-nav-tasks').click()
    await expect(page).toHaveURL(/\/app\/tasks/)
    await expect(page.getByTestId('mobile-nav-tasks')).toHaveAttribute('aria-current', 'page')
    await expect(page.getByTestId('mobile-nav-home')).not.toHaveAttribute('aria-current')
  })

  test('Home brings you back to the dashboard', async ({ adminPage: page }) => {
    await page.goto('/app/tasks')
    await page.getByTestId('mobile-nav-home').click()
    await expect(page).toHaveURL(/\/app\/home/)
    await expect(page.getByTestId('dashboard-header')).toBeVisible()
  })

  test('the More sheet no longer lists Home', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('mobile-nav-more').click()
    await expect(page.getByTestId('mobile-more-sheet')).toBeVisible()
    await expect(page.getByTestId('mobile-more-home')).toHaveCount(0)
    await expect(page.getByTestId('mobile-more-availability')).toBeVisible()
  })

  test('on a phone the open shifts stop at four', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    const section = page.getByTestId('dashboard-open-shifts')
    await expect(section.locator('[data-testid="open-shift-card"]:visible')).toHaveCount(4)
    const browse = page.getByTestId('btn-browse-open-shifts')
    await expect(browse).toBeVisible()
    // The link holds both counts and shows one by width; text matching would
    // read the hidden one too, so this asks which is on screen.
    const phoneCount = browse.getByTestId('open-shifts-more-mobile')
    await expect(phoneCount).toBeVisible()
    await expect(phoneCount).toHaveText(/^\(\d+ more\)$/)
    await expect(browse.getByTestId('open-shifts-more-desktop')).toBeHidden()
  })
})
