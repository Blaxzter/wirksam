/**
 * My Bookings on a phone (Pixel 7).
 *
 * The search used to share its row with the date range and the "cancelled"
 * button at a flex basis of zero, which left it a few dozen pixels: the
 * placeholder read "Suchen.". Now it shares the row with one filter button,
 * and that button holds the date range and the cancelled switch.
 */
import { expect, test } from '../../fixtures.js'

test.describe('My Bookings – on a phone', () => {
  test('the search keeps a usable width next to one filter button', async ({
    adminPage: page,
  }) => {
    expect(page.viewportSize()?.width).toBeLessThan(768)

    await page.goto('/app/bookings')
    await expect(page.getByTestId('input-search')).toBeVisible()
    await expect(page.getByTestId('btn-bookings-filters')).toBeVisible()
    // The wide-screen controls are folded into the one button.
    await expect(page.getByTestId('btn-toggle-cancelled')).toBeHidden()

    // Both measured in one go: the cards above load later and move the row.
    const layout = await page.getByTestId('bookings-filter-row').evaluate((row) => {
      const box = (testid: string) =>
        row.querySelector(`[data-testid="${testid}"]`)!.getBoundingClientRect()
      const search = box('input-search')
      const filters = box('btn-bookings-filters')
      return {
        searchWidth: search.width,
        offset: Math.abs(search.top + search.height / 2 - (filters.top + filters.height / 2)),
      }
    })
    expect(layout.searchWidth).toBeGreaterThanOrEqual(200)
    // Side by side, on one row.
    expect(layout.offset).toBeLessThan(4)
  })

  test('the filter button holds the date range and the cancelled switch', async ({
    adminPage: page,
  }) => {
    await page.goto('/app/bookings')
    await page.getByTestId('btn-bookings-filters').click()

    const menu = page.getByTestId('bookings-filters')
    await expect(menu).toBeVisible()
    await expect(menu.getByRole('button', { name: /from today/i })).toBeVisible()
    const cancelled = menu.getByTestId('switch-show-cancelled')
    await expect(cancelled).toHaveAttribute('aria-checked', 'false')
    await cancelled.click()
    await expect(cancelled).toHaveAttribute('aria-checked', 'true')
  })
})
