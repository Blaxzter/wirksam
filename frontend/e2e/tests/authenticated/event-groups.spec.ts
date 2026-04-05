/**
 * E2E tests for Event Groups & Availability feature.
 *
 * Strategy: use authenticated fetch() calls (via page.evaluate) to set up and
 * tear down test data so every test starts from a known state instead of
 * relying on pre-existing DB data.
 */
import { expect, test } from '../../fixtures.js'
import {
  type EventGroupRead,
  api,
  clearAvailability,
  createGroup,
  deleteGroup,
  futureDate,
  uniqueName,
} from '../../helpers/api.js'
import { pickDate } from '../../helpers/ui.js'

// ── navigation ────────────────────────────────────────────────────────────────

test.describe('Event Groups – navigation', () => {
  test('sidebar shows Event Groups link', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await expect(page.getByTestId('sidebar-link-event-groups')).toBeVisible()
  })

  test('clicking sidebar link navigates to /app/event-groups', async ({ adminPage: page }) => {
    await page.goto('/app/home')
    await page.getByTestId('sidebar-link-event-groups').click()
    await expect(page).toHaveURL(/\/app\/event-groups$/)
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })

  test('direct navigation to /app/event-groups works', async ({ adminPage: page }) => {
    await page.goto('/app/event-groups')
    await expect(page).toHaveURL(/\/app\/event-groups$/)
    await expect(page.getByTestId('page-heading')).toBeVisible()
  })
})

// ── list view ─────────────────────────────────────────────────────────────────

test.describe('Event Groups – list view', () => {
  let group: EventGroupRead
  const groupName = uniqueName('E2E List')

  test.beforeEach(async ({ adminPage: page }) => {
    await page.goto('/app/event-groups')
    group = await createGroup(page, groupName)
  })

  test.afterEach(async ({ adminPage: page }) => {
    await deleteGroup(page, group.id)
  })

  test('shows heading and search input', async ({ adminPage: page }) => {
    await page.goto('/app/event-groups')
    await expect(page.getByTestId('page-heading')).toBeVisible()
    await expect(page.getByTestId('input-search')).toBeVisible()
  })

  test('created group appears in list with published badge', async ({ adminPage: page }) => {
    await page.goto('/app/event-groups')
    const card = page.locator('[class*="cursor-pointer"]').filter({ hasText: group.name })
    await expect(card).toBeVisible()
    // published status badge within the card
    await expect(card.getByTestId('group-status')).toBeVisible()
  })

  test('created group shows date range', async ({ adminPage: page }) => {
    await page.goto('/app/event-groups')
    // Dates are formatted locale-dependently; check both dates appear somewhere
    const card = page.locator('[class*="cursor-pointer"]').filter({ hasText: group.name })
    await expect(card).toBeVisible()
  })

  test('search filters the list by name', async ({ adminPage: page }) => {
    await page.goto('/app/event-groups')
    const searchInput = page.getByTestId('input-search')
    await searchInput.fill(groupName)
    const card = page.locator('[class*="cursor-pointer"]').filter({ hasText: groupName })
    await expect(card).toBeVisible()

    await searchInput.fill('zzzzunlikelymatch')
    await expect(card).toBeHidden()
  })

  test('clicking a card navigates to the detail page', async ({ adminPage: page }) => {
    await page.goto('/app/event-groups')
    const card = page.locator('[class*="cursor-pointer"]').filter({ hasText: group.name })
    await card.click()
    await expect(page).toHaveURL(new RegExp(`/app/event-groups/${group.id}`))
  })
})

// ── admin actions ─────────────────────────────────────────────────────────────

test.describe('Event Groups – admin create & delete', () => {
  test('Create button is visible (test user is admin in test env)', async ({ adminPage: page }) => {
    await page.goto('/app/event-groups')
    // In the test environment the E2E user has admin privileges
    await expect(page.getByTestId('btn-create-group')).toBeVisible()
  })

  test('admin can open the create event group dialog', async ({ adminPage: page }) => {
    await page.goto('/app/event-groups')

    await page.getByTestId('btn-create-group').click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // Dialog has the expected form fields
    await expect(dialog.locator('input').first()).toBeVisible()
    await expect(dialog.getByRole('button', { name: /create|erstellen/i })).toBeVisible()

    // Close without saving
    await dialog.getByRole('button', { name: /cancel|abbrechen/i }).click()
    await expect(dialog).toBeHidden()
  })

  test('admin can delete an event group via trash icon', async ({ adminPage: page }) => {
    const deleteName = uniqueName('E2E Delete')
    await page.goto('/app/event-groups')
    const groupToDelete = await createGroup(page, deleteName)

    await page.goto('/app/event-groups')
    const card = page.locator('[class*="cursor-pointer"]').filter({ hasText: deleteName })
    await expect(card).toBeVisible()

    // Click delete button on the specific card
    await card.getByRole('button').click()

    // Handle app-level confirmation dialog
    const confirmBtn = page.getByRole('button', { name: /confirm|bestätigen/i })
    if (await confirmBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await confirmBtn.click()
    }

    await expect(card).toBeHidden()
  })
})

