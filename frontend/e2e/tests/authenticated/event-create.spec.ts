/**
 * E2E tests for Event Creation wizard.
 */
import { expect, test } from '../../fixtures.js'
import { api, deleteEvent } from '../../helpers/api.js'

// ── page access ──────────────────────────────────────────────────────────────

test.describe('Event Create – page access', () => {
  test('can navigate to create page', async ({ adminPage: page }) => {
    await page.goto('/app/events/create')
    await expect(page).toHaveURL(/\/app\/events\/create/)
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('shows back button', async ({ adminPage: page }) => {
    await page.goto('/app/events/create')
    await expect(page.getByTestId('btn-back')).toBeVisible()
  })

  test('back button navigates to events', async ({ adminPage: page }) => {
    await page.goto('/app/events/create')
    await page.getByTestId('btn-back').click()
    await expect(page).toHaveURL(/\/app\/events$/)
  })
})

// ── form sections ────────────────────────────────────────────────────────────

test.describe('Event Create – form wizard', () => {
  test('shows accordion sections', async ({ adminPage: page }) => {
    await page.goto('/app/events/create')
    // The accordion sections are visible via test IDs
    await expect(page.getByTestId('section-event-details')).toBeVisible()
  })

  test('can fill event name in details section', async ({ adminPage: page }) => {
    await page.goto('/app/events/create')
    const nameInput = page.getByTestId('input-event-name')
    await nameInput.fill('E2E Create Test Event')
    await expect(nameInput).toHaveValue('E2E Create Test Event')
  })

  test('Next button advances to next section', async ({ adminPage: page }) => {
    await page.goto('/app/events/create')
    const nameInput = page.getByTestId('input-event-name')
    await nameInput.fill('Test Event')
    // Click the Next button inside the active (details) section (matches both EN "Next" and DE "Weiter")
    await page
      .getByTestId('section-event-details')
      .getByRole('button', { name: /next|weiter/i })
      .click()
    // Second section should now be visible (Event Group)
    await expect(page.getByTestId('section-event-group')).toBeVisible()
  })
})

// ── cleanup ──────────────────────────────────────────────────────────────────

test.afterEach(async ({ adminPage: page }) => {
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
