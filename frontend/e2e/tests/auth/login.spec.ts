/**
 * Signing in with a password, against the real endpoint.
 *
 * Both halves matter and neither is worth much alone: a "wrong password is
 * refused" test passes just as happily when the form is broken and nothing ever
 * signs in, so the accepted password is checked first.
 */
import { expect, test } from '../../fixtures.js'
import {
  AUTH_TEST_PASSWORD,
  AUTH_WRONG_PASSWORD,
  authTestEmail,
  deleteAccount,
  pinBrowserPreferences,
  registerAccount,
} from '../../helpers/auth.js'

// An authenticated visitor is redirected off /login by the router guard, so a
// leaked session would fail these on a redirect rather than on the thing they
// mean to check.
test.use({ storageState: { cookies: [], origins: [] } })

test.beforeEach(async ({ page }, testInfo) => {
  await registerAccount(authTestEmail(testInfo), 'Login Test')
  await pinBrowserPreferences(page)
})

// Registered accounts carry a `local|…` subject, which `POST /testing/reset`
// deliberately leaves alone — so each test removes its own.
test.afterEach(async ({ adminUser }, testInfo) => {
  await deleteAccount(adminUser.email, authTestEmail(testInfo)).catch(() => {})
})

test.describe('Auth – sign in', () => {
  test('the right password signs in and opens the app', async ({ page }, testInfo) => {
    await page.goto('/login')
    await expect(page.getByTestId('page-heading')).toBeVisible()

    await page.getByTestId('input-email').fill(authTestEmail(testInfo))
    await page.getByTestId('input-password').fill(AUTH_TEST_PASSWORD)
    await page.getByTestId('btn-login').click()

    // The account belongs to no event, so the router lands it on the picker
    // rather than the dashboard. Both are inside /app; which one is the
    // onboarding tests' business, not this one's.
    await page.waitForURL(/\/app\//)
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('a wrong password is refused and the visitor stays on the form', async ({
    page,
  }, testInfo) => {
    await page.goto('/login')
    await page.getByTestId('input-email').fill(authTestEmail(testInfo))
    await page.getByTestId('input-password').fill(AUTH_WRONG_PASSWORD)
    await page.getByTestId('btn-login').click()

    // `errorCodes.auth.invalid_credentials`. The endpoint deliberately gives
    // the same answer for a wrong password and an unknown address, so this
    // wording must not name which of the two it was.
    await expect(page.locator('[data-sonner-toast]')).toContainText(
      'That email address and password do not match.',
    )
    // The toast fades; the same sentence stays on the form, in red, until the
    // visitor changes what they typed.
    const formError = page.getByTestId('form-error')
    await expect(formError).toContainText('That email address and password do not match.')
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByTestId('login-form')).toBeVisible()

    await page.getByTestId('input-password').fill(AUTH_TEST_PASSWORD)
    await expect(formError).toBeHidden()
  })

  test('an address with no account is refused the same way', async ({ page }, testInfo) => {
    await page.goto('/login')
    // A second, never-registered address: the refusal has to read identically,
    // or the form becomes a way to ask whether somebody has an account here.
    await page.getByTestId('input-email').fill(authTestEmail(testInfo, 2))
    await page.getByTestId('input-password').fill(AUTH_TEST_PASSWORD)
    await page.getByTestId('btn-login').click()

    await expect(page.locator('[data-sonner-toast]')).toContainText(
      'That email address and password do not match.',
    )
    await expect(page.getByTestId('form-error')).toContainText(
      'That email address and password do not match.',
    )
    await expect(page).toHaveURL(/\/login/)
  })
})
