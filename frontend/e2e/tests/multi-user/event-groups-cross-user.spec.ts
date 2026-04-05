/**
 * Cross-user E2E tests -- scenarios requiring both an admin and a member session.
 *
 * Uses adminPage/memberPage fixtures for isolated auth.
 */
import { expect, test } from '../../fixtures.js'
import {
  api,
  clearAvailability,
  createGroup,
  deleteGroup,
  futureDate,
  uniqueName,
} from '../../helpers/api.js'
import type { EventGroupRead } from '../../helpers/api.js'

// ── Admin creates group -> member sees it ─────────────────────────────────────

test.describe('Cross-user – visibility', () => {
  test('admin-published group is visible to member', async ({ adminPage, memberPage }) => {
    await adminPage.goto('/app/event-groups')
    const group = await createGroup(adminPage, uniqueName('E2E Cross Published Group'))

    try {
      await memberPage.goto('/app/event-groups')
      await expect(memberPage.getByRole('heading', { name: group.name })).toBeVisible()
    } finally {
      await deleteGroup(adminPage, group.id)
    }
  })

  test('admin draft group is hidden from member', async ({ adminPage, memberPage }) => {
    await adminPage.goto('/app/event-groups')
    const draft = await createGroup(adminPage, uniqueName('E2E Cross Draft Group'), 'draft')

    try {
      await memberPage.goto('/app/event-groups')
      await expect(memberPage.getByText(draft.name)).toBeHidden()
    } finally {
      await deleteGroup(adminPage, draft.id)
    }
  })
})

// ── Member registers availability -> admin sees it ────────────────────────────

test.describe('Cross-user – availability flow', () => {
  let group: EventGroupRead

  test.beforeEach(async ({ adminPage }) => {
    await adminPage.goto('/app/event-groups')
    group = await createGroup(adminPage, uniqueName('E2E Cross Availability Group'))
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteGroup(adminPage, group.id)
  })

  test('member availability appears in admin member table', async ({ adminPage, memberPage }) => {
    // Member registers availability via UI
    await memberPage.goto(`/app/event-groups/${group.id}`)
    await memberPage.getByTestId('btn-availability').click()
    await memberPage.getByTestId('availability-type-fully_available').click()
    await memberPage.getByTestId('btn-save').click()
    await expect(memberPage.getByTestId('btn-availability')).toBeVisible()

    // Admin sees the entry in the member availability table
    await adminPage.goto(`/app/event-groups/${group.id}`)
    const adminTable = adminPage.getByTestId('section-admin-availabilities')
    await expect(adminTable.getByText(/fully.?available|open to be requested/i)).toBeVisible()

    await clearAvailability(memberPage, group.id).catch(() => {})
  })

  test('member removing availability is reflected in admin table', async ({
    adminPage,
    memberPage,
  }) => {
    // Pre-seed availability as member via API
    await memberPage.goto(`/app/event-groups/${group.id}`)
    await api(memberPage, 'POST', `/event-groups/${group.id}/availability`, {
      availability_type: 'fully_available',
      dates: [],
    })

    // Member removes it via UI
    await memberPage.reload()
    await memberPage.getByTestId('btn-remove-availability').click()

    // Handle app-level confirmation dialog
    const confirmBtn = memberPage.getByRole('button', { name: /confirm|bestätigen/i })
    if (await confirmBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await confirmBtn.click()
    }
    await expect(memberPage.getByTestId('btn-availability')).toBeVisible()

    // Admin table shows empty state
    await adminPage.goto(`/app/event-groups/${group.id}`)
    const adminTable = adminPage.getByTestId('section-admin-availabilities')
    await expect(adminTable.getByText(/no.*(members|registrations|availability)/i)).toBeVisible()
  })

  test('multiple members availability visible to admin', async ({ adminPage, memberPage }) => {
    // Admin registers as fully available
    await adminPage.goto(`/app/event-groups/${group.id}`)
    await api(adminPage, 'POST', `/event-groups/${group.id}/availability`, {
      availability_type: 'fully_available',
      dates: [],
    })

    // Member registers with specific dates
    await memberPage.goto(`/app/event-groups/${group.id}`)
    await api(memberPage, 'POST', `/event-groups/${group.id}/availability`, {
      availability_type: 'specific_dates',
      dates: [futureDate(30), futureDate(31)],
    })

    // Admin sees both entries in the table
    await adminPage.reload()
    const adminTable = adminPage.getByTestId('section-admin-availabilities')
    const rows = adminTable.getByText(/fully.?available|specific.?dates/i)
    await expect(rows).toHaveCount(2)

    await clearAvailability(adminPage, group.id).catch(() => {})
    await clearAvailability(memberPage, group.id).catch(() => {})
  })
})
