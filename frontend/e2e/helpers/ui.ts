import { type Locator, expect } from '@playwright/test'

/**
 * Pick a date from a shadcn-vue/reka-ui DatePicker (popover calendar).
 * @param trigger - locator for the DatePicker trigger button
 * @param dateStr - ISO date string, e.g. "2026-06-10"
 */
export async function pickDate(trigger: Locator, dateStr: string) {
  const [yearStr, monthStr, dayStr] = dateStr.split('-')
  const month = parseInt(monthStr, 10)
  const day = parseInt(dayStr, 10)

  const page = trigger.page()
  const calendar = page.locator('[data-slot="calendar"]')

  // A picker opened a moment ago is still mounted while its popover animates
  // out, and two calendars in the DOM make every locator below ambiguous.
  // Picking a start date and then an end date is exactly that case.
  await expect(calendar).toHaveCount(0)

  // Open the popover; the calendar appears inside it
  await trigger.click()
  await expect(calendar).toHaveCount(1)

  // Navigate to the correct month/year via the native <select> dropdowns
  const selects = calendar.locator('select')
  await selects.first().selectOption(String(month))
  await selects.last().selectOption(yearStr)

  // Click the day cell (exclude outside-view days from adjacent months)
  await calendar
    .locator('[data-slot="calendar-cell-trigger"]:not([data-outside-view])')
    .getByText(String(day), { exact: true })
    .click()
}

/**
 * Pick an option from a shadcn-vue/reka-ui Select.
 * Its list is portalled to the body, so the option is found on the page, not
 * under the trigger; waits for the list to close so the next step starts clean.
 * @param trigger - locator for the Select trigger (`role="combobox"`)
 * @param name - the option's visible text
 */
export async function pickOption(trigger: Locator, name: string | RegExp) {
  await trigger.click()
  const listbox = trigger.page().getByRole('listbox')
  await listbox.getByRole('option', { name, exact: typeof name === 'string' }).click()
  await expect(listbox).toHaveCount(0)
}
