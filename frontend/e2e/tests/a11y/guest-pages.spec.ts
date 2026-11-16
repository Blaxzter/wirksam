/**
 * Accessibility scans of the guest pages: a shared list's public page in each
 * of its steps (list, form with its errors, done), and a guest's manage page,
 * with its vouchers and the code shown at a stand, and its address to confirm.
 *
 * As the anonymous visitor who opens these links, with no session to leak in.
 * Strangers with whatever device and assistive tech they have are exactly who
 * these pages are for.
 */
import { expect, test } from '../../fixtures.js'
import { expectNoA11yViolations } from '../../helpers/a11y.js'
import { guestMailLink } from '../../helpers/api.js'
import { pinBrowserPreferences } from '../../helpers/auth.js'
import {
  type GuestListSeed,
  deleteGuestList,
  endGuestShift,
  seedGuestList,
  seedVoucherGuestList,
  signUpGuest,
} from '../../helpers/guest.js'
import { guestEmail } from '../../helpers/shared-list-seed.js'

test.use({ storageState: { cookies: [], origins: [] } })

let seed: GuestListSeed | undefined

test.beforeEach(async ({ page }) => {
  await pinBrowserPreferences(page)
})

test.afterEach(async ({ adminUser }) => {
  await deleteGuestList(adminUser.email, seed)
  seed = undefined
})

test.describe('a11y – guest pages', () => {
  test('the list, the form and the done step have no serious or critical violations', async ({
    page,
    adminUser,
  }) => {
    seed = await seedGuestList(adminUser.email, {
      list: { intro: 'Pick what suits you.\nThank you!', ask_phone: 'optional' },
    })
    await page.goto(`/l/${seed.list.code}`)
    await expect(page.getByTestId('page-heading')).toHaveText(seed.list.title)
    await expectNoA11yViolations(page, { label: 'shared list (/l/…)' })

    await page.getByTestId(`btn-pick-shift-${seed.shifts[0]!.id}`).click()
    await page.getByTestId('btn-guest-submit').click()
    await expect(page.getByTestId('guest-name-error')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'shared list form with errors (/l/…)' })

    await page.getByTestId('guest-input-name').fill('Ada Access')
    await page.getByTestId('guest-input-email').fill('ada.access@test.example.com')
    await page.getByTestId('btn-guest-submit').click()
    await expect(page.getByTestId('guest-signup-done')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'shared list done (/l/…)' })
  })

  test('a link that leads nowhere has no serious or critical violations', async ({ page }) => {
    await page.goto('/l/nothing-here')
    await expect(page.getByTestId('shared-list-not-found')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'shared list not found (/l/…)' })
  })

  test('the manage page has no serious or critical violations', async ({ page, adminUser }) => {
    seed = await seedGuestList(adminUser.email)
    const signup = await signUpGuest(seed, {
      shift_id: seed.shifts[0]!.id,
      email: 'ada.manage@test.example.com',
      remind: true,
    })
    await page.goto(`/guest-signup#${signup.guest_token}`)
    await expect(page.getByTestId('page-heading')).toHaveText('Your sign-ups')
    await expectNoA11yViolations(page, { label: 'guest manage page (/guest-signup)' })
  })

  test('the manage page with vouchers and the open code screen has no serious or critical violations', async ({
    page,
    adminUser,
  }) => {
    seed = await seedVoucherGuestList(adminUser.email)
    const signup = await signUpGuest(seed, {
      shift_id: seed.shifts[0]!.id,
      email: guestEmail('ada vouchers'),
    })
    await endGuestShift(adminUser.email, seed.shifts[0]!.id)

    await page.goto(`/guest-signup#${signup.guest_token}`)
    await expect(page.getByTestId('guest-vouchers').getByTestId('voucher-available')).toHaveText(
      '2',
    )
    await expectNoA11yViolations(page, { label: 'guest manage page with vouchers (/guest-signup)' })

    await page.getByTestId('btn-guest-show-code').click()
    await expect(page.getByTestId('voucher-code-text')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'guest code screen (/guest-signup)' })
  })

  test('the address to confirm has no serious or critical violations', async ({
    page,
    adminUser,
  }) => {
    seed = await seedGuestList(adminUser.email)
    const signup = await signUpGuest(seed, {
      shift_id: seed.shifts[0]!.id,
      email: guestEmail('ada confirm'),
    })
    await page.goto(`/guest-signup#${await guestMailLink(signup.guest_token)}`)
    await expect(page.getByTestId('guest-confirm')).toBeVisible()
    await expectNoA11yViolations(page, { label: 'guest manage page to confirm (/guest-signup)' })
  })
})
