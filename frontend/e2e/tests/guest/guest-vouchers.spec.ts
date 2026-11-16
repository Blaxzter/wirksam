/**
 * Vouchers for people who sign up through a shared list, without an account.
 *
 * A guest earns the task's vouchers once their shift is over, shows a code on
 * their own page (`/guest-signup#<token>`), and an organiser redeems it at a
 * stand by typing it in, as for a member. Nobody can sign up for a shift that
 * is over, so the guest signs up for one still ahead and the organiser then
 * moves it to yesterday, inside an event that started yesterday.
 *
 * Confirming an address needs the link from a mail. E2E has no mailbox, so
 * `guestMailLink` (`/testing/guest-mail-link`) hands it over, before the
 * confirmation retires the sign-up's own link.
 */
import { expect, test } from '../../fixtures.js'
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

test.describe('Guest – vouchers', () => {
  test('a guest earns vouchers, shows a code and an organiser redeems it', async ({
    page,
    adminPage,
    adminUser,
  }) => {
    // Two people through several screens, and a wait for the guest's code
    // screen to follow the redemption.
    test.slow()
    const list = (seed = await seedVoucherGuestList(adminUser.email))
    const point = list.pointTask!

    // The public list says what each shift brings, and that guests earn it too.
    await page.goto(`/l/${list.list.code}`)
    await expect(page.getByTestId('shared-list-vouchers-hint')).toBeVisible()
    await expect(page.getByTestId('public-shift-vouchers').first()).toHaveText('2 vouchers')

    const signup = await signUpGuest(list, {
      shift_id: list.shifts[0]!.id,
      email: guestEmail('vera voucher'),
    })
    await endGuestShift(adminUser.email, list.shifts[0]!.id)

    await page.goto(`/guest-signup#${signup.guest_token}`)
    const card = page.getByTestId('guest-vouchers')
    await expect(card.getByTestId('voucher-available')).toHaveText('2')
    await card.getByTestId('btn-guest-show-code').click()
    const codeDialog = page.getByTestId('voucher-code-dialog')
    const codeText = codeDialog.getByTestId('voucher-code-text')
    await expect(codeText).toHaveText(/^[2-9A-HJKMNP-Z]{3}-[2-9A-HJKMNP-Z]{3}$/)
    const code = (await codeText.textContent())!.trim()

    // The organiser redeems both at the stand. No camera here, so the page
    // opens the field to type the code by itself.
    await adminPage.addInitScript(() => {
      Object.defineProperty(navigator, 'mediaDevices', {
        configurable: true,
        value: {
          getUserMedia: () => Promise.reject(new DOMException('No camera', 'NotFoundError')),
        },
      })
    })
    await adminPage.goto(`/app/vouchers/redeem/${list.eventId}?task=${point.id}`)
    await expect(adminPage.getByTestId('voucher-scanner-error')).toBeVisible()
    await adminPage.getByTestId('voucher-code-input').fill(code)
    await adminPage.getByTestId('btn-voucher-check').click()
    const confirm = adminPage.getByTestId('voucher-redeem-confirm')
    const person = confirm.getByTestId('voucher-redeem-person')
    await expect(person).toContainText('Grace Guest')
    await expect(person.getByTestId('guest-tag')).toHaveText('no account')
    await expect(confirm.getByTestId('voucher-redeem-available')).toHaveText('2 available')
    await confirm.getByTestId('btn-voucher-amount-increase').click()
    await confirm.getByTestId('btn-voucher-redeem').click()
    await expect(confirm.getByTestId('voucher-redeem-success')).toContainText('2 vouchers redeemed')
    await expect(confirm.getByTestId('voucher-redeem-left')).toHaveText('none left')

    // The guest's screen follows within a couple of seconds, and the page
    // behind it reads the balance again.
    const used = codeDialog.getByTestId('voucher-code-used')
    await expect(used).toContainText(`2 vouchers used at ${point.name}`, { timeout: 10_000 })
    await expect(used.getByTestId('voucher-code-left')).toHaveText(
      'You have no vouchers to use right now.',
    )
    await codeDialog.getByRole('button', { name: 'Close' }).first().click()
    await expect(codeDialog).toBeHidden()
    await expect(card.getByTestId('voucher-available')).toHaveText('0')
    await expect(card.getByTestId('btn-guest-show-code')).toHaveAttribute('aria-disabled', 'true')
  })

  test('two sign-ups with one address end on one page once both are confirmed', async ({
    page,
    adminUser,
  }) => {
    seed = await seedGuestList(adminUser.email)
    const email = guestEmail('family')
    const maria = await signUpGuest(seed, {
      shift_id: seed.shifts[0]!.id,
      email,
      name: 'Maria Muster',
    })
    const tom = await signUpGuest(seed, {
      shift_id: seed.shifts[1]!.id,
      email,
      name: 'Tom Muster',
    })
    const mariaMail = await guestMailLink(maria.guest_token)
    const tomMail = await guestMailLink(tom.guest_token)

    // The sign-up's own link cannot confirm; it only says where that happens.
    await page.goto(`/guest-signup#${maria.guest_token}`)
    await expect(page.getByTestId('guest-confirm-from-mail')).toBeVisible()
    await expect(page.getByTestId('btn-guest-confirm')).toHaveCount(0)

    await page.goto('about:blank')
    await page.goto(`/guest-signup#${mariaMail}`)
    await expect(page.getByTestId('guest-confirm')).toBeVisible()
    const first = page.waitForResponse((r) => r.url().endsWith('/public/guest-signups/confirm'))
    await page.getByTestId('btn-guest-confirm').click()
    expect((await first).status()).toBe(200)
    await expect(page.getByTestId('guest-manage-confirmed')).toBeFocused()
    await expect(page.getByTestId('guest-confirm')).toHaveCount(0)

    await page.goto('about:blank')
    await page.goto(`/guest-signup#${tomMail}`)
    await expect(page.getByTestId('guest-manage-booking')).toHaveCount(1)
    await page.getByTestId('btn-guest-confirm').click()

    // One page, both shifts, each under its own name.
    const rows = page.getByTestId('guest-manage-booking')
    await expect(rows).toHaveCount(2)
    await expect(page.getByTestId('guest-manage-who')).toContainText('Signed up as Maria Muster')
    await expect(page.getByTestId('guest-booking-name')).toHaveCount(1)
    await expect(
      page.locator(`[data-booking-id="${tom.booking_id}"]`).getByTestId('guest-booking-name'),
    ).toHaveText('Signed up as Tom Muster')

    // The first sign-up's own link died with the confirmation.
    await page.goto('about:blank')
    await page.goto(`/guest-signup#${maria.guest_token}`)
    await expect(page.getByTestId('guest-manage-not-found')).toBeVisible()
  })

  test('at phone width the vouchers card and the code screen scroll no page sideways', async ({
    page,
    adminUser,
  }) => {
    const list = (seed = await seedVoucherGuestList(adminUser.email))
    const signup = await signUpGuest(list, {
      shift_id: list.shifts[0]!.id,
      email: guestEmail('narrow'),
    })
    await endGuestShift(adminUser.email, list.shifts[0]!.id)

    await page.setViewportSize({ width: 375, height: 740 })
    await page.goto(`/guest-signup#${signup.guest_token}`)
    await expect(page.getByTestId('guest-vouchers').getByTestId('voucher-available')).toHaveText(
      '2',
    )
    const overflow = () =>
      page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
    expect(await overflow()).toBe(0)

    await page.getByTestId('btn-guest-show-code').click()
    await expect(page.getByTestId('voucher-code-text')).toBeVisible()
    expect(await overflow()).toBe(0)
    const dialog = await page.getByTestId('voucher-code-dialog').boundingBox()
    expect(dialog!.x).toBeGreaterThanOrEqual(0)
    expect(dialog!.x + dialog!.width).toBeLessThanOrEqual(375)
  })
})
