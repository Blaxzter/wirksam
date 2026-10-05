/**
 * The three ways a self-hosted deployment can restrict signup, through the real
 * form, the real endpoints and the real router guard.
 *
 * The E2E backend runs open signup, and it runs four worker processes, so a
 * spec cannot switch the mode by changing a setting: only one process would
 * see it. Instead every API request from the page carries the policy it wants
 * in `X-Test-Registration-Policy`, which the backend honours only while
 * `TESTING` is on (`app/logic/auth/registration.py::policy_for_request`). That
 * keeps the override per test, so these run in parallel with everything else.
 *
 * The rules themselves (which invitation counts, the superadmin exemption, the
 * bypass switch) are covered in `backend/tests/api/routes/test_registration_modes.py`.
 * What is checked here is the half only a browser can see: what the form says
 * before anyone types, the refusal it shows, and where the guard sends an
 * account that may sign in but not use the app.
 */
import type { Page } from '@playwright/test'

import { expect, serverApi, serverApiRaw, test } from '../../fixtures.js'
import { futureDate, uniqueName } from '../../helpers/api.js'
import {
  AUTH_TEST_PASSWORD,
  authTestEmail,
  deleteAccount,
  pinBrowserPreferences,
} from '../../helpers/auth.js'

// An anonymous visitor: a signed-in one is bounced off /register.
test.use({ storageState: { cookies: [], origins: [] } })

test.afterEach(async ({ adminUser }, testInfo) => {
  await deleteAccount(adminUser.email, authTestEmail(testInfo)).catch(() => {})
})

interface Policy {
  mode: 'open' | 'approval' | 'invite'
  allowed_domains?: string[]
  invite_bypass?: boolean
}

/** Make every API call this page sends ask for `policy`. */
async function usePolicy(page: Page, policy: Policy): Promise<void> {
  const header = JSON.stringify({ allowed_domains: [], invite_bypass: true, ...policy })
  await page.route('**/api/v1/**', (route) =>
    route.continue({
      headers: { ...route.request().headers(), 'x-test-registration-policy': header },
    }),
  )
}

async function fillRegistration(page: Page, email: string, name = 'Mode Tester'): Promise<void> {
  await page.getByTestId('input-name').fill(name)
  await page.getByTestId('input-email').fill(email)
  await page.getByTestId('input-password').fill(AUTH_TEST_PASSWORD)
  await page.getByTestId('input-confirm-password').fill(AUTH_TEST_PASSWORD)
  await page.getByTestId('btn-register').click()
}

async function userIdByEmail(adminEmail: string, email: string): Promise<string> {
  const found = await serverApi<{ items: { id: string; email: string | null }[] }>(
    'GET',
    `/users/?q=${encodeURIComponent(email)}`,
    adminEmail,
  )
  const user = found.items.find((item) => item.email === email)
  expect(user, `no account for ${email}`).toBeDefined()
  return user!.id
}

test.describe('Registration modes – approval queue', () => {
  test('a new account waits, and gets in once a superadmin approves it', async ({
    adminUser,
    page,
  }, testInfo) => {
    const email = authTestEmail(testInfo)
    await pinBrowserPreferences(page)
    await usePolicy(page, { mode: 'approval' })

    await page.goto('/register')
    await expect(page.getByTestId('register-policy')).toContainText(
      'An administrator approves every new account',
    )
    await fillRegistration(page, email)

    // Signed in, but parked on the waiting screen rather than inside the app.
    await page.waitForURL('**/account-pending')
    await expect(page.getByTestId('page-heading')).toHaveText(
      'Your account is waiting for approval',
    )
    await page.goto('/app/home')
    await expect(page).toHaveURL(/\/account-pending/)

    const id = await userIdByEmail(adminUser.email, email)
    await serverApi('POST', `/users/${id}/approve`, adminUser.email)

    // "Check again" picks the decision up without signing out and in.
    await page.getByTestId('btn-check-approval').click()
    await page.waitForURL(/\/app\//)
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('a rejected registration is told so, with the reason', async ({
    adminUser,
    page,
  }, testInfo) => {
    const email = authTestEmail(testInfo)
    await pinBrowserPreferences(page)
    await usePolicy(page, { mode: 'approval' })

    await page.goto('/register')
    await fillRegistration(page, email)
    await page.waitForURL('**/account-pending')

    const id = await userIdByEmail(adminUser.email, email)
    await serverApi('POST', `/users/${id}/reject`, adminUser.email, {
      reason: 'Only for members of the parish.',
    })

    await page.reload()
    await expect(page.getByTestId('page-heading')).toHaveText('Your registration was not approved')
    await expect(page.getByTestId('suspension-reason')).toContainText(
      'Only for members of the parish.',
    )
    await expect(page.getByTestId('btn-check-approval')).toHaveCount(0)
  })
})

test.describe('Registration modes – invitation only', () => {
  test('without an invitation the form says so and the signup is refused', async ({
    page,
  }, testInfo) => {
    await pinBrowserPreferences(page)
    await usePolicy(page, { mode: 'invite' })

    await page.goto('/register')
    await expect(page.getByTestId('register-policy')).toContainText(
      'You need an invitation to sign up here',
    )
    await fillRegistration(page, authTestEmail(testInfo))

    // `errorCodes.auth.invitation_required`
    await expect(page.locator('[data-sonner-toast]')).toContainText(
      'You need an invitation to sign up here',
    )
    await expect(page).toHaveURL(/\/register/)
  })

  test('the invitation link lets the signup through', async ({ adminUser, page }, testInfo) => {
    const event = await serverApi<{ id: string; name: string }>(
      'POST',
      '/events/',
      adminUser.email,
      {
        name: uniqueName('E2E Invite Only'),
        status: 'published',
        visibility: 'private',
        start_date: futureDate(30),
        end_date: futureDate(34),
      },
    )
    try {
      const invitation = await serverApi<{ token: string }>(
        'POST',
        `/events/${event.id}/invitations`,
        adminUser.email,
        { role: 'member' },
      )
      await pinBrowserPreferences(page)
      await usePolicy(page, { mode: 'invite' })

      await page.goto(`/invite/${invitation.token}`)
      await page.getByTestId('btn-invite-register').click()

      // Arriving with the invitation, the "you need one" note has no business
      // being there.
      await expect(page.getByTestId('register-form')).toBeVisible()
      await expect(page.getByTestId('register-policy')).toHaveCount(0)
      await fillRegistration(page, authTestEmail(testInfo))

      await page.waitForURL(`**/invite/${invitation.token}`)
      await expect(page.getByTestId('invite-event-name')).toContainText(event.name)
    } finally {
      await serverApiRaw('DELETE', `/events/${event.id}`, adminUser.email).catch(() => {})
    }
  })
})

test.describe('Registration modes – allowed domains', () => {
  test('the form names the domains and refuses any other address', async ({
    page,
  }, testInfo) => {
    await pinBrowserPreferences(page)
    await usePolicy(page, { mode: 'open', allowed_domains: ['gemeinde.de'] })

    await page.goto('/register')
    await expect(page.getByTestId('register-policy')).toContainText('@gemeinde.de')
    await fillRegistration(page, authTestEmail(testInfo))

    // `errorCodes.auth.email_domain_not_allowed`
    await expect(page.locator('[data-sonner-toast]')).toContainText(
      'This email address cannot be used to sign up here.',
    )
    await expect(page).toHaveURL(/\/register/)
  })
})
