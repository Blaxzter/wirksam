// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { EventInvitationPreview } from '@/client/types.gen'
import i18n from '@/locales/i18n'
import InviteAcceptView from '@/views/events/InviteAcceptView.vue'

/**
 * What someone sees on an invitation that asks them to be in charge of
 * tasks. The server also lists those tasks to a member whose invitation is
 * spent, expired or withdrawn; the page must not then tell them they are
 * asked to be in charge, and an expired or withdrawn one says why it is gone.
 */

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({ useAuthenticatedClient: () => api }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    isAuthenticated: true,
    loadProfile: vi.fn(),
    setSelectedEvent: vi.fn(() => Promise.resolve()),
  }),
}))
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ params: { token: 'tok-1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))

const bar = {
  task_id: 't-bar',
  name: 'Bar',
  start_date: '2026-11-20',
  end_date: '2026-11-20',
}

function preview(overrides: Partial<EventInvitationPreview> = {}): EventInvitationPreview {
  return {
    event_id: 'e1',
    event_name: 'Summer fair',
    event_description: null,
    start_date: '2026-11-20',
    end_date: '2026-11-22',
    role: 'member',
    invited_by_name: 'Anna',
    is_valid: true,
    invalid_reason: null,
    already_member: false,
    tasks: [bar],
    ...overrides,
  }
}

async function mountWith(p: EventInvitationPreview) {
  api.get.mockResolvedValue({ data: p })
  const w = mount(InviteAcceptView, {
    global: { plugins: [i18n] },
  })
  await flushPromises()
  return w
}

const has = (w: Awaited<ReturnType<typeof mountWith>>, testid: string) =>
  w.find(`[data-testid="${testid}"]`).exists()

beforeEach(() => {
  i18n.global.locale.value = 'en'
  api.get.mockReset()
})

describe('InviteAcceptView: the tasks asked of the invitee', () => {
  it('lists them on a valid invitation, with the accept button', async () => {
    const w = await mountWith(preview())
    expect(w.find('[data-testid="invite-tasks"]').text()).toContain('Bar')
    expect(has(w, 'btn-accept-invite')).toBe(true)
  })

  it('lets a member who joined another way accept a valid one', async () => {
    const w = await mountWith(preview({ already_member: true }))
    expect(has(w, 'invite-tasks')).toBe(true)
    expect(w.find('[data-testid="btn-accept-invite"]').text()).toBe('Accept')
  })

  it.each([
    ['expired', 'This invitation has expired.'],
    ['revoked', 'This invitation was withdrawn.'],
  ])('tells a member why an %s one is gone, without the tasks', async (reason, message) => {
    const w = await mountWith(
      preview({ already_member: true, is_valid: false, invalid_reason: reason }),
    )
    expect(has(w, 'invite-tasks')).toBe(false)
    expect(has(w, 'btn-accept-invite')).toBe(false)
    expect(w.find('[data-testid="invite-invalid"]').text()).toContain(message)
    expect(has(w, 'invite-already-member')).toBe(true)
    expect(has(w, 'btn-open-event')).toBe(true)
  })

  it('shows a member who already accepted the event, not the tasks or an error', async () => {
    const w = await mountWith(
      preview({ already_member: true, is_valid: false, invalid_reason: 'already_used' }),
    )
    expect(has(w, 'invite-tasks')).toBe(false)
    expect(has(w, 'invite-invalid')).toBe(false)
    expect(has(w, 'btn-open-event')).toBe(true)
  })
})

describe("InviteAcceptView: the event's look", () => {
  it("wears the event's colours while it is open", async () => {
    const w = await mountWith(
      preview({
        event_primary_color: 'violet',
        event_secondary_color: 'yellow',
        event_base_color: 'rose',
      }),
    )
    expect(document.documentElement.dataset.eventPrimary).toBe('violet')
    expect(document.documentElement.dataset.eventSecondary).toBe('yellow')
    expect(document.documentElement.dataset.eventBase).toBe('rose')
    w.unmount()
    expect(document.documentElement.dataset.eventPrimary).toBeUndefined()
    expect(document.documentElement.dataset.eventSecondary).toBeUndefined()
    expect(document.documentElement.dataset.eventBase).toBeUndefined()
  })

  it("shows the event's logo in place of the check mark", async () => {
    const w = await mountWith(preview({ event_logo_etag: 'v1' }))
    expect(w.get('[data-testid="event-logo"] img').attributes('src')).toContain(
      '/events/e1/logo?v=v1',
    )
  })

  it('keeps the cross on an invitation that cannot be used, logo or not', async () => {
    const w = await mountWith(
      preview({ event_logo_etag: 'v1', is_valid: false, invalid_reason: 'expired' }),
    )
    expect(w.find('[data-testid="event-logo"]').exists()).toBe(false)
  })

  it('formats the description', async () => {
    const w = await mountWith(preview({ event_description: 'Bring **water**' }))
    expect(w.find('.markdown-body strong').text()).toBe('water')
  })
})
