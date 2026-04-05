import type { Locator } from '@playwright/test'

/**
 * Pick a date from a shadcn-vue/reka-ui DatePicker (popover calendar).
 * @param trigger - locator for the DatePicker trigger button
 * @param dateStr - ISO date string, e.g. "2026-06-10"
 */
export async function pickDate(trigger: Locator, dateStr: string) {
  const [yearStr, monthStr, dayStr] = dateStr.split('-')
  const month = parseInt(monthStr, 10)
  const day = parseInt(dayStr, 10)

  // Open the popover
  await trigger.click()

  // The calendar appears inside the popover
  const page = trigger.page()
  const calendar = page.locator('[data-slot="calendar"]')
  await calendar.waitFor()

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
