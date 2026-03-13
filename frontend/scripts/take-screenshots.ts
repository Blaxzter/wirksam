/**
 * Automated screenshot script for DutyHub landing page showcase.
 *
 * Usage:
 *   pnpm exec playwright test --config=scripts/screenshots.config.ts
 *   LANG=de pnpm exec playwright test --config=scripts/screenshots.config.ts
 *   LANG=en pnpm exec playwright test --config=scripts/screenshots.config.ts
 *
 * The LANG env var controls the app locale (default: "en").
 * Screenshots are saved to public/screenshots/<lang>/ (e.g. public/screenshots/en/).
 *
 * Requires:
 *   - Frontend running at http://localhost:5173
 *   - Backend running at http://localhost:8000
 *   - Valid Auth0 credentials in frontend/.env (E2E_AUTH0_USERNAME, E2E_AUTH0_PASSWORD)
 */

import { test } from '@playwright/test'

const BASE_URL = 'http://localhost:5173'
const LANG = process.env.LANG === 'de' ? 'de' : 'en'
const SCREENSHOT_DIR = `public/screenshots/${LANG}`
const VIEWPORT = { width: 1280, height: 720 }

// Credentials from .env
const EMAIL = process.env.E2E_AUTH0_USERNAME ?? ''
const PASSWORD = process.env.E2E_AUTH0_PASSWORD ?? ''

// Locale-dependent UI labels
const L = {
  en: {
    next: 'Next',
    pickADate: 'Pick a date',
    dateRange: 'Date range',
    addException: 'Add Exception',
    defaultStartTime: 'Default Start Time',
    signIn: 'Sign In',
    continue: 'Continue',
  },
  de: {
    next: 'Weiter',
    pickADate: 'Datum auswählen',
    dateRange: 'Zeitraum',
    addException: 'Ausnahme hinzufügen',
    defaultStartTime: 'Standard-Startzeit',
    signIn: 'Anmelden',
    continue: 'Continue', // Auth0 login page is always English
  },
} as const

const labels = L[LANG]

