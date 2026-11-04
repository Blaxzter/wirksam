/**
 * E2E tests for self-service event membership.
 *
 * Replaces event-managers.spec.ts, which drove the removed admin-only
 * `/events/{id}/managers` endpoints. An event is now run by its own owner and
 * admins:
 *
 * 1. People tab UI: invite, promote, remove — no platform admin involved
 * 2. Invitation redemption: an invite is what gets you into a private event
 * 3. Scoped API permissions: an admin membership grants nothing elsewhere
 * 4. Join requests: asking into a public event, and the organiser deciding
 */
import { expect, test } from '../../fixtures.js'
import {
  type EventRead,
  addMember,
  api,
  apiStatus,
  createEvent,
  deleteEvent,
  futureDate,
  getUserIdByEmail,
  uniqueName,
} from '../../helpers/api.js'

/** Shared task payload for creating a test task in an event. */
function taskPayload(eventId: string, name: string) {
  const date = futureDate(30)
  return {
    name,
    start_date: date,
    end_date: date,
    event_id: eventId,
    schedule: {
      default_start_time: '10:00:00',
      default_end_time: '12:00:00',
      shift_duration_minutes: 60,
      people_per_shift: 2,
      remainder_mode: 'drop',
      overrides: [],
      excluded_shifts: [],
    },
  }
}

function peopleUrl(eventId: string): string {
  return `/app/event-settings/${eventId}?tab=people`
}

// ── People tab ───────────────────────────────────────────────────────────────

test.describe('Event members – People tab', () => {
  let event: EventRead

  test.beforeEach(async ({ adminPage }) => {
    event = await createEvent(adminPage, uniqueName('E2E Members UI'))
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteEvent(adminPage, event.id).catch(() => {})
  })

  test('owner sees the People tab with members, invitations and requests', async ({
    adminPage,
  }) => {
    await adminPage.goto(peopleUrl(event.id))
    await expect(adminPage.getByTestId('tab-people')).toBeVisible()
    await expect(adminPage.getByTestId('section-event-members')).toBeVisible()
    await expect(adminPage.getByTestId('section-event-invitations')).toBeVisible()
    await expect(adminPage.getByTestId('section-join-requests')).toBeVisible()
  })

  test('a freshly created event lists its creator as owner', async ({ adminPage }) => {
    await adminPage.goto(peopleUrl(event.id))
    const rows = adminPage.getByTestId('event-member-row')
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toHaveAttribute('data-role', 'owner')
  })

  test('owner can invite by email from the UI', async ({ adminPage, memberUser }) => {
    await adminPage.goto(peopleUrl(event.id))
    await adminPage.getByTestId('input-invite-emails').fill(memberUser.email)
    await adminPage.getByTestId('btn-send-invites').click()

    await expect(adminPage.getByTestId('pending-invite-row')).toContainText(memberUser.email)
  })

  test('owner can withdraw a pending invitation', async ({ adminPage, memberUser }) => {
    await adminPage.goto(peopleUrl(event.id))
    await adminPage.getByTestId('input-invite-emails').fill(memberUser.email)
    await adminPage.getByTestId('btn-send-invites').click()
    await expect(adminPage.getByTestId('pending-invite-row')).toBeVisible()

    await adminPage.getByTestId('btn-revoke-invite').click()
    await expect(adminPage.getByTestId('invitations-empty')).toBeVisible()
  })

  test('owner can promote a member to organiser', async ({ adminPage, memberPage, memberUser }) => {
    await addMember(adminPage, memberPage, event.id, memberUser.email)
    await adminPage.goto(peopleUrl(event.id))

    const memberRow = adminPage
      .getByTestId('event-member-row')
      .filter({ hasText: memberUser.email })
    await memberRow.getByRole('combobox').selectOption('admin')

    await adminPage.reload()
    await expect(
      adminPage.getByTestId('event-member-row').filter({ hasText: memberUser.email }),
    ).toHaveAttribute('data-role', 'admin')
  })

  test('owner can remove a member', async ({ adminPage, memberPage, memberUser }) => {
    await addMember(adminPage, memberPage, event.id, memberUser.email)
    await adminPage.goto(peopleUrl(event.id))
    await expect(adminPage.getByTestId('event-member-row')).toHaveCount(2)

    await adminPage
      .getByTestId('event-member-row')
      .filter({ hasText: memberUser.email })
      .getByTestId('btn-remove-member')
      .click()

    await expect(adminPage.getByTestId('event-member-row')).toHaveCount(1)
  })

  test('the owner row offers no remove button', async ({ adminPage }) => {
    await adminPage.goto(peopleUrl(event.id))
    const ownerRow = adminPage.getByTestId('event-member-row').filter({
      has: adminPage.locator('[data-role="owner"]'),
    })
    void ownerRow
    await expect(adminPage.getByTestId('btn-remove-member')).toHaveCount(0)
  })

  test('a non-member cannot open the event at all', async ({ memberPage }) => {
    await memberPage.goto(peopleUrl(event.id))
    // The event is 404 to them, so the People tab never renders.
    await expect(memberPage.getByTestId('section-event-members')).toBeHidden()
  })
})

