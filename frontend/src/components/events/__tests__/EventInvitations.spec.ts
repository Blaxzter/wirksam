// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { describe, expect, it, vi } from 'vitest'

import EventInvitations from '@/components/events/EventInvitations.vue'

import type { EventInvitationRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The server keeps listing an invitation past its date until someone withdraws
 * it, so the screen has to say it no longer works. Its timestamps are naive UTC.
 */

vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ post: vi.fn(), delete: vi.fn() }),
}))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))
vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))

const PAST = '2020-01-01T12:00:00'
const FUTURE = '2999-01-01T12:00:00'

function invitation(overrides: Partial<EventInvitationRead>): EventInvitationRead {
  return {
    id: 'i1',
    event_id: 'e1',
    role: 'member',
    token: 'tok',
    use_count: 0,
    tasks: [],
    ...overrides,
  } as EventInvitationRead
}

function mountList(invitations: EventInvitationRead[]) {
  return mount(EventInvitations, {
    props: { eventId: 'e1', invitations },
    global: { plugins: [i18n] },
  })
}

describe('EventInvitations', () => {
  it('marks an expired email invitation and keeps a way to withdraw it', () => {
    const w = mountList([invitation({ email: 'a@example.org', expires_at: PAST })])
    expect(w.get('[data-testid="invitation-expired"]').text()).toBe('Expired')
    expect(w.get('[data-testid="invitation-expired-hint"]').text()).toContain('no longer works')
    expect(w.find('[data-testid="btn-revoke-invite"]').exists()).toBe(true)
  })

  it('marks an expired share link and stops offering to copy it', () => {
    const w = mountList([invitation({ expires_at: PAST })])
    expect(w.find('[data-testid="invitation-expired"]').exists()).toBe(true)
    expect(w.get('[data-testid="share-link-row"]').find('[aria-label="Copy link"]').exists()).toBe(
      false,
    )
    expect(
      w.get('[data-testid="share-link-row"]').find('[aria-label="Withdraw invitation"]').exists(),
    ).toBe(true)
  })

  it('leaves invitations alone that are still valid or never expire', () => {
    const w = mountList([
      invitation({ id: 'i1', email: 'a@example.org', expires_at: FUTURE }),
      invitation({ id: 'i2', email: 'b@example.org', expires_at: null }),
      invitation({ id: 'i3', expires_at: FUTURE }),
    ])
    expect(w.find('[data-testid="invitation-expired"]').exists()).toBe(false)
    expect(w.get('[data-testid="share-link-row"]').find('[aria-label="Copy link"]').exists()).toBe(
      true,
    )
  })
})
