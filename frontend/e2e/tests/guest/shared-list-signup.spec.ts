/**
 * A shared list's public page, `/l/<code>`, as the stranger who opens it from
 * a group chat: no account, no bypass cookie, no session of any kind.
 *
 * Nothing here may depend on a cookie. In CI the page and the API are on
 * different sites, so the guest flow has to work on the response bodies alone,
 * which is how it is built.
 *
 * Whether a confirmation mail goes out depends on the backend having SMTP
 * (the mailcatcher locally, possibly none in CI). Without one the done step
 * shows the manage link instead, so the specs accept either where it matters
 * and pin the link down where there is no address at all.
 */
import type { Page } from '@playwright/test'

import { expect, serverApi, test } from '../../fixtures.js'
import { type PublicSignupResult, guestMailLink } from '../../helpers/api.js'
import { pinBrowserPreferences } from '../../helpers/auth.js'
import {
  type GuestListSeed,
  deleteGuestList,
  seedGuestList,
  signUpGuest,
} from '../../helpers/guest.js'

test.use({ storageState: { cookies: [], origins: [] } })

let seed: GuestListSeed | undefined

test.afterEach(async ({ adminUser }) => {
  await deleteGuestList(adminUser.email, seed)
  seed = undefined
})

/** Open the list and wait until its title is on screen. */
async function openList(page: Page, list: GuestListSeed) {
  await page.goto(`/l/${list.list.code}`)
  await expect(page.getByTestId('page-heading')).toHaveText(list.list.title)
}

/** Pick a shift, type a name (and an address) and send it; resolves with the request body. */
async function signUp(page: Page, shiftId: string, fields: { name: string; email?: string }) {
  await page.getByTestId(`btn-pick-shift-${shiftId}`).click()
  await page.getByTestId('guest-input-name').fill(fields.name)
  if (fields.email !== undefined) await page.getByTestId('guest-input-email').fill(fields.email)
  const request = page.waitForRequest((r) => r.method() === 'POST' && r.url().endsWith(`/signups`))
  const response = page.waitForResponse(
    (r) => r.request().method() === 'POST' && r.url().endsWith('/signups'),
  )
  await page.getByTestId('btn-guest-submit').click()
  const sent = (await request).postDataJSON() as Record<string, unknown>
  await response
  return sent
}