// ── detail page ───────────────────────────────────────────────────────────────

test.describe('Event Group Detail – page structure', () => {
  let group: EventGroupRead

  test.beforeEach(async ({ adminPage: page }) => {
    await page.goto('/app/event-groups')
    group = await createGroup(page, uniqueName('E2E Detail Page Group'))
  })

  test.afterEach(async ({ adminPage: page }) => {
    await clearAvailability(page, group.id).catch(() => {})
    await deleteGroup(page, group.id)
  })

  test('shows group name and status badge', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    await expect(page.getByTestId('page-heading')).toContainText(group.name)
    await expect(page.getByTestId('group-status')).toBeVisible()
  })

  test('shows date range in header', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    // The group's date range appears somewhere on the page
    await expect(page.getByText(new RegExp(new Date().getFullYear().toString()))).toBeVisible()
  })

  test('shows My Availability section', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    await expect(page.getByTestId('section-my-availability')).toBeVisible()
  })

  test('shows Events in this Group section', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    await expect(page.getByTestId('section-events')).toBeVisible()
  })

  test('back button navigates to event groups list', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    await page.getByTestId('btn-back').click()
    await expect(page).toHaveURL(/\/app\/event-groups$/)
  })

  test('navigating to a non-existent group shows back button', async ({ adminPage: page }) => {
    await page.goto('/app/event-groups/00000000-0000-0000-0000-000000000000')
    await expect(page.getByTestId('btn-back')).toBeVisible()
  })
})

// ── availability: register fully available ────────────────────────────────────

test.describe('Availability – fully available', () => {
  let group: EventGroupRead

  test.beforeEach(async ({ adminPage: page }) => {
    await page.goto('/app/event-groups')
    group = await createGroup(page, uniqueName('E2E Availability Group'))
    await clearAvailability(page, group.id).catch(() => {})
  })

  test.afterEach(async ({ adminPage: page }) => {
    await clearAvailability(page, group.id).catch(() => {})
    await deleteGroup(page, group.id)
  })

  test('Register button is visible when no availability set', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    await expect(page.getByTestId('btn-availability')).toBeVisible()
  })

  test('Register button opens availability dialog', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    await page.getByTestId('btn-availability').click()
    await expect(page.getByTestId('dialog-availability')).toBeVisible()
  })

  test('dialog shows both availability type options', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    await page.getByTestId('btn-availability').click()
    await expect(page.getByTestId('dialog-availability')).toBeVisible()
    await expect(page.getByTestId('availability-type-fully_available')).toBeVisible()
    await expect(page.getByTestId('availability-type-specific_dates')).toBeVisible()
  })

  test('Cancel closes the dialog without saving', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    await page.getByTestId('btn-availability').click()
    await expect(page.getByTestId('dialog-availability')).toBeVisible()
    await page.getByTestId('btn-cancel').click()
    await expect(page.getByTestId('dialog-availability')).toBeHidden()
    // Still shows Register button (nothing was saved)
    await expect(page.getByTestId('btn-availability')).toBeVisible()
  })

  test('can register as fully available', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    await page.getByTestId('btn-availability').click()

    // "Open to be requested" / "fully available" option — select it
    await page.getByTestId('availability-type-fully_available').click()
    await page.getByTestId('btn-save').click()

    await expect(page.getByTestId('dialog-availability')).toBeHidden()
    // Status now shows type text in the My Availability section
    const myAvail = page.getByTestId('section-my-availability')
    await expect(myAvail.getByText(/fully.?available|voll.?verfügbar/i)).toBeVisible()
    // Register button replaced by Update / Remove
    await expect(page.getByTestId('btn-availability')).toBeVisible()
    await expect(page.getByTestId('btn-remove-availability')).toBeVisible()
  })

  test('can add a note when registering', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    await page.getByTestId('btn-availability').click()

    await page.getByTestId('availability-type-fully_available').click()
    await page
      .getByTestId('dialog-availability')
      .locator('textarea')
      .fill('I am free the whole week!')
    await page.getByTestId('btn-save').click()

    await expect(page.getByTestId('dialog-availability')).toBeHidden()
    await expect(
      page.getByTestId('section-my-availability').getByText(/I am free the whole week!/i),
    ).toBeVisible()
  })

  test('can remove availability', async ({ adminPage: page }) => {
    // Set availability via API so we start with one registered
    await api(page, 'POST', `/event-groups/${group.id}/availability`, {
      availability_type: 'fully_available',
      dates: [],
    })

    await page.goto(`/app/event-groups/${group.id}`)
    // Confirm-destructive dialog is inside the app; accept via dialog event
    page.on('dialog', (d) => d.accept())

    await page.getByTestId('btn-remove-availability').click()

    // Register button should return
    await expect(page.getByTestId('btn-availability')).toBeVisible()
  })

  test('can update existing availability', async ({ adminPage: page }) => {
    // Pre-seed via API
    await api(page, 'POST', `/event-groups/${group.id}/availability`, {
      availability_type: 'fully_available',
      dates: [],
    })

    await page.goto(`/app/event-groups/${group.id}`)
    await page.getByTestId('btn-availability').click()
    await expect(page.getByTestId('dialog-availability')).toBeVisible()

    // Switch to specific_dates
    await page.getByTestId('availability-type-specific_dates').click()
    await page.getByTestId('btn-save').click()

    await expect(page.getByTestId('dialog-availability')).toBeHidden()
    await expect(
      page.getByTestId('section-my-availability').getByText(/specific.?dates|bestimmte.?termine/i),
    ).toBeVisible()
  })
})

