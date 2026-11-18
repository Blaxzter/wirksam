/**
 * A shared list's public page on a phone, which is where nearly everyone opens
 * it: from a group chat, or from a QR code at the stand.
 *
 * It asserts the layout contract rather than the copy (that is the `guest`
 * project's job): nothing scrolls sideways, the buttons are big enough for a
 * thumb, and the done step stacks its ways on instead of crowding a row.
 */
import type { Page } from '@playwright/test'

import { expect, test } from '../../fixtures.js'
import { pinBrowserPreferences } from '../../helpers/auth.js'
import { type GuestListSeed, deleteGuestList, seedGuestList } from '../../helpers/guest.js'

test.use({ storageState: { cookies: [], origins: [] } })

let seed: GuestListSeed | undefined

test.afterEach(async ({ adminUser }) => {
  await deleteGuestList(adminUser.email, seed)
  seed = undefined
})

/** How far the page reaches past the right edge of the screen; 0 when it fits. */
const sidewaysOverflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)

test('the page runs at a phone width', async ({ page }) => {
  const viewport = page.viewportSize()
  expect(viewport?.width).toBeLessThan(500)
})

test('a list fits the screen and signs a guest up with thumb-sized buttons', async ({
  page,
  adminUser,
}) => {
  seed = await seedGuestList(adminUser.email, {
    list: {
      intro:
        'We need a hand at the long-named Gemeindefest-Getränkeausschank with a very long title.',
      ask_phone: 'optional',
    },
  })
  await pinBrowserPreferences(page)
  await page.goto(`/l/${seed.list.code}`)
  await expect(page.getByTestId('page-heading')).toHaveText(seed.list.title)
  expect(await sidewaysOverflow(page)).toBeLessThanOrEqual(0)

  const pick = page.getByTestId(`btn-pick-shift-${seed.shifts[0]!.id}`)
  expect((await pick.boundingBox())!.height).toBeGreaterThanOrEqual(40)
  await pick.click()

  await expect(page.getByTestId('guest-signup-form')).toBeVisible()
  expect(await sidewaysOverflow(page)).toBeLessThanOrEqual(0)
  await page.getByTestId('guest-input-name').fill('Pia Phone')
  await page.getByTestId('guest-input-email').fill('pia.phone@test.example.com')
  const submit = page.getByTestId('btn-guest-submit')
  expect((await submit.boundingBox())!.height).toBeGreaterThanOrEqual(44)
  await submit.click()

  await expect(page.getByTestId('guest-signup-done')).toBeVisible()
  expect(await sidewaysOverflow(page)).toBeLessThanOrEqual(0)
  // The ways on are stacked, each across the whole column.
  const another = (await page.getByTestId('btn-guest-another').boundingBox())!
  const next = (await page.getByTestId('btn-guest-next').boundingBox())!
  expect(next.y).toBeGreaterThan(another.y + another.height - 1)
  expect(Math.abs(next.width - another.width)).toBeLessThan(2)
})