test.describe('Guest – signing up on a shared list', () => {
  test.beforeEach(async ({ page }) => {
    await pinBrowserPreferences(page)
  })

  test('signs up with an email address and ends on "You\'re signed up"', async ({
    page,
    adminUser,
  }) => {
    seed = await seedGuestList(adminUser.email)
    await openList(page, seed)
    await expect(page.getByTestId('shared-list-event')).toContainText(seed.eventName)

    const sent = await signUp(page, seed.shifts[0]!.id, {
      name: 'Grace Guest',
      email: 'grace.guest@test.example.com',
    })
    expect(sent).toMatchObject({ name: 'Grace Guest', show_names: 'none', language: 'en' })
    expect(sent).not.toHaveProperty('turnstile_token')

    const done = page.getByTestId('guest-signup-done')
    await expect(done).toContainText("You're signed up")
    await expect(done).toContainText(seed.taskName)
    await expect(
      page.getByTestId('guest-done-mail').or(page.getByTestId('guest-done-keep-link')),
    ).toBeVisible()
  })

  test('signs up for another shift through the same chain', async ({ page, adminUser }) => {
    seed = await seedGuestList(adminUser.email)
    await openList(page, seed)
    await signUp(page, seed.shifts[0]!.id, {
      name: 'Grace Guest',
      email: 'grace.chain@test.example.com',
    })
    await page.getByTestId('btn-guest-another').click()
    await expect(page.getByTestId('public-shift-list')).toBeVisible()

    await page.getByTestId(`btn-pick-shift-${seed.shifts[1]!.id}`).click()
    await expect(page.getByTestId('guest-input-name')).toHaveValue('Grace Guest')
    const request = page.waitForRequest(
      (r) => r.method() === 'POST' && r.url().endsWith('/signups'),
    )
    await page.getByTestId('btn-guest-submit').click()
    expect((await request).postDataJSON()).toHaveProperty('guest_token')
    await expect(page.getByTestId('guest-signup-done')).toBeVisible()
  })

  test('goes on with a new chain once the first was confirmed from its mail', async ({
    page,
    adminUser,
  }) => {
    seed = await seedGuestList(adminUser.email)
    await openList(page, seed)
    const answer = () =>
      page.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith('/signups'))
    const first = answer()
    await signUp(page, seed.shifts[0]!.id, {
      name: 'Grace Guest',
      email: 'grace.confirmed@test.example.com',
    })
    const firstToken = ((await (await first).json()) as PublicSignupResult).guest_token

    // "Ja, das bin ich" in the mail's tab retires the token this tab holds.
    const mailToken = await guestMailLink(firstToken)
    await serverApi('POST', '/public/guest-signups/confirm', '', { token: mailToken })

    await page.getByTestId('btn-guest-another').click()
    await page.getByTestId(`btn-pick-shift-${seed.shifts[1]!.id}`).click()
    const second = answer()
    await page.getByTestId('btn-guest-submit').click()
    const secondToken = ((await (await second).json()) as PublicSignupResult).guest_token
    expect(secondToken).not.toBe(firstToken)

    // Taking it back works with the token that answered it.
    const cancel = page.waitForRequest((r) => r.url().endsWith('/public/guest-signups/cancel'))
    const cancelled = page.waitForResponse((r) => r.url().endsWith('/public/guest-signups/cancel'))
    await page.getByTestId('btn-guest-undo').click()
    expect((await cancel).postDataJSON()).toMatchObject({ token: secondToken })
    expect((await cancelled).status()).toBe(200)
    await expect(page.getByTestId('public-shift-list')).toBeVisible()

    // And the next sign-up continues the new chain instead of starting a third.
    await page.getByTestId(`btn-pick-shift-${seed.shifts[1]!.id}`).click()
    const request = page.waitForRequest(
      (r) => r.method() === 'POST' && r.url().endsWith('/signups'),
    )
    await page.getByTestId('btn-guest-submit').click()
    expect((await request).postDataJSON()).toMatchObject({ guest_token: secondToken })
    await expect(page.getByTestId('guest-signup-done')).toBeVisible()
  })

  test('takes a sign-up back, and the place opens again', async ({ page, adminUser }) => {
    seed = await seedGuestList(adminUser.email)
    await openList(page, seed)
    const shiftId = seed.shifts[0]!.id
    const card = page.locator(`[data-testid="public-shift"][data-shift-id="${shiftId}"]`)
    await expect(card.getByTestId('public-shift-free')).toHaveText('2 free')

    await signUp(page, shiftId, { name: 'Grace Guest', email: 'grace.undo@test.example.com' })
    const cancel = page.waitForResponse((r) => r.url().endsWith('/public/guest-signups/cancel'))
    await page.getByTestId('btn-guest-undo').click()
    expect((await cancel).status()).toBe(200)

    await expect(page.getByTestId('public-shift-list')).toBeVisible()
    await expect(card.getByTestId('public-shift-free')).toHaveText('2 free')
  })

  test('"Done – next person" leaves nothing of the last guest in the form', async ({
    page,
    adminUser,
  }) => {
    seed = await seedGuestList(adminUser.email)
    await openList(page, seed)
    await signUp(page, seed.shifts[0]!.id, {
      name: 'Grace Guest',
      email: 'grace.next@test.example.com',
    })
    await page.getByTestId('btn-guest-next').click()

    await expect(page.getByTestId('public-shift-list')).toBeVisible()
    await page.getByTestId(`btn-pick-shift-${seed.shifts[1]!.id}`).click()
    await expect(page.getByTestId('guest-input-name')).toHaveValue('')
    await expect(page.getByTestId('guest-input-email')).toHaveValue('')
  })

  test('shows the manage link to keep when there is no address to mail', async ({
    page,
    adminUser,
  }) => {
    seed = await seedGuestList(adminUser.email, { list: { ask_email: 'off' } })
    await openList(page, seed)
    await page.getByTestId(`btn-pick-shift-${seed.shifts[0]!.id}`).click()
    await expect(page.getByTestId('guest-input-email')).toHaveCount(0)
    await page.getByTestId('guest-input-name').fill('Nora Nomail')
    await page.getByTestId('btn-guest-submit').click()

    await expect(page.getByTestId('guest-done-keep-link')).toBeVisible()
    await expect(page.getByTestId('guest-manage-link')).toHaveValue(/\/guest-signup#.+/)
    await expect(page.getByTestId('guest-done-mail')).toHaveCount(0)
  })

  test('says a shift has just filled up when someone else took the last place', async ({
    page,
    adminUser,
  }) => {
    seed = await seedGuestList(adminUser.email, { peoplePerShift: 1 })
    await openList(page, seed)
    const shiftId = seed.shifts[0]!.id
    await page.getByTestId(`btn-pick-shift-${shiftId}`).click()
    await page.getByTestId('guest-input-name').fill('Slow Sam')
    await page.getByTestId('guest-input-email').fill('slow.sam@test.example.com')

    // Somebody on another phone is quicker.
    await signUpGuest(seed, { shift_id: shiftId, email: 'quick.quinn@test.example.com' })

    const refused = page.waitForResponse((r) => r.url().endsWith('/signups'))
    await page.getByTestId('btn-guest-submit').click()
    expect((await refused).status()).toBe(409)
    await expect(page.getByTestId('form-error')).toHaveText(
      'This shift has just filled up. Please pick another one.',
    )
  })

  test('checks the fields before sending, in the order they are laid out', async ({
    page,
    adminUser,
  }) => {
    seed = await seedGuestList(adminUser.email)
    await openList(page, seed)
    await page.getByTestId(`btn-pick-shift-${seed.shifts[0]!.id}`).click()
    await page.getByTestId('btn-guest-submit').click()

    await expect(page.getByTestId('guest-name-error')).toHaveText('Please enter your name.')
    await expect(page.getByTestId('guest-email-error')).toBeVisible()
    await expect(page.getByTestId('guest-input-name')).toBeFocused()
  })

  test('says first names show where the list shows them, how long details are kept, then links to privacy', async ({
    page,
    adminUser,
  }) => {
    seed = await seedGuestList(adminUser.email, { list: { show_names: 'first' } })
    await openList(page, seed)
    await page.getByTestId(`btn-pick-shift-${seed.shifts[0]!.id}`).click()

    const note = page.getByTestId('guest-privacy-note')
    await expect(note).toContainText('on shared lists that show first names.')
    // The server's number of days, and only what the list asks for (no phone here).
    // One space between the sentence and the link, however the template wraps.
    await expect(note).toContainText(
      'We delete your name and email address 30 days after your last shift. More about privacy',
    )
  })

  test('asks search engines to stay away', async ({ page, adminUser }) => {
    seed = await seedGuestList(adminUser.email)
    await openList(page, seed)
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute(
      'content',
      'noindex, nofollow',
    )
  })
})

