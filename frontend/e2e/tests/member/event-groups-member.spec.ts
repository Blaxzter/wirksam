/**
 * E2E tests from a regular (non-admin) member's perspective.
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
import { pickDate } from '../../helpers/ui.js'

// ── RBAC: member cannot create or delete ─────────────────────────────────────

test.describe('Member – RBAC', () => {
  let group: EventGroupRead

  test.beforeEach(async ({ adminPage }) => {
    await adminPage.goto('/app/event-groups')
    group = await createGroup(adminPage, uniqueName('E2E RBAC Member Test Group'))
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteGroup(adminPage, group.id)
  })

  test('member does not see Create button', async ({ memberPage: member }) => {
    await member.goto('/app/event-groups')
    await expect(member.getByTestId('btn-create-group')).toBeHidden()
  })

  test('member does not see Delete button on event group cards', async ({ memberPage: member }) => {
    await member.goto('/app/event-groups')
    await expect(member.getByText(group.name).first()).toBeVisible()
    const card = member.locator('[class*="cursor-pointer"]').filter({ hasText: group.name })
    await expect(card.getByRole('button')).toBeHidden()
  })

  test('member does not see the member availabilities admin table', async ({
    memberPage: member,
  }) => {
    await member.goto(`/app/event-groups/${group.id}`)
    await expect(member.getByTestId('section-admin-availabilities')).toBeHidden()
  })
})

// ── Member can view published groups but not drafts ───────────────────────────

test.describe('Member – list view', () => {
  let group: EventGroupRead

  test.beforeEach(async ({ adminPage }) => {
    await adminPage.goto('/app/event-groups')
    group = await createGroup(adminPage, uniqueName('E2E Member Visible Group'))
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteGroup(adminPage, group.id)
  })

  test('member can see published event groups', async ({ memberPage: member }) => {
    await member.goto('/app/event-groups')
    await expect(member.getByText(group.name).first()).toBeVisible()
  })

  test('member cannot see draft event groups', async ({ adminPage, memberPage: member }) => {
    const draft = await createGroup(adminPage, uniqueName('E2E Hidden Draft Group'), 'draft')
    try {
      await member.goto('/app/event-groups')
      await expect(member.getByText(draft.name)).toBeHidden()
    } finally {
      await deleteGroup(adminPage, draft.id)
    }
  })

  test('member can navigate to event group detail page', async ({ memberPage: member }) => {
    await member.goto('/app/event-groups')
    await member.getByText(group.name).first().click()
    await expect(member).toHaveURL(new RegExp(`/app/event-groups/${group.id}`))
    await expect(member.getByRole('heading', { name: group.name })).toBeVisible()
  })
})

// ── Member can manage their own availability ──────────────────────────────────

test.describe('Member – availability', () => {
  let group: EventGroupRead

  test.beforeEach(async ({ adminPage }) => {
    await adminPage.goto('/app/event-groups')
    group = await createGroup(adminPage, uniqueName('E2E Member Availability Group'))
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteGroup(adminPage, group.id)
  })

  test('member sees Register Availability button when none set', async ({ memberPage: member }) => {
    await member.goto(`/app/event-groups/${group.id}`)
    await clearAvailability(member, group.id).catch(() => {})
    await member.reload()
    await expect(member.getByTestId('btn-availability')).toBeVisible()
  })

  test('member can register as fully available', async ({ memberPage: member }) => {
    await member.goto(`/app/event-groups/${group.id}`)
    await clearAvailability(member, group.id).catch(() => {})
    await member.reload()
    await member.getByTestId('btn-availability').click()
    await member.getByTestId('availability-type-fully_available').click()
    await member.getByTestId('btn-save').click()

    await expect(member.getByTestId('dialog-availability')).toBeHidden()
    await expect(member.getByText(/open to be requested|fully.?available/i)).toBeVisible()
    await expect(member.getByTestId('btn-availability')).toBeVisible()
    await expect(member.getByTestId('btn-remove-availability')).toBeVisible()
    await clearAvailability(member, group.id).catch(() => {})
  })

  test('member can register availability for specific dates', async ({ memberPage: member }) => {
    await member.goto(`/app/event-groups/${group.id}`)
    await clearAvailability(member, group.id).catch(() => {})
    await member.reload()
    await member.getByTestId('btn-availability').click()
    await member.getByTestId('availability-type-specific_dates').click()
    await member.getByTestId('btn-add-date').click()
    await pickDate(
      member.getByRole('button', { name: /pick a date|datum/i }).last(),
      futureDate(30),
    )
    await member.getByTestId('btn-save').click()

    await expect(member.getByTestId('dialog-availability')).toBeHidden()
    await expect(member.getByText(/specific dates/i)).toBeVisible()
    await clearAvailability(member, group.id).catch(() => {})
  })

  test('member can update their availability', async ({ memberPage: member }) => {
    await member.goto(`/app/event-groups/${group.id}`)
    await api(member, 'POST', `/event-groups/${group.id}/availability`, {
      availability_type: 'fully_available',
      dates: [],
    })
    await member.reload()
    await member.getByTestId('btn-availability').click()
    await member.getByTestId('availability-type-specific_dates').click()
    await member.getByTestId('btn-save').click()

    await expect(member.getByTestId('dialog-availability')).toBeHidden()
    await expect(member.getByText(/specific dates/i)).toBeVisible()
    await clearAvailability(member, group.id).catch(() => {})
  })

  test('member can remove their availability', async ({ memberPage: member }) => {
    await member.goto(`/app/event-groups/${group.id}`)
    await api(member, 'POST', `/event-groups/${group.id}/availability`, {
      availability_type: 'fully_available',
      dates: [],
    })
    await member.reload()
    member.on('dialog', (d) => d.accept())
    await member.getByTestId('btn-remove-availability').click()
    await expect(member.getByTestId('btn-availability')).toBeVisible()
  })
})
