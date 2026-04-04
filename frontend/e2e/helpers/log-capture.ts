/**
 * Playwright fixture for capturing backend logs during E2E tests.
 *
 * Usage in a test file:
 *   import { test } from '../helpers/log-capture'
 *
 * This extends the base Playwright test with automatic beforeEach/afterEach
 * that captures backend logs and attaches them to the test report on failure.
 */

import fs from 'node:fs'
import path from 'node:path'
import { test as base } from '@playwright/test'

const API = process.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'
const LOG_DIR = path.resolve('e2e/test-logs')

export const test = base.extend<{ backendLogs: void }>({

  backendLogs: [async ({ request }, use, testInfo) => {
    // Start capturing before the test
    await request.post(`${API}/debug/start-log-capture`).catch(() => {
      // Debug endpoint may not be available — silently skip
    })

    await use()

    // Stop capturing and collect logs
    const resp = await request.post(`${API}/debug/stop-log-capture`).catch(() => null)
    if (!resp) return

    const { log } = (await resp.json()) as { log: string }
    if (!log) return

    // Always attach to test report (visible in HTML reporter)
    await testInfo.attach('backend-logs', { body: log, contentType: 'text/plain' })

    // On failure, also write to a file for quick access
    if (testInfo.status !== testInfo.expectedStatus) {
      fs.mkdirSync(LOG_DIR, { recursive: true })
      const safeName = testInfo.title.replace(/[^a-z0-9]+/gi, '-').slice(0, 80)
      const logFile = path.join(LOG_DIR, `${safeName}-${Date.now()}.log`)
      fs.writeFileSync(logFile, log)
    }
  }, { auto: true }],
})

export { expect } from '@playwright/test'