test.describe('Guest – a list that is not open', () => {
  test.beforeEach(async ({ page }) => {
    await pinBrowserPreferences(page)
  })

  test('a link that leads nowhere says so', async ({ page }) => {
    await page.goto('/l/nothing-here')
    await expect(page.getByTestId('shared-list-not-found')).toBeVisible()
    await expect(page.getByTestId('page-heading')).toHaveText("This link doesn't exist (any more)")
  })

  test('a paused list and an ended one say so under their title', async ({ page, adminUser }) => {
    seed = await seedGuestList(adminUser.email)

    await serverApi('POST', `/shared-lists/${seed.list.id}/pause`, adminUser.email)
    await openList(page, seed)
    await expect(page.getByTestId('shared-list-paused')).toBeVisible()
    await expect(page.getByTestId('public-shift-list')).toHaveCount(0)

    await serverApi('POST', `/shared-lists/${seed.list.id}/end`, adminUser.email)
    await openList(page, seed)
    await expect(page.getByTestId('shared-list-closed')).toBeVisible()
  })
})

test.describe('Guest – in German', () => {
  test('follows the language the visitor chose', async ({ page, adminUser }) => {
    seed = await seedGuestList(adminUser.email)
    await page.addInitScript(() => {
      localStorage.setItem('locale', 'de')
      localStorage.setItem('wirksam-last-seen-changelog', '99.99.99')
    })
    await openList(page, seed)
    await expect(page.locator('html')).toHaveAttribute('lang', 'de')
    await expect(page.getByText('Such dir eine Schicht aus. Du brauchst kein Konto.')).toBeVisible()

    const sent = await signUp(page, seed.shifts[0]!.id, {
      name: 'Greta Gast',
      email: 'greta.gast@test.example.com',
    })
    expect(sent.language).toBe('de')
    await expect(page.getByTestId('guest-signup-done')).toContainText('Du bist eingetragen')
  })
})
