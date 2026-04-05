import { mkdirSync } from 'node:fs'
import { dirname } from 'node:path'
import { expect, test as setup } from '@playwright/test'

const authFile = 'e2e/.auth/member.json'

setup('authenticate member with Auth0', async ({ page }) => {
  const username = process.env.E2E_AUTH0_USERNAME_MEMBER
  const password = process.env.E2E_AUTH0_PASSWORD_MEMBER

  if (!username || !password) {
    throw new Error(
      'Missing E2E member credentials. Set E2E_AUTH0_USERNAME_MEMBER and E2E_AUTH0_PASSWORD_MEMBER before running Playwright.',
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
  await page.waitForURL(/(\/app\/home|\/pending-approval|\?\w+=)/, { timeout: 60_000 })

  // If we landed on root with auth code, navigate to /app/home
  // (the router will redirect to /pending-approval if the user is inactive)
  if (!page.url().includes('/app/home') && !page.url().includes('/pending-approval')) {
    await page.goto('/app/home')
  }

  // Dismiss "What's New" dialog if it appears (blocks test interactions)
  const dismissBtn = page.getByTestId('btn-dismiss-whats-new')
  if (await dismissBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await dismissBtn.click()
  }

  // Member may land on Dashboard (active) or Pending Approval (inactive)
  await expect(page.getByTestId('page-heading')).toBeVisible({ timeout: 30_000 })

  // If member is pending approval, activate via admin API
  if (page.url().includes('/pending-approval')) {
    const API = process.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'

    // Wait for admin auth file to be ready (auth-admin may run in parallel)
    const { existsSync } = await import('node:fs')
    const adminAuthFile = 'e2e/.auth/user.json'
    const deadline = Date.now() + 60_000
    while (!existsSync(adminAuthFile) && Date.now() < deadline) {
      await page.waitForTimeout(1000)
    }

    // Use admin storage state to approve the member via API
    const adminCtx = await page.context().browser()!.newContext({ storageState: adminAuthFile })
    const adminPage = await adminCtx.newPage()
    await adminPage.goto('http://localhost:5173/app/home')
    await adminPage.waitForTimeout(3000)

    // Find member in admin user list and approve
    await adminPage.evaluate(
      async ({ email, apiUrl }) => {
        const key = Object.keys(localStorage).find((k) =>
          k.startsWith('@@auth0spajs@@') && !k.includes('@@user@@'),
        )
        if (!key) return
        const token = JSON.parse(localStorage.getItem(key)!).body.access_token

        const listRes = await fetch(`${apiUrl}/users/`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        const users = (await listRes.json()) as Array<{
          id: string
          email: string
          is_active: boolean
        }>
        const member = users.find((u) => u.email?.toLowerCase() === email.toLowerCase())
        if (member && !member.is_active) {
          await fetch(`${apiUrl}/users/${member.id}`, {
            method: 'PATCH',
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ is_active: true }),
          })
        }
      },
      { email: username, apiUrl: API },
    )

    await adminCtx.close()

    // Refresh member page — should now be active
    await page.goto('/app/home')
    await expect(page.getByTestId('page-heading')).toBeVisible({ timeout: 30_000 })
  }

  // Wait for the Auth0 SPA SDK to persist the token to localStorage
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