const PAGES: Array<{
  name: string
  path: string
  action?: (page: import('@playwright/test').Page) => Promise<void>
  fullPage?: boolean
}> = [
  { name: 'dashboard', path: '/app/home' },
  { name: 'event-groups', path: '/app/event-groups' },
  { name: 'events', path: '/app/events' },
  {
    name: 'event-detail',
    path: '/app/events',
    action: async (page: import('@playwright/test').Page) => {
      await page.getByText('[DEMO] Holiday Coverage').first().click()
      await page.waitForURL(/\/app\/events\//)
      await page.waitForTimeout(1000)
    },
  },
  { name: 'my-bookings', path: '/app/bookings' },
  {
    name: 'notification-bell',
    path: '/app/home',
    action: async (page: import('@playwright/test').Page) => {
      // Click the notification bell to open the popover
      const bellButton = page.locator('button:has(svg.lucide-bell)').first()
      await bellButton.waitFor({ state: 'visible', timeout: 5_000 })
      await bellButton.click()
      await page.waitForTimeout(500)
    },
  },
  { name: 'notification-preferences', path: '/app/settings/notifications' },
  { name: 'user-management', path: '/app/admin/users' },
]

async function login(page: import('@playwright/test').Page) {
  // Set locale before any navigation so the app picks it up on first load
  await page.addInitScript((lang: string) => {
    localStorage.setItem('locale', lang)
  }, LANG)

  // Navigate to the app — Auth0 may auto-redirect if session exists
  await page.goto(`${BASE_URL}/app/home`)
  await page.waitForTimeout(3000)

  // If we landed on the dashboard, we're already authenticated
  if (page.url().includes('/app/home')) {
    const heading = page.getByRole('heading', { name: /Dashboard/i }).first()
    if (await heading.isVisible({ timeout: 10_000 }).catch(() => false)) {
      console.log('  Already authenticated, skipping login.')
      return
    }
  }

  // If redirected to Auth0, fill in credentials
  if (page.url().includes('auth0')) {
    if (!EMAIL || !PASSWORD) {
      throw new Error(
        'Not authenticated and no credentials found.\n' +
          'Set E2E_AUTH0_USERNAME and E2E_AUTH0_PASSWORD in frontend/.env',
      )
    }

    const usernameInput = page
      .locator('input[name="username"], input#username, input[type="email"]')
      .first()
    await usernameInput.waitFor({ state: 'visible', timeout: 45_000 })
    await usernameInput.fill(EMAIL)

    const passwordInput = page
      .locator('input[name="password"], input#password, input[type="password"]')
      .first()

    if (!(await passwordInput.isVisible({ timeout: 2_000 }).catch(() => false))) {
      const continueBtn = page.getByRole('button', { name: /continue|next/i }).first()
      if (await continueBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
        await continueBtn.click()
      }
    }

    await passwordInput.waitFor({ state: 'visible', timeout: 45_000 })
    await passwordInput.fill(PASSWORD)

    const submitBtn = page
      .getByRole('button', { name: /continue|log in|sign in/i })
      .first()
    if (await submitBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await submitBtn.click()
    } else {
      await page.locator('button[type="submit"], button[name="action"]').first().click()
    }

    const consentBtn = page.getByRole('button', { name: /accept|authorize|allow/i }).first()
    if (await consentBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await consentBtn.click()
    }

    await page.waitForURL(/localhost:5173/, { timeout: 60_000 })
    await page.waitForTimeout(2000)
    return
  }

  // On the landing page — click sign in
  const signInButton = page.getByRole('button', { name: /sign in|anmelden/i }).first()
  if (await signInButton.isVisible({ timeout: 3000 }).catch(() => false)) {
    if (!EMAIL || !PASSWORD) {
      throw new Error(
        'Not authenticated and no credentials found.\n' +
          'Set E2E_AUTH0_USERNAME and E2E_AUTH0_PASSWORD in frontend/.env',
      )
    }

    await signInButton.click()
    await page.waitForURL(/auth0/, { timeout: 15_000 })

    const usernameInput = page
      .locator('input[name="username"], input#username, input[type="email"]')
      .first()
    await usernameInput.waitFor({ state: 'visible', timeout: 45_000 })
    await usernameInput.fill(EMAIL)

    const passwordInput = page
      .locator('input[name="password"], input#password, input[type="password"]')
      .first()

    if (!(await passwordInput.isVisible({ timeout: 2_000 }).catch(() => false))) {
      const continueBtn = page.getByRole('button', { name: /continue|next/i }).first()
      if (await continueBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
        await continueBtn.click()
      }
    }

    await passwordInput.waitFor({ state: 'visible', timeout: 45_000 })
    await passwordInput.fill(PASSWORD)

    const submitBtn = page
      .getByRole('button', { name: /continue|log in|sign in/i })
      .first()
    if (await submitBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await submitBtn.click()
    } else {
      await page.locator('button[type="submit"], button[name="action"]').first().click()
    }

    await page.waitForURL(/localhost:5173/, { timeout: 60_000 })
    await page.waitForTimeout(2000)
  }
}

test(`Take landing page screenshots [${LANG}]`, async ({ page }) => {
  await page.setViewportSize(VIEWPORT)
  await login(page)

  for (const { name, path, action, fullPage } of PAGES) {
    await page.goto(`${BASE_URL}${path}`)
    await page.waitForTimeout(3000)

    if (action) {
      await action(page)
    }

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/${name}.png`,
      type: 'png',
      fullPage: fullPage ?? false,
    })

    console.log(`  Saved: ${SCREENSHOT_DIR}/${name}.png`)
  }

  console.log(`\nAll landing page screenshots captured! [${LANG}]`)
})

test(`Take How It Works step screenshots [${LANG}]`, async ({ page }) => {
  await page.setViewportSize(VIEWPORT)
  await login(page)

  // Navigate to event creation
  await page.goto(`${BASE_URL}/app/events/create`)
  await page.waitForTimeout(3000)

  // --- Step 1: Event Details ---
  await page.getByRole('textbox').first().fill('Kirchentag 2026')
  await page.locator('textarea').fill(
    'Annual church congress with multiple duty stations across the venue.',
  )
  await page.getByRole('textbox').nth(2).fill('Messe Hannover')
  await page.getByRole('textbox').nth(3).fill('Conference')

  // Screenshot the accordion item (header + content) by going up from the region
  const detailsSection = page
    .getByRole('region', { name: /Event Details|Veranstaltungsdetails/ })
    .locator('..')
  await detailsSection.screenshot({
    path: `${SCREENSHOT_DIR}/create-step1-details.png`,
    type: 'png',
  })
  console.log(`  Saved: ${SCREENSHOT_DIR}/create-step1-details.png`)

  // Click Next to move to Event Group
  await page.getByRole('button', { name: labels.next }).click()
  await page.waitForTimeout(500)

  // Skip Event Group, click Next to move to Dates
  await page.getByRole('button', { name: labels.next }).click()
  await page.waitForTimeout(500)

  // --- Step 2: Choose Dates ---
  await page.getByRole('radio', { name: labels.dateRange }).click()
  await page.waitForTimeout(300)

  // Pick start date — use data-value attribute which is locale-independent
  const startPicker = page.getByRole('button', { name: labels.pickADate }).first()
  await startPicker.click()
  await page.waitForTimeout(300)
  await page.locator('button[data-value="2026-03-20"]').click()
  await page.waitForTimeout(300)

  // Pick end date
  const endPicker = page.getByRole('button', { name: labels.pickADate })
  await endPicker.click()
  await page.waitForTimeout(300)
  await page.locator('button[data-value="2026-03-22"]').click()
  await page.waitForTimeout(300)

  const datesSection = page
    .getByRole('region', { name: /Event Dates|Veranstaltungstermine/ })
    .locator('..')
  await datesSection.screenshot({
    path: `${SCREENSHOT_DIR}/create-step2-dates.png`,
    type: 'png',
  })
  console.log(`  Saved: ${SCREENSHOT_DIR}/create-step2-dates.png`)

  // Click Next to move to Schedule & Slots
  await page.getByRole('button', { name: labels.next }).click()
  await page.waitForTimeout(500)

  // --- Step 3: Configure Schedule ---
  await page.getByRole('button', { name: labels.addException }).click()
  await page.waitForTimeout(300)

  // Select exception date
  await page.getByRole('combobox').filter({ hasText: /Pick a date|Datum auswählen/ }).click()
  await page.waitForTimeout(300)
  // Select the second date option (Saturday) — works regardless of locale
  await page.getByRole('option').nth(1).click()
  await page.waitForTimeout(300)

  // Change exception start time to 08:00
  const exceptionStartTime = page.locator('input[placeholder="HH:MM"]').nth(2)
  await exceptionStartTime.fill('08:00')
  await page.waitForTimeout(500)

  // Click elsewhere to close any popover
  await page.getByText(labels.defaultStartTime).click()
  await page.waitForTimeout(300)

  const scheduleSection = page
    .getByRole('region', { name: /Schedule & Slots|Zeitplan & Schichten/ })
    .locator('..')
  await scheduleSection.screenshot({
    path: `${SCREENSHOT_DIR}/create-step3-schedule.png`,
    type: 'png',
  })
  console.log(`  Saved: ${SCREENSHOT_DIR}/create-step3-schedule.png`)

  // Click Next to move to Preview
  await page.getByRole('button', { name: labels.next }).click()
  await page.waitForTimeout(500)

  // --- Step 5: Preview & Exclude ---
  await page.getByText('12:00 - 12:30').first().click()
  await page.waitForTimeout(300)
  await page.getByText('12:30 - 13:00').first().click()
  await page.waitForTimeout(300)

  const previewSection = page
    .getByRole('region', { name: /Preview|Vorschau/ })
    .locator('..')
  await previewSection.screenshot({
    path: `${SCREENSHOT_DIR}/create-step5-preview.png`,
    type: 'png',
  })
  console.log(`  Saved: ${SCREENSHOT_DIR}/create-step5-preview.png`)

  console.log(`\nAll How It Works screenshots captured! [${LANG}]`)
})
