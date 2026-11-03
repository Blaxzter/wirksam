/**
 * Cross-user E2E tests for the event picker and availability flows.
 *
 * Replaces the old event-groups-cross-user.spec.ts which operated on the
 * removed /app/events/:id/availability route. Under the new scoped-UI model
 * the worker fixture points both users' selected_event_id at the same
 * `workerEvent`, so these tests exercise that shared event.
 *
 * Availability is now an inline editor and the admin team view renders a
 * heatmap with one row per member (commit 649a9f5).
 */
import type { Locator, Page } from '@playwright/test'

import { expect, test } from '../../fixtures.js'
import {
  addMember,
  api,
  clearAvailability,
  createEvent,
  deleteEvent,
  futureDate,
  uniqueName,
} from '../../helpers/api.js'

// ── Picker visibility (admin-published vs draft) ─────────────────────────────

test.describe('Cross-user – picker visibility', () => {
  test('an event the member joined appears in My events', async ({
    adminPage,
    memberPage,
    memberUser,
  }) => {
    const event = await createEvent(adminPage, uniqueName('E2E Cross Published'))
    try {
      await addMember(adminPage, memberPage, event.id, memberUser.email)
      await memberPage.goto('/app/select-event?mode=switch')
      await expect(memberPage.getByText(event.name).first()).toBeVisible()
    } finally {
      await deleteEvent(adminPage, event.id)
    }
  })

  test('a public event the member has not joined shows under Discover', async ({
    adminPage,
    memberPage,
  }) => {
    // Discover lists the first 100 by start date, and every worker's event starts
    // tomorrow and stays in the database. Starting today keeps this one in reach
    // however many of them a reused stack has piled up.
    const event = await createEvent(
      adminPage,
      uniqueName('E2E Cross Discover'),
      'published',
      'public',
      { start: futureDate(0), end: futureDate(4) },
    )
    try {
      await memberPage.goto('/app/select-event?mode=switch')
      // Not a member yet, so it must not be in the "My events" list…
      await expect(memberPage.getByText(event.name)).toBeHidden()
      // …but it is public, so Discover offers it.
      await memberPage.getByTestId('tab-discover').click()
      await expect(memberPage.getByText(event.name).first()).toBeVisible()
    } finally {
      await deleteEvent(adminPage, event.id)
    }
  })

  test('a private event the member is not in stays hidden everywhere', async ({
    adminPage,
    memberPage,
  }) => {
    const secret = await createEvent(
      adminPage,
      uniqueName('E2E Cross Private'),
      'published',
      'private',
    )
    try {
      await memberPage.goto('/app/select-event?mode=switch')
      await expect(memberPage.getByText(secret.name)).toBeHidden()
      await memberPage.getByTestId('tab-discover').click()
      await expect(memberPage.getByText(secret.name)).toBeHidden()
    } finally {
      await deleteEvent(adminPage, secret.id)
    }
  })
})

// ── Availability flow between member and admin ───────────────────────────────

/**
 * Open the admin's availability page once its team list has arrived.
 *
 * The page asks for the team's availability once, after the admin's own, and a
 * write the test made before is already in that answer: the backend commits
 * before it responds (`get_db` in `app/api/deps.py`). So one visit is enough,
 * and what has to be waited for is the page, which with a dozen workers on the
 * Docker stack takes up to two seconds after `goto` to fetch both.
 *
 * This wait starts before `goto`, so it has to outlast the whole page load as
 * well. The 5 s action timeout from the config does not: a busy stack can spend
 * that on the load alone, before the page has asked for anything.
 */
async function openTeamView(adminPage: Page, eventId: string): Promise<Locator> {
  const listed = adminPage.waitForResponse(
    (r) =>
      r.request().method() === 'GET' &&
      new URL(r.url()).pathname.endsWith(`/events/${eventId}/availabilities`),
    { timeout: 20_000 },
  )
  await adminPage.goto('/app/availability')
  expect((await listed).ok()).toBe(true)
  return adminPage.getByTestId('section-admin-availabilities')
}

test.describe('Cross-user – availability flow', () => {
  test.beforeEach(async ({ adminPage, memberPage, workerEvent }) => {
    await clearAvailability(adminPage, workerEvent.id).catch(() => {})
    await clearAvailability(memberPage, workerEvent.id).catch(() => {})
  })

  test.afterEach(async ({ adminPage, memberPage, workerEvent }) => {
    await clearAvailability(adminPage, workerEvent.id).catch(() => {})
    await clearAvailability(memberPage, workerEvent.id).catch(() => {})
  })

  test('member availability appears in admin team heatmap', async ({
    adminPage,
    memberPage,
    memberUser,
    workerEvent,
  }) => {
    await memberPage.goto('/app/availability')
    await memberPage.getByTestId('availability-type-fully_available').first().click()
    await memberPage.getByTestId('btn-save').click()
    await expect(memberPage.getByTestId('btn-remove-availability')).toBeVisible()

    const team = await openTeamView(adminPage, workerEvent.id)
    await expect(team.getByText(memberUser.name).first()).toBeVisible()
  })

  test('member removing availability is reflected in admin team view', async ({
    adminPage,
    memberPage,
    workerEvent,
  }) => {
    await api(memberPage, 'POST', `/events/${workerEvent.id}/availability`, {
      availability_type: 'fully_available',
      dates: [],
    })

    await memberPage.goto('/app/availability')
    await memberPage.getByTestId('btn-remove-availability').click()

    // App-level confirm-destructive dialog
    const confirmBtn = memberPage.getByRole('button', { name: /confirm|bestätigen/i })
    if (await confirmBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await confirmBtn.click()
    }
    await expect(memberPage.getByTestId('btn-remove-availability')).toBeHidden()

    const team = await openTeamView(adminPage, workerEvent.id)
    await expect(
      team.getByText(/no teammates have registered|noch keine teammitglieder/i),
    ).toBeVisible()
  })

  test('admin sees multiple members in the team heatmap', async ({
    adminPage,
    memberPage,
    workerEvent,
    adminUser,
    memberUser,
  }) => {
    await api(adminPage, 'POST', `/events/${workerEvent.id}/availability`, {
      availability_type: 'fully_available',
      dates: [],
    })
    await api(memberPage, 'POST', `/events/${workerEvent.id}/availability`, {
      availability_type: 'specific_dates',
      dates: [futureDate(10), futureDate(11)],
    })

    const team = await openTeamView(adminPage, workerEvent.id)
    await expect(team.getByText(adminUser.name).first()).toBeVisible()
    await expect(team.getByText(memberUser.name).first()).toBeVisible()
  })
})