// ── Invitation redemption ────────────────────────────────────────────────────

test.describe('Event members – invitations', () => {
  let event: EventRead

  test.beforeEach(async ({ adminPage }) => {
    event = await createEvent(adminPage, uniqueName('E2E Invite'), 'published', 'private')
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteEvent(adminPage, event.id).catch(() => {})
  })

  test('an invite link lets someone into a private event', async ({
    adminPage,
    disposablePage,
    disposableUser,
  }) => {
    // Accepting in the UI switches the accepter's selected event, so this runs
    // as a disposable identity rather than the shared memberUser.
    const invitation = await api<{ token: string }>(
      adminPage,
      'POST',
      `/events/${event.id}/invitations`,
      { email: disposableUser.email, role: 'member' },
    )

    await disposablePage.goto(`/invite/${invitation.token}`)
    await expect(disposablePage.getByTestId('invite-event-name')).toContainText(event.name)
    await disposablePage.getByTestId('btn-accept-invite').click()

    await disposablePage.waitForURL('**/app/home')
    const members = await api<{ user_id: string }[]>(
      adminPage,
      'GET',
      `/events/${event.id}/members`,
    )
    expect(members).toHaveLength(2)
  })

  test('an invite for a different address is refused', async ({ adminPage, memberPage }) => {
    const invitation = await api<{ token: string }>(
      adminPage,
      'POST',
      `/events/${event.id}/invitations`,
      { email: 'someone.else@test.example.com', role: 'member' },
    )

    await memberPage.goto(`/invite/${invitation.token}`)
    await expect(memberPage.getByTestId('invite-invalid')).toBeVisible()
    await expect(memberPage.getByTestId('btn-accept-invite')).toHaveCount(0)
  })

  test('an unknown token shows a dead-link page', async ({ memberPage }) => {
    await memberPage.goto('/invite/definitely-not-a-real-token')
    await expect(memberPage.getByTestId('invite-not-found')).toBeVisible()
  })

  test('a share link admits anyone signed in', async ({ adminPage, disposablePage }) => {
    const invitation = await api<{ token: string }>(
      adminPage,
      'POST',
      `/events/${event.id}/invitations`,
      { role: 'member' },
    )

    await disposablePage.goto(`/invite/${invitation.token}`)
    await disposablePage.getByTestId('btn-accept-invite').click()
    await disposablePage.waitForURL('**/app/home')

    const members = await api<{ user_id: string }[]>(
      adminPage,
      'GET',
      `/events/${event.id}/members`,
    )
    expect(members).toHaveLength(2)
  })
})

// ── Scoped permissions ───────────────────────────────────────────────────────

test.describe('Event members – scoped permissions (API)', () => {
  let event: EventRead

  test.beforeEach(async ({ adminPage }) => {
    event = await createEvent(adminPage, uniqueName('E2E Scoped'))
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteEvent(adminPage, event.id).catch(() => {})
  })

  test('an event admin can create tasks in their own event', async ({
    adminPage,
    memberPage,
    memberUser,
  }) => {
    await addMember(adminPage, memberPage, event.id, memberUser.email, 'admin')

    const result = await api<{ task: { id: string } }>(
      memberPage,
      'POST',
      '/tasks/with-shifts',
      taskPayload(event.id, uniqueName('E2E Scoped Task')),
    )
    expect(result.task.id).toBeTruthy()

    await api(adminPage, 'DELETE', `/tasks/${result.task.id}`)
  })

  test("an event admin cannot create tasks in someone else's event", async ({
    adminPage,
    memberPage,
    memberUser,
  }) => {
    await addMember(adminPage, memberPage, event.id, memberUser.email, 'admin')
    const other = await createEvent(adminPage, uniqueName('E2E Other Event'))
    try {
      const status = await apiStatus(
        memberPage,
        'POST',
        '/tasks/with-shifts',
        taskPayload(other.id, uniqueName('E2E Should Fail')),
      )
      expect([403, 404]).toContain(status)
    } finally {
      await deleteEvent(adminPage, other.id).catch(() => {})
    }
  })

  test('removing someone revokes their access', async ({ adminPage, memberPage, memberUser }) => {
    await addMember(adminPage, memberPage, event.id, memberUser.email, 'admin')
    const memberId = await getUserIdByEmail(adminPage, memberUser.email)
    await api(adminPage, 'DELETE', `/events/${event.id}/members/${memberId}`)

    const status = await apiStatus(
      memberPage,
      'POST',
      '/tasks/with-shifts',
      taskPayload(event.id, uniqueName('E2E After Removal')),
    )
    expect([403, 404]).toContain(status)
  })

  test('a plain member cannot manage the event', async ({ adminPage, memberPage, memberUser }) => {
    await addMember(adminPage, memberPage, event.id, memberUser.email, 'member')

    const status = await apiStatus(memberPage, 'PATCH', `/events/${event.id}`, {
      name: 'Renamed by a member',
    })
    expect(status).toBe(403)
  })
})

