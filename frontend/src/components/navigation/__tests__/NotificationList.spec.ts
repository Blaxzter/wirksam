// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { NotificationItem } from '@/stores/notification'

import NotificationList from '@/components/navigation/NotificationList.vue'

import i18n from '@/locales/i18n'

/**
 * Where a notice opens when it is clicked in the bell's list. An invitation
 * carries its token and opens the invitation: its event's page is a 404 to
 * someone not in a private event yet, and the token was never used before.
 * The other branches open what they did before.
 */

const push = vi.fn()
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRouter: () => ({ push }),
}))

const store = vi.hoisted(() => ({
  notifications: [] as NotificationItem[],
  hasMore: false,
  loading: false,
  markAsRead: vi.fn(),
  dismissNotification: vi.fn(),
  loadMoreNotifications: vi.fn(),
}))
vi.mock('@/stores/notification', () => ({ useNotificationStore: () => store }))

function notice(data: Record<string, unknown> | null, isRead = true): NotificationItem {
  return {
    id: 'n1',
    recipient_id: 'u1',
    notification_type_code: 'event.invitation',
    classification: 'announcement',
    title: 'Invitation',
    body: 'Anna invited you.',
    data,
    is_read: isRead,
    read_at: null,
    channels_sent: [],
    channels_failed: [],
    created_at: new Date().toISOString(),
  }
}

async function click(data: Record<string, unknown> | null, isRead = true) {
  store.notifications = [notice(data, isRead)]
  const w = mount(NotificationList, {
    global: { plugins: [i18n], stubs: { HintTooltip: { template: '<div><slot /></div>' } } },
  })
  await w.find('.event').trigger('click')
  return w
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
  push.mockReset()
  store.markAsRead.mockReset()
})

describe('NotificationList clicks', () => {
  it('opens the invitation when the notice carries a token, before its event', async () => {
    const w = await click({ event_id: 'e1', token: 'tok-123' })
    expect(push).toHaveBeenCalledWith({ name: 'invite-accept', params: { token: 'tok-123' } })
    expect(w.emitted('navigate')).toHaveLength(1)
  })

  it('opens the task for a task notice', async () => {
    await click({ task_id: 't1', event_id: 'e1' })
    expect(push).toHaveBeenCalledWith({ name: 'task-detail', params: { eventId: 't1' } })
  })

  it('opens the team on the Teams page for a team notice', async () => {
    await click({ team_id: 'tm1', event_id: 'e1' })
    expect(push).toHaveBeenCalledWith({
      name: 'teams',
      params: { eventId: 'e1' },
      query: { team: 'tm1' },
    })
  })

  it('opens the event for an event notice', async () => {
    await click({ event_id: 'e1' })
    expect(push).toHaveBeenCalledWith({ name: 'event-settings', params: { eventId: 'e1' } })
  })

  it('opens my bookings for a booking notice', async () => {
    await click({ booking_id: 'b1' })
    expect(push).toHaveBeenCalledWith({ name: 'my-bookings' })
  })

  it('stays put without anything to open, and marks an unread notice read', async () => {
    const w = await click(null, false)
    expect(push).not.toHaveBeenCalled()
    expect(w.emitted('navigate')).toBeUndefined()
    expect(store.markAsRead).toHaveBeenCalledWith('n1')
  })
})
