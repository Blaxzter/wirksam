/**
 * Playwright fixtures for isolated E2E testing without Auth0.
 *
 * Requires the backend to run with TESTING=true so that:
 * - POST /testing/seed creates test users directly in the DB
 * - POST /testing/reset cleans up test users
 * - X-Test-User-Email header bypasses Auth0 JWT validation
 *
 * Each parallel Playwright worker gets its own admin and member user,
 * so tests never interfere with each other.
 */

import { test as base, expect, type BrowserContext, type Page } from '@playwright/test'

const API = process.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'

export interface TestUser {
  email: string
  name: string
  roles: string[]
}

/**
 * Pre-seed Auth0 SDK localStorage cache so the SDK (initialised with
 * test-client-id / test-audience in bypass mode) finds a cached token
 * and reports isAuthenticated=true without making any network calls.
 */
function setupAuthBypass(context: BrowserContext, user: TestUser) {
  return context.addInitScript((userInfo) => {
    // Key must match the clientId + audience used in main.ts bypass mode
    const key = '@@auth0spajs@@::test-client-id::test-audience::openid profile email'
    const value = {
      body: {
        access_token: 'fake-test-token',
        token_type: 'Bearer',
        expires_in: 86400,
        scope: 'openid profile email',
        client_id: 'test-client-id',
        audience: 'test-audience',
        decodedToken: {
          user: {
            sub: `test|${userInfo.email}`,
            email: userInfo.email,
            name: userInfo.name,
            email_verified: true,
            picture: '',
          },
          claims: {
            sub: `test|${userInfo.email}`,
            aud: 'test-audience',
            iss: 'https://test.auth0.local/',
            exp: Math.floor(Date.now() / 1000) + 86400,
            iat: Math.floor(Date.now() / 1000),
          },
        },
      },
      expiresAt: Math.floor(Date.now() / 1000) + 86400,
    }
    localStorage.setItem(key, JSON.stringify(value))
    localStorage.setItem('wirksam-last-seen-changelog', '99.99.99')
    localStorage.setItem('locale', 'en')
  }, { email: user.email, name: user.name })
}

/**
 * Intercept all API requests on a page and add the X-Test-User-Email header.
 * Must be called on the page (not context) so cross-origin requests are caught.
 */
function setupApiInterception(page: Page, email: string) {
  return page.route('**/api/v1/**', (route) => {
    const headers = {
      ...route.request().headers(),
      'x-test-user-email': email,
    }
    return route.continue({ headers })
  })
}

/**
 * Seed a test user via the backend testing API (no auth required).
 */
async function seedUser(email: string, name: string, roles: string[], isActive = true): Promise<void> {
  const resp = await fetch(`${API}/testing/seed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, name, roles, is_active: isActive, preferred_language: 'en' }),
  })
  if (!resp.ok) {
    throw new Error(`Failed to seed user ${email}: ${resp.status} ${await resp.text()}`)
  }
}

const IS_TESTING = process.env.USE_AUTH0_E2E?.toLowerCase() !== 'true'

// ── Fixtures ──────────────────────────────────────────────────────────────────

export const test = base.extend<
  // Test-scoped fixtures
  { adminPage: Page; memberPage: Page },
  // Worker-scoped fixtures
  { adminUser: TestUser; memberUser: TestUser }
>({
  // Worker-scoped: each parallel worker seeds its own admin user
  adminUser: [async ({}, use, workerInfo) => {
    if (!IS_TESTING) {
      await use({ email: '', name: '', roles: [] })
      return
    }
    const email = `admin-worker-${workerInfo.workerIndex}@test.example.com`
    const name = `Test Admin ${workerInfo.workerIndex}`
    await seedUser(email, name, ['admin'])
    await use({ email, name, roles: ['admin'] })
  }, { scope: 'worker' }],

  // Worker-scoped: each parallel worker seeds its own member user
  memberUser: [async ({}, use, workerInfo) => {
    if (!IS_TESTING) {
      await use({ email: '', name: '', roles: [] })
      return
    }
    const email = `member-worker-${workerInfo.workerIndex}@test.example.com`
    const name = `Test Member ${workerInfo.workerIndex}`
    await seedUser(email, name, [])
    await use({ email, name, roles: [] })
  }, { scope: 'worker' }],

  // Test-scoped: a page pre-configured as the admin user
  adminPage: async ({ browser, adminUser }, use) => {
    const context = await browser.newContext()
    if (IS_TESTING) {
      // Set bypass cookie so main.ts and router activate the fake Auth0 plugin
      await context.addCookies([{ name: 'e2e_bypass', value: '1', domain: 'localhost', path: '/' }])
      await setupAuthBypass(context, adminUser)
    }
    const page = await context.newPage()
    if (IS_TESTING) {
      await setupApiInterception(page, adminUser.email)
      await page.goto('/app/home')
      await page.getByTestId('page-heading').waitFor({ timeout: 15_000 })
    }
    await use(page)
    await context.close()
  },

  // Test-scoped: a page pre-configured as the member user
  memberPage: async ({ browser, memberUser }, use) => {
    const context = await browser.newContext()
    if (IS_TESTING) {
      await context.addCookies([{ name: 'e2e_bypass', value: '1', domain: 'localhost', path: '/' }])
      await setupAuthBypass(context, memberUser)
    }
    const page = await context.newPage()
    if (IS_TESTING) {
      await setupApiInterception(page, memberUser.email)
      await page.goto('/app/home')
      await page.getByTestId('page-heading').waitFor({ timeout: 15_000 })
    }
    await use(page)
    await context.close()
  },
})

export { expect }

// Re-export API helpers with test-user support
export { API }

/** Make an authenticated API call using X-Test-User-Email header. */
export async function testApi<T = unknown>(
  page: Page,
  method: string,
  path: string,
  body?: object,
  testEmail?: string,
): Promise<T> {
  const email = testEmail ?? ''
  return page.evaluate(
    async ({ url, method, body, email }) => {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      }
      if (email) {
        headers['X-Test-User-Email'] = email
      }
      const res = await fetch(url, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
      })
      if (res.status === 204) return null
      return res.json()
    },
    { url: `${API}${path}`, method, body, email },
  ) as Promise<T>
}
