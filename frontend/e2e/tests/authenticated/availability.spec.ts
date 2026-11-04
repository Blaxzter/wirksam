/**
 * E2E tests for Availability registration at /app/availability.
 *
 * Availability is now scoped to the user's selected_event_id. The fixture
 * sets `workerEvent` as the selected event for both admin and member, so
 * every test here operates against that shared worker event.
 *
 * The dialog-based registration flow was replaced by an inline editor on
 * the page itself (commit 649a9f5) — the mode picker, paint grid and Save
 * button live directly inside `section-my-availability`.
 */
import { expect, test } from '../../fixtures.js'
import { api, clearAvailability } from '../../helpers/api.js'

// ── page structure ───────────────────────────────────────────────────────────

test.describe('Availability – page structure', () => {
  test.beforeEach(async ({ adminPage: page, workerEvent }) => {
    await clearAvailability(page, workerEvent.id).catch(() => {})
  })

  test('heading and My Availability section are visible', async ({ adminPage: page }) => {
    await page.goto('/app/availability')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expect(page.getByTestId('section-my-availability')).toBeVisible()
  })

  test('admin sees the member availabilities section', async ({ adminPage: page }) => {
    await page.goto('/app/availability')
    await expect(page.getByTestId('section-admin-availabilities')).toBeVisible()
  })

  test('mode picker shows all three availability types', async ({ adminPage: page }) => {
    await page.goto('/app/availability')
    // The desktop picker is hidden on mobile and vice versa, so use .first()
    // to match whichever variant the viewport rendered.
    await expect(page.getByTestId('availability-type-fully_available').first()).toBeVisible()
    await expect(page.getByTestId('availability-type-specific_dates').first()).toBeVisible()
    await expect(page.getByTestId('availability-type-time_range').first()).toBeVisible()
  })
})

// ── register fully available ─────────────────────────────────────────────────

test.describe('Availability – fully available', () => {
  test.beforeEach(async ({ adminPage: page, workerEvent }) => {
    await clearAvailability(page, workerEvent.id).catch(() => {})
  })

  test.afterEach(async ({ adminPage: page, workerEvent }) => {
    await clearAvailability(page, workerEvent.id).catch(() => {})
  })

  test('Save button is disabled when there are no changes', async ({ adminPage: page }) => {
    await page.goto('/app/availability')
    // Fresh state with no availability registered → nothing dirty → Save disabled
    await expect(page.getByTestId('btn-save')).toBeDisabled()
  })

  test('a mode cannot be picked before the saved one has loaded', async ({ adminPage: page }) => {
    // Hold the saved availability back. A pick made before it arrives would
    // be overwritten by it and leave nothing to save.
    let release = () => {}
    const held = new Promise<void>((resolve) => (release = resolve))
    await page.route('**/availability/me', async (route) => {
      await held
      await route.fallback()
    })
    await page.goto('/app/availability')
    const full = page.getByTestId('availability-type-fully_available').first()
    await expect(full).toBeDisabled()
    await expect(page.getByTestId('section-my-availability')).toHaveAttribute('aria-busy', 'true')

    release()
    await full.click()
    await expect(page.getByTestId('btn-save')).toBeEnabled()
  })

  test('can register as fully available', async ({ adminPage: page }) => {
    await page.goto('/app/availability')
    await page.getByTestId('availability-type-fully_available').first().click()
    await page.getByTestId('btn-save').click()

    const myAvail = page.getByTestId('section-my-availability')
    await expect(myAvail.getByText(/fully.?available|voll.?verfügbar/i).first()).toBeVisible()
    await expect(page.getByTestId('btn-remove-availability')).toBeVisible()
  })

  test('can remove availability', async ({ adminPage: page, workerEvent }) => {
    await api(page, 'POST', `/events/${workerEvent.id}/availability`, {
      availability_type: 'fully_available',
      dates: [],
    })

    await page.goto('/app/availability')
    await page.getByTestId('btn-remove-availability').click()

    // App-level confirm-destructive dialog
    const confirmBtn = page.getByRole('button', { name: /confirm|bestätigen/i })
    if (await confirmBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await confirmBtn.click()
    }

    await expect(page.getByTestId('btn-remove-availability')).toBeHidden()
  })

  test('can switch from fully available to specific dates', async ({
    adminPage: page,
    workerEvent,
  }) => {
    await api(page, 'POST', `/events/${workerEvent.id}/availability`, {
      availability_type: 'fully_available',
      dates: [],
    })

    await page.goto('/app/availability')
    await page.getByTestId('availability-type-specific_dates').first().click()
    // Switching mode should make the editor dirty → Save enabled
    await expect(page.getByTestId('btn-save')).toBeEnabled()
  })
})

// ── specific dates ───────────────────────────────────────────────────────────

test.describe('Availability – specific dates', () => {
  test.beforeEach(async ({ adminPage: page, workerEvent }) => {
    await clearAvailability(page, workerEvent.id).catch(() => {})
  })

  test.afterEach(async ({ adminPage: page, workerEvent }) => {
    await clearAvailability(page, workerEvent.id).catch(() => {})
  })

  test('specific dates mode reveals the paint grid', async ({ adminPage: page }) => {
    await page.goto('/app/availability')
    await page.getByTestId('availability-type-specific_dates').first().click()
    // Paint grid renders cells with [data-cell] attributes; existence of any
    // such cell means the grid mounted.
    await expect(page.getByTestId('section-my-availability').locator('[data-cell]').first()).toBeVisible()
  })

  test('registering specific dates via API shows them in the UI', async ({
    adminPage: page,
    workerEvent,
  }) => {
    // Use full-day dates inside the worker event window (day+1 to day+60).
    // The view interprets uniform-time entries as time_range mode (which uses
    // a slider, not the paint grid), so we send full-day dates to keep the
    // payload in specific_dates mode.
    const d1 = new Date()
    d1.setDate(d1.getDate() + 10)
    const date1 = d1.toISOString().slice(0, 10)
    const d2 = new Date()
    d2.setDate(d2.getDate() + 11)
    const date2 = d2.toISOString().slice(0, 10)

    await api(page, 'POST', `/events/${workerEvent.id}/availability`, {
      availability_type: 'specific_dates',
      dates: [date1, date2],
    })

    await page.goto('/app/availability')
    // Paint grid renders cells with [data-cell] attributes when in specific_dates mode.
    await expect(
      page.getByTestId('section-my-availability').locator('[data-cell]').first(),
    ).toBeVisible()
    // Remove button is only visible when an availability exists
    await expect(page.getByTestId('btn-remove-availability')).toBeVisible()
  })
})

// ── admin: member availability table ─────────────────────────────────────────

test.describe('Admin – member availability table', () => {
  test.beforeEach(async ({ adminPage: page, workerEvent }) => {
    await clearAvailability(page, workerEvent.id).catch(() => {})
  })

  test.afterEach(async ({ adminPage: page, workerEvent }) => {
    await clearAvailability(page, workerEvent.id).catch(() => {})
  })

  test('empty state is shown when no teammates have registered', async ({ adminPage: page }) => {
    await page.goto('/app/availability')
    await expect(
      page
        .getByTestId('section-admin-availabilities')
        .getByText(/no teammates have registered|noch keine teammitglieder/i),
    ).toBeVisible()
  })

  test('team section title is visible to admins', async ({ adminPage: page }) => {
    await page.goto('/app/availability')
    await expect(
      page
        .getByTestId('section-admin-availabilities')
        .getByText(/team availability|verfügbarkeiten der mitglieder/i),
    ).toBeVisible()
  })
})
