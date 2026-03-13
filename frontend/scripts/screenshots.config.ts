import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from '@playwright/test'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// Load .env manually without requiring dotenv
const envPath = resolve(__dirname, '..', '.env')
try {
  const envContent = readFileSync(envPath, 'utf-8')
  for (const line of envContent.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eqIndex = trimmed.indexOf('=')
    if (eqIndex === -1) continue
    const key = trimmed.slice(0, eqIndex).trim()
    const value = trimmed.slice(eqIndex + 1).trim()
    if (!process.env[key]) {
      process.env[key] = value
    }
  }
} catch {
  // .env file not found — rely on existing env vars
}

export default defineConfig({
  testDir: '.',
  testMatch: 'take-screenshots.ts',
  timeout: 180_000,
  use: {
    baseURL: 'http://localhost:5173',
    headless: !!process.env.CI,
  },
})