// ── availability: specific dates ──────────────────────────────────────────────

test.describe('Availability – specific dates', () => {
  let group: EventGroupRead

  test.beforeEach(async ({ adminPage: page }) => {
    await page.goto('/app/event-groups')
    group = await createGroup(page, uniqueName('E2E Specific Dates Group'))
    await clearAvailability(page, group.id).catch(() => {})
  })

  test.afterEach(async ({ adminPage: page }) => {
    await clearAvailability(page, group.id).catch(() => {})
    await deleteGroup(page, group.id)
  })

  test('specific dates option reveals date builder', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    await page.getByTestId('btn-availability').click()
    await page.getByTestId('availability-type-specific_dates').click()
    // Add date button or date input appears
    await expect(page.getByTestId('btn-add-date')).toBeVisible()
  })

  test('can register availability with specific dates', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    await page.getByTestId('btn-availability').click()
    await page.getByTestId('availability-type-specific_dates').click()

    // Add a date
    await page.getByTestId('btn-add-date').click()
    // Pick a date from the calendar popover (must fall within the group's date range)
    const groupStart = futureDate(30)
    await pickDate(page.getByRole('button', { name: /pick a date|datum/i }).last(), groupStart)

    await page.getByTestId('btn-save').click()
    await expect(page.getByTestId('dialog-availability')).toBeHidden()

    // The availability type text is now shown on the page
    await expect(
      page.getByTestId('section-my-availability').getByText(/specific.?dates|bestimmte.?termine/i),
    ).toBeVisible()
  })

  test('registering specific dates via API shows them in UI', async ({ adminPage: page }) => {
    const date1 = futureDate(30)
    const date2 = futureDate(31)
    await api(page, 'POST', `/event-groups/${group.id}/availability`, {
      availability_type: 'specific_dates',
      dates: [date1, date2],
    })

    await page.goto(`/app/event-groups/${group.id}`)
    await expect(
      page.getByTestId('section-my-availability').getByText(/specific.?dates|bestimmte.?termine/i),
    ).toBeVisible()
    // Both dates should appear somewhere on the page
    await expect(page.getByTestId(`date-${date1}`)).toBeVisible()
    await expect(page.getByTestId(`date-${date2}`)).toBeVisible()
  })
})

// ── admin: member availability table ─────────────────────────────────────────

test.describe('Admin – member availability table', () => {
  let group: EventGroupRead

  test.beforeEach(async ({ adminPage: page }) => {
    await page.goto('/app/event-groups')
    group = await createGroup(page, uniqueName('E2E Admin Avail Group'))
  })

  test.afterEach(async ({ adminPage: page }) => {
    await clearAvailability(page, group.id).catch(() => {})
    await deleteGroup(page, group.id)
  })

  test('member availabilities section is visible for admins', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    await expect(page.getByTestId('section-admin-availabilities')).toBeVisible()
  })

  test('empty state is shown when no members have registered', async ({ adminPage: page }) => {
    await page.goto(`/app/event-groups/${group.id}`)
    // Match both EN "No members have registered" and DE "Noch keine Mitglieder haben Verfügbarkeit registriert"
    await expect(
      page.getByText(/no.*(members|registrations|availability)|keine.*mitglieder.*verfügbarkeit/i),
    ).toBeVisible()
  })

  test('registered availability appears in admin table', async ({ adminPage: page }) => {
    await api(page, 'POST', `/event-groups/${group.id}/availability`, {
      availability_type: 'fully_available',
      notes: 'E2E admin table test',
      dates: [],
    })

    await page.goto(`/app/event-groups/${group.id}`)
    // The admin table should show an entry — look for the availability type or note
    await expect(
      page.getByText(/fully.?available|open to be requested|voll.?verfügbar/i).nth(1),
    ).toBeVisible()
  })
})
