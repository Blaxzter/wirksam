/**
 * Keyboard and focus-management tests.
 *
 * axe-core is static analysis: it can tell you a dialog has the right role, but
 * not whether it traps focus, closes on Escape or hands focus back afterwards.
 * reka-ui gives all of that for free — these tests exist to notice when a
 * customisation quietly takes it away.
 */
import { expect, test } from '../../fixtures.js'
import {
  describeFocus,
  focusIsInside,
  focusedAttribute,
  tabUntilFocused,
} from '../../helpers/a11y.js'
import {
  type TaskWithShifts,
  createTaskWithShifts,
  deleteTask,
  uniqueName,
} from '../../helpers/api.js'

const DIALOG = '[data-slot="dialog-content"]'
const CALENDAR = '[data-slot="calendar"]'
const CALENDAR_DAY = '[data-slot="calendar-cell-trigger"]'

// ── Task creation wizard ─────────────────────────────────────────────────────

test.describe('a11y – task create wizard keyboard support', () => {
  test('tab order follows the visual order of the details section', async ({ adminPage: page }) => {
    await page.goto('/app/tasks/create')

    const details = page.getByTestId('section-task-details')
    await expect(details).toBeVisible()

    const name = page.getByTestId('input-task-name')
    const description = details.locator('textarea')
    // The location is a picker (a select trigger), not a text field.
    const location = details.getByTestId('location-picker')
    const category = details.locator('#task-category')
    // The Next button is disabled — and therefore unfocusable — until the
    // section is valid, so give it a name first.
    const next = details.getByRole('button', { name: /next|weiter/i })

    await name.fill('E2E A11y Tab Order')
    await expect(name).toBeFocused()

    await page.keyboard.press('Tab')
    await expect(description).toBeFocused()

    await page.keyboard.press('Tab')
    await expect(location).toBeFocused()

    await page.keyboard.press('Tab')
    await expect(category).toBeFocused()

    await page.keyboard.press('Tab')
    await expect(next).toBeFocused()
  })

  // Regression guard for #149: the calendar grid used to render its day cells
  // as native <button>s, which made every adjacent-month day a tab stop and let
  // ArrowRight page the calendar forever, wedging the renderer. `tabUntilFocused`
  // below only reaches a day at all because the grid now has a single tab stop.
  test('the date picker is operable with the keyboard alone', async ({ adminPage: page }) => {
    await page.goto('/app/tasks/create')

    const dates = page.getByTestId('section-task-dates')
    await expect(dates).toBeVisible()

    // Open the accordion section with Enter rather than a click.
    await dates.getByRole('button').first().focus()
    await page.keyboard.press('Enter')

    // The DatePicker trigger is the only popover trigger in this section.
    const trigger = dates.locator('button[aria-haspopup="dialog"]')
    await expect(trigger).toBeVisible()

    // From here on: keyboard only, no clicks.
    await trigger.focus()
    await page.keyboard.press('Enter')

    const calendar = page.locator(CALENDAR)
    await expect(calendar).toBeVisible()

    // Opening the popover must move focus into it, or a keyboard user is stranded.
    await expect
      .poll(() => focusIsInside(page, CALENDAR), {
        message: 'opening the date picker should move focus into the calendar',
      })
      .toBe(true)

    // Reach the day grid, then walk a day with ArrowRight.
    await tabUntilFocused(page, CALENDAR_DAY)
    const before = await focusedAttribute(page, 'data-value')
    await page.keyboard.press('ArrowRight')
    const after = await focusedAttribute(page, 'data-value')
    expect(
      after,
      `ArrowRight should move to the next day, focus is on ${await describeFocus(page)}`,
    ).not.toBeNull()
    expect(after).not.toBe(before)

    // Enter selects the focused day, closes the popover and returns focus.
    await page.keyboard.press('Enter')
    await expect(calendar).toBeHidden()
    await expect(trigger).toBeFocused()
    // The trigger now renders the picked date instead of the placeholder.
    await expect(trigger).toContainText(String(after).slice(0, 4))
  })
})

// ── Confirm-delete dialog ────────────────────────────────────────────────────

test.describe('a11y – confirm-delete dialog focus management', () => {
  let created: TaskWithShifts

  test.beforeEach(async ({ adminPage: page }) => {
    await page.goto('/app/tasks')
    created = await createTaskWithShifts(page, {
      name: uniqueName('E2E A11y Dialog Task'),
      status: 'published',
      startTime: '10:00',
      endTime: '12:00',
      slotDuration: 60,
      peoplePerShift: 2,
    })
  })

  test.afterEach(async ({ adminPage: page }) => {
    await deleteTask(page, created.task.id).catch(() => {})
  })

  test('traps focus and closes on Escape', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)

    const trigger = page.getByTestId('btn-delete-task')
    await expect(trigger).toBeVisible()
    await trigger.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await expect
      .poll(() => focusIsInside(page, DIALOG), {
        message: 'opening the dialog should move focus inside it',
      })
      .toBe(true)

    // Tab well past the number of controls in the dialog: focus must never
    // reach the page behind it.
    for (let press = 1; press <= 8; press++) {
      await page.keyboard.press('Tab')
      const inside = await focusIsInside(page, DIALOG)
      expect(
        inside,
        `focus escaped the dialog after ${press} Tab press(es), landing on ${await describeFocus(page)}`,
      ).toBe(true)
    }

    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
  })

  test('returns focus to the trigger after closing', async ({ adminPage: page }) => {
    await page.goto(`/app/tasks/${created.task.id}`)

    const trigger = page.getByTestId('btn-delete-task')
    await expect(trigger).toBeVisible()
    await trigger.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()

    // Without this, a keyboard user is dropped back at the top of the document.
    await expect(trigger).toBeFocused()
  })
})
