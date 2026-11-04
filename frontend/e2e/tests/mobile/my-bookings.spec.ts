/**
 * My Bookings on a phone (Pixel 7).
 *
 * The search used to share its row with the date range and the "cancelled"
 * button at a flex basis of zero, which left it a few dozen pixels: the
 * placeholder read "Suchen.". Now it shares the row with one filter button,
 * and that button holds the date range, the cancelled switch and how the
 * list is arranged (by date, task or place).
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
        searchHeight: search.height,
        filtersHeight: filters.height,
        offset: Math.abs(search.top + search.height / 2 - (filters.top + filters.height / 2)),
      }
    })
    expect(layout.searchWidth).toBeGreaterThanOrEqual(200)
    // Both big enough to hit with a thumb.
    expect(layout.searchHeight).toBeGreaterThanOrEqual(44)
    expect(layout.filtersHeight).toBeGreaterThanOrEqual(44)
    // Side by side, on one row.
    expect(layout.offset).toBeLessThan(4)
  })

  test('the filter button holds the date range, the cancelled switch and the arrangement', async ({
    adminPage: page,
  }) => {
    await page.goto('/app/bookings')
    const button = page.getByTestId('btn-bookings-filters')
    await button.click()

    const menu = page.getByTestId('bookings-filters')
    await expect(menu).toBeVisible()
    await expect(menu.getByRole('button', { name: /from today/i })).toBeVisible()
    const cancelled = menu.getByTestId('switch-show-cancelled')
    await expect(cancelled).toHaveAttribute('aria-checked', 'false')
    await cancelled.click()
    await expect(cancelled).toHaveAttribute('aria-checked', 'true')
    // The dot on the button says so to the eye; its name says so to a screen reader.
    await expect(button).toHaveAttribute('aria-label', /cancelled bookings shown/i)

    // How the list is arranged lives here too, one choice at a time.
    const byPlace = menu.getByTestId('btn-arrange-location')
    await expect(menu.getByTestId('btn-arrange-date')).toHaveAttribute('aria-pressed', 'true')
    await byPlace.click()
    await expect(byPlace).toHaveAttribute('aria-pressed', 'true')
    await expect(menu.getByTestId('btn-arrange-date')).toHaveAttribute('aria-pressed', 'false')
    await menu.getByTestId('btn-arrange-date').click()
  })
})
