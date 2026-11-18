/**
 * A guest's own page, `/guest-signup#<token>`, opened with the token the
 * sign-up itself answered with (the one the done step shows as the link to
 * keep). The page takes the token out of the address bar before anything
 * else, then lets the guest take their name off, or delete their data.
 *
 * "Das war ich nicht" needs the token from a mail, which only the mailbox
 * holds: the backend refuses the sign-up's own token for it
 * (`guest_signup.mail_link_required`, covered by the backend suite). Here the
 * button is checked to stay away on the sign-up's link, and its flow is
 * walked with the mail's link, which `guestMailLink` hands over.
 */
import { expect, test } from '../../fixtures.js'
import { guestMailLink } from '../../helpers/api.js'
import { pinBrowserPreferences } from '../../helpers/auth.js'
import {
  type GuestListSeed,
  deleteGuestList,
  seedGuestList,
  signUpGuest,
} from '../../helpers/guest.js'

test.use({ storageState: { cookies: [], origins: [] } })

let seed: GuestListSeed | undefined

test.beforeEach(async ({ page }) => {
  await pinBrowserPreferences(page)
})

test.afterEach(async ({ adminUser }) => {
  await deleteGuestList(adminUser.email, seed)
  seed = undefined
})

test.describe('Guest – managing a sign-up', () => {
  test('reads the link, takes the token out of the address bar and lists the shifts', async ({
    page,
    adminUser,
  }) => {
    seed = await seedGuestList(adminUser.email)
    const signup = await signUpGuest(seed, {
      shift_id: seed.shifts[0]!.id,
      email: 'mia.manage@test.example.com',
      remind: true,
    })

    // Started before the page loads, so it has to cover the whole load.
    const loaded = page.waitForResponse((r) => r.url().endsWith('/public/guest-signups/manage'), {
      timeout: 20_000,
    })
    await page.goto(`/guest-signup#${signup.guest_token}`)
    expect((await loaded).status()).toBe(200)

    await expect(page.getByTestId('page-heading')).toHaveText('Your sign-ups')
    expect(new URL(page.url()).hash).toBe('')
    await expect(page.getByTestId('guest-manage-who')).toContainText('Grace Guest')
    await expect(page.getByTestId('guest-manage-booking')).toContainText(seed.taskName)
    await expect(page.getByTestId('guest-reminders-switch')).toHaveAttribute(
      'data-state',
      'checked',
    )
    // The link the sign-up page showed cannot say "that was not me".
    await expect(page.getByTestId('btn-guest-not-me')).toHaveCount(0)
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute(
      'content',
      'noindex, nofollow',
    )

    // The router forgot the token too: the next page's entry does not point back to it.
    await page.getByRole('link', { name: 'Privacy Policy' }).click()
    await expect(page).toHaveURL(/\/privacy/)
    const state = await page.evaluate(() => JSON.stringify(history.state))
    expect(state).toContain('"back":"/guest-signup"')
    expect(state).not.toContain(signup.guest_token)
  })

  test('a link that does not work says so, also after a reload', async ({ page }) => {
    await page.goto('/guest-signup#not-a-real-token')
    await expect(page.getByTestId('guest-manage-not-found')).toBeVisible()
    await page.reload()
    await expect(page.getByTestId('guest-manage-not-found')).toBeVisible()
  })

  test('takes the guest off a shift once they confirm', async ({ page, adminUser }) => {
    seed = await seedGuestList(adminUser.email)
    const signup = await signUpGuest(seed, {
      shift_id: seed.shifts[0]!.id,
      email: 'mia.cancel@test.example.com',
    })
    await page.goto(`/guest-signup#${signup.guest_token}`)
    await page.getByTestId(`btn-guest-cancel-${signup.booking_id}`).focus()
    await page.keyboard.press('Enter')

    const cancelled = page.waitForResponse((r) => r.url().endsWith('/public/guest-signups/cancel'))
    await page.getByTestId('btn-dialog-confirm').click()
    expect((await cancelled).status()).toBe(200)

    const row = page.locator(`[data-booking-id="${signup.booking_id}"]`)
    await expect(row).toHaveAttribute('data-status', 'cancelled')
    await expect(page.getByTestId(`btn-guest-cancel-${signup.booking_id}`)).toHaveCount(0)
    // Its button went with it; focus stays on the shift instead of falling out of the page.
    await expect(row.getByRole('heading', { name: seed.taskName })).toBeFocused()
  })

  test('switches the reminder mail off', async ({ page, adminUser }) => {
    seed = await seedGuestList(adminUser.email)
    const signup = await signUpGuest(seed, {
      shift_id: seed.shifts[0]!.id,
      email: 'mia.remind@test.example.com',
      remind: true,
    })
    await page.goto(`/guest-signup#${signup.guest_token}`)
    const toggle = page.getByTestId('guest-reminders-switch')
    await expect(toggle).toHaveAttribute('data-state', 'checked')

    const saved = page.waitForResponse((r) => r.url().endsWith('/public/guest-signups/reminders'))
    await toggle.click()
    expect((await saved).request().postDataJSON()).toMatchObject({ enabled: false })
    await expect(toggle).toHaveAttribute('data-state', 'unchecked')
  })

  test('deletes the data, after which the link stops working', async ({ page, adminUser }) => {
    seed = await seedGuestList(adminUser.email)
    const signup = await signUpGuest(seed, {
      shift_id: seed.shifts[0]!.id,
      email: 'mia.erase@test.example.com',
    })
    await page.goto(`/guest-signup#${signup.guest_token}`)
    await page.getByTestId('btn-guest-erase').click()
    const erased = page.waitForResponse((r) => r.url().endsWith('/public/guest-signups/erase'))
    await page.getByTestId('btn-dialog-confirm').click()
    expect((await erased).status()).toBe(204)
    await expect(page.getByTestId('guest-manage-erased')).toBeVisible()
    await expect(page.getByTestId('page-heading')).toBeFocused()

    await page.goto(`/guest-signup#${signup.guest_token}`)
    await expect(page.getByTestId('guest-manage-not-found')).toBeVisible()
  })

  test('"That wasn\'t me" from a mail link ends the sign-up', async ({ page, adminUser }) => {
    seed = await seedGuestList(adminUser.email)
    const signup = await signUpGuest(seed, {
      shift_id: seed.shifts[0]!.id,
      email: 'not.me@test.example.com',
    })
    const mailLink = await guestMailLink(signup.guest_token)

    await page.goto(`/guest-signup#${mailLink}`)
    // Opened from the mail, the page also asks whether the address is theirs.
    await expect(page.getByTestId('guest-confirm')).toBeVisible()
    await page.getByTestId('btn-guest-not-me').click()
    await expect(page.getByRole('dialog')).toContainText(
      'We delete the sign-up and never write to this address again.',
    )
    const rejected = page.waitForResponse((r) => r.url().endsWith('/public/guest-signups/not-me'))
    await page.getByTestId('btn-dialog-confirm').click()
    const response = await rejected
    expect(response.status()).toBe(204)
    expect(response.request().postDataJSON()).toEqual({ token: mailLink })
    await expect(page.getByTestId('guest-manage-rejected')).toBeVisible()
    await expect(page.getByTestId('guest-manage-rejected')).toContainText(
      "We've deleted the sign-up and won't write to this address any more.",
    )
  })
})
