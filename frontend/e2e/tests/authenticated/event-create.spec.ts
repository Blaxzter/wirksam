/**
 * E2E tests for Event Creation wizard.
 */

import { expect, test } from '@playwright/test'
import { api, deleteEvent } from '../../helpers/api'

// ── page access ──────────────────────────────────────────────────────────────

test.describe('Event Create – page access', () => {
  test('can navigate to create page', async ({ page }) => {
    await page.goto('/app/events/create')
    await expect(page).toHaveURL(/\/app\/events\/create/)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('shows back button', async ({ page }) => {
    await page.goto('/app/events/create')
    await expect(page.getByRole('button', { name: /back/i })).toBeVisible()
  })

  test('back button navigates to events', async ({ page }) => {
    await page.goto('/app/events/create')
    await page.getByRole('button', { name: /back/i }).click()
    await expect(page).toHaveURL(/\/app\/events$/)
  })
})

// ── form sections ────────────────────────────────────────────────────────────

test.describe('Event Create – form wizard', () => {
  test('shows accordion sections', async ({ page }) => {
    await page.goto('/app/events/create')
    // The accordion sections are visible as triggers
    await expect(page.getByText(/event details|details/i).first()).toBeVisible()
  })

  test('can fill event name in details section', async ({ page }) => {
    await page.goto('/app/events/create')
    // The name input should be in the first section
    const nameInput = page.locator('input').first()
    await nameInput.fill('E2E Create Test Event')
    await expect(nameInput).toHaveValue('E2E Create Test Event')
  })

  test('Next button advances to next section', async ({ page }) => {
    await page.goto('/app/events/create')
    const nameInput = page.locator('input').first()
    await nameInput.fill('Test Event')
    await page.getByRole('button', { name: /next/i }).click()
    // Second section should now be visible (Event Group)
    await expect(page.getByText(/existing|none/i).first()).toBeVisible()
  })
})

// ── cleanup ──────────────────────────────────────────────────────────────────

test.afterEach(async ({ page }) => {
  try {
    const events = await api<{ items: Array<{ id: string; name: string }> }>(
      page,
      'GET',
      '/events/?limit=100',
    )
    for (const event of events.items) {
      if (event.name.startsWith('E2E Create') || event.name.startsWith('E2E Full')) {
        await deleteEvent(page, event.id).catch(() => {})
      }
    }
  } catch {
    // Best effort cleanup
  }
})
