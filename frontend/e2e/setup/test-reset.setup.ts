/**
 * Global setup: reset all test data before the isolated test suite runs.
 * This ensures a clean slate regardless of what previous runs left behind.
 */
import { test as setup } from '@playwright/test'

const API = process.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'

setup('reset test data', async () => {
  const resp = await fetch(`${API}/testing/reset`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to reset test data: ${resp.status} ${await resp.text()}`)
  }
  const result = (await resp.json()) as { deleted_users: number }
  console.log(`Reset complete: deleted ${result.deleted_users} test users`)
})