// ── Join requests ────────────────────────────────────────────────────────────

test.describe('Event members – join requests', () => {
  let event: EventRead

  test.beforeEach(async ({ adminPage }) => {
    // Today, because Discover lists the first 100 by start date and every
    // worker's event starts tomorrow and stays in the database.
    event = await createEvent(adminPage, uniqueName('E2E Join'), 'published', 'public', {
      start: futureDate(0),
      end: futureDate(4),
    })
  })

  test.afterEach(async ({ adminPage }) => {
    await deleteEvent(adminPage, event.id).catch(() => {})
  })

  test('a member can ask to join from Discover, and the owner lets them in', async ({
    adminPage,
    memberPage,
    memberUser,
  }) => {
    await memberPage.goto('/app/select-event?mode=switch')
    await memberPage.getByTestId('tab-discover').click()

    const card = memberPage.getByTestId('select-event-card').filter({ hasText: event.name })
    await card.getByTestId('btn-request-join').click()
    await expect(card.getByTestId('join-requested-badge')).toBeVisible()

    // The organiser decides — no platform admin involved.
    await adminPage.goto(peopleUrl(event.id))
    const request = adminPage.getByTestId('join-request-row').filter({ hasText: memberUser.email })
    await expect(request).toBeVisible()
    await request.getByTestId('btn-approve-request').click()

    await expect(adminPage.getByTestId('join-requests-empty')).toBeVisible()
    await expect(
      adminPage.getByTestId('event-member-row').filter({ hasText: memberUser.email }),
    ).toBeVisible()
  })

  test('a declined request grants no membership', async ({ adminPage, memberPage, memberUser }) => {
    await api(memberPage, 'POST', `/events/${event.id}/join-request`, {})

    await adminPage.goto(peopleUrl(event.id))
    await adminPage
      .getByTestId('join-request-row')
      .filter({ hasText: memberUser.email })
      .getByTestId('btn-decline-request')
      .click()

    await expect(adminPage.getByTestId('join-requests-empty')).toBeVisible()
    const members = await api<{ user_id: string }[]>(
      adminPage,
      'GET',
      `/events/${event.id}/members`,
    )
    expect(members).toHaveLength(1)
  })
})

// ── First sign-in ────────────────────────────────────────────────────────────

test.describe('Event members – the first screen a new account sees', () => {
  // No membership anywhere, which is what a genuine first sign-in looks like.
  test.use({ disposableUserOptions: { joinWorkerEvent: false } })

  test('an account in no event lands on Discover, not an empty list', async ({
    disposablePage,
  }) => {
    // With no selected event the router forces the picker. "My events" would
    // be an empty dead end, so Discover — where the curated list lives — is
    // the useful first screen.
    await expect(disposablePage).toHaveURL(/\/app\/select-event/)
    await expect(disposablePage.getByTestId('tab-discover')).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  test('the featured event is pinned above the rest of Discover', async ({
    adminPage,
    disposablePage,
    workerEvent,
  }) => {
    await api(adminPage, 'PATCH', `/events/${workerEvent.id}/featured`, {
      is_featured: true,
    })
    try {
      await disposablePage.goto('/app/select-event?mode=onboarding')
      await disposablePage.getByTestId('tab-discover').click()

      await expect(disposablePage.getByTestId('featured-heading')).toBeVisible()
      // Other parallel workers feature their own events, so match this
      // worker's card by name rather than assuming a single featured card.
      const featured = disposablePage
        .locator('[data-featured="true"]')
        .filter({ hasText: workerEvent.name })
      await expect(featured).toHaveCount(1)
    } finally {
      await api(adminPage, 'PATCH', `/events/${workerEvent.id}/featured`, {
        is_featured: false,
      })
    }
  })

  test('featuring is refused for a private event', async ({ adminPage }) => {
    const secret = await createEvent(
      adminPage,
      uniqueName('E2E Not Featurable'),
      'published',
      'private',
    )
    try {
      const status = await apiStatus(adminPage, 'PATCH', `/events/${secret.id}/featured`, {
        is_featured: true,
      })
      expect(status).toBe(422)
    } finally {
      await deleteEvent(adminPage, secret.id).catch(() => {})
    }
  })

  test('a member already in the event does not see it offered again', async ({
    adminPage,
    memberPage,
    workerEvent,
  }) => {
    // Featured does not mean "show it to everyone" — someone already taking
    // part has nothing to join.
    await api(adminPage, 'PATCH', `/events/${workerEvent.id}/featured`, {
      is_featured: true,
    })
    try {
      await memberPage.goto('/app/select-event?mode=switch')
      await memberPage.getByTestId('tab-discover').click()
      await expect(
        memberPage.locator('[data-featured="true"]').filter({ hasText: workerEvent.name }),
      ).toHaveCount(0)
    } finally {
      await api(adminPage, 'PATCH', `/events/${workerEvent.id}/featured`, {
        is_featured: false,
      })
    }
  })
})
