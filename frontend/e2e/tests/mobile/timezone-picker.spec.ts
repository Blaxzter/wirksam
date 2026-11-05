/**
 * The time zone picker on a phone: it takes the whole screen, with the list above
 * the keyboard, rather than squeezing a few hundred names into a popup. Every
 * other project runs at a desktop viewport and would not notice this breaking.
 */
import { expect, test } from '../../fixtures.js'

test('the time zone picker fills a phone screen and picks a zone', async ({ adminPage: page }) => {
  await page.goto('/app/events/create')

  await page.getByTestId('timezone-picker').click()

  const sheet = page.getByTestId('timezone-picker-sheet')
  await expect(sheet).toBeVisible()
  const viewport = page.viewportSize()
  const box = await sheet.boundingBox()
  expect(viewport && viewport.width < 640).toBe(true)
  expect(box?.width).toBe(viewport?.width)
  expect(box?.height).toBe(viewport?.height)

  await page.getByTestId('timezone-picker-input').fill('lisbon')
  await page.getByTestId('timezone-option-Europe/Lisbon').click()

  await expect(sheet).toBeHidden()
  await expect(page.getByTestId('timezone-picker-value')).toHaveText('Europe/Lisbon')
})
