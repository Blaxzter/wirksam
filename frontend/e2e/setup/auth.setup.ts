import { mkdirSync } from 'node:fs'
import { dirname } from 'node:path'
import { expect, test as setup } from '@playwright/test'

const authFile = 'e2e/.auth/user.json'

setup('authenticate with Auth0', async ({ page }) => {
  const username = process.env.E2E_AUTH0_USERNAME
  const password = process.env.E2E_AUTH0_PASSWORD

  if (!username || !password) {
    throw new Error(
      'Missing E2E auth credentials. Set E2E_AUTH0_USERNAME and E2E_AUTH0_PASSWORD before running Playwright.',
    )
  }

  await page.goto('/')
  await page.getByRole('button', { name: /sign in|get started/i }).first().click()

  const usernameInput = page
    .locator('input[name="username"], input#username, input[type="email"]')
    .first()
  await usernameInput.waitFor({ state: 'visible', timeout: 45_000 })
  await usernameInput.fill(username)

  const passwordInput = page
    .locator('input[name="password"], input#password, input[type="password"]')
    .first()

  const passwordVisible = await passwordInput.isVisible({ timeout: 2_000 }).catch(() => false)
  if (!passwordVisible) {
    const continueButton = page.getByRole('button', { name: /continue|next/i }).first()
    if (await continueButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await continueButton.click()
    }
  }

  await passwordInput.waitFor({ state: 'visible', timeout: 45_000 })
  await passwordInput.fill(password)

  const submitButton = page.getByRole('button', { name: /continue|log in|login|sign in/i }).first()
  if (await submitButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await submitButton.click()
  } else {
    await page.locator('button[type="submit"], button[name="action"]').first().click()
  }

  const consentButton = page.getByRole('button', { name: /accept|authorize|allow/i }).first()
  if (await consentButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await consentButton.click()
  }

  // Wait for Auth0 to process the callback code and authenticate
  // The callback URL may return to root (/) if VITE_AUTH0_CALLBACK_URL points there
  await page.waitForURL(/(\/app\/home|\?\w+=)/, { timeout: 60_000 })

  // If we landed on root with auth code, the Auth0 SDK processes it and we become authenticated.
  // Navigate to /app/home to trigger the post-auth redirect and profile load.
  if (!page.url().includes('/app/home')) {
    await page.goto('/app/home')
  }

  // Dismiss "What's New" dialog if it appears (blocks test interactions)
  const dismissBtn = page.getByTestId('btn-dismiss-whats-new')
  if (await dismissBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await dismissBtn.click()
  }

  // Wait for the dashboard to load (locale-independent via data-testid)
  await expect(page.getByTestId('page-heading')).toBeVisible({ timeout: 30_000 })

  // Wait for the Auth0 SPA SDK to persist the token to localStorage.
  await page.waitForFunction(
    () => Object.keys(localStorage).some((k) => k.startsWith('@@auth0spajs@@')),
    null,
    { timeout: 15_000 },
  )

  // Suppress "What's New" dialog and set English locale for all future tests
  await page.evaluate(() => {
    localStorage.setItem('wirksam-last-seen-changelog', '99.99.99')
    localStorage.setItem('locale', 'en')
  })

  mkdirSync(dirname(authFile), { recursive: true })
  await page.context().storageState({ path: authFile })
})
