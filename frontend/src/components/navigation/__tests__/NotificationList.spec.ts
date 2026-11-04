// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { NotificationItem } from '@/stores/notification'

import NotificationList from '@/components/navigation/NotificationList.vue'

import i18n from '@/locales/i18n'

/**
 * The bell's dropdown. Each notice is a link to what it is about: an
 * invitation carries its token and opens the invitation (its event's page is
 * a 404 to someone not in a private event yet); the other kinds open their
 * task, team, event or bookings. Clicking one marks it read and closes the
 * dropdown. Notices sit under "Today", "Yesterday" and "Earlier".
 */

const store = vi.hoisted(() => ({
  notifications: [] as NotificationItem[],
  hasMore: false,
  loading: false,
  markAsRead: vi.fn(),
  dismissNotification: vi.fn(),
  loadMoreNotifications: vi.fn(),
}))
vi.mock('@/stores/notification', () => ({ useNotificationStore: () => store }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))

const page = { template: '<div />' }

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: page },
      { path: '/invite/:token', name: 'invite-accept', component: page },
      { path: '/app/tasks/:eventId', name: 'task-detail', component: page },
      { path: '/app/teams/:eventId', name: 'teams', component: page },
      { path: '/app/events/:eventId', name: 'event-settings', component: page },
      { path: '/app/bookings', name: 'my-bookings', component: page },
    ],
  })
}

const naive = (d: Date) => d.toISOString().slice(0, -1)

function notice(
  data: Record<string, unknown> | null,
  { isRead = true, id = 'n1', createdAt = new Date() } = {},
): NotificationItem {
  return {
    id,
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
    created_at: naive(createdAt),
  }
}

async function mountList(items: NotificationItem[]) {
  store.notifications = items
  const router = makeRouter()
  await router.push('/')
  const w = mount(NotificationList, {
    global: {
      plugins: [i18n, router],
      stubs: { HintTooltip: { template: '<div><slot /></div>' } },
    },
  })
  return { w, router }
}

async function click(data: Record<string, unknown> | null, isRead = true) {
  const { w, router } = await mountList([notice(data, { isRead })])
  const row = w.find('[data-testid="notification-row"] > :first-child')
  await row.trigger('click')
  await flushPromises()
  return { w, router, row }
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
  store.markAsRead.mockReset()
  store.dismissNotification.mockReset()
})

describe('NotificationList clicks', () => {
  it('opens the invitation when the notice carries a token, before its event', async () => {
    const { w, router } = await click({ event_id: 'e1', token: 'tok-123' })
    expect(router.currentRoute.value.fullPath).toBe('/invite/tok-123')
    expect(w.emitted('navigate')).toHaveLength(1)
  })

  it('opens the task for a task notice', async () => {
    const { router } = await click({ task_id: 't1', event_id: 'e1' })
    expect(router.currentRoute.value.fullPath).toBe('/app/tasks/t1')
  })

  it('opens the team on the Teams page for a team notice', async () => {
    const { router } = await click({ team_id: 'tm1', event_id: 'e1' })
    expect(router.currentRoute.value.fullPath).toBe('/app/teams/e1?team=tm1')
  })

  it('opens the event for an event notice', async () => {
    const { router } = await click({ event_id: 'e1' })
    expect(router.currentRoute.value.fullPath).toBe('/app/events/e1')
  })

  it('opens my bookings for a booking notice', async () => {
    const { router } = await click({ booking_id: 'b1' })
    expect(router.currentRoute.value.fullPath).toBe('/app/bookings')
  })

  it('marks an unread notice read as it opens', async () => {
    await click({ task_id: 't1' }, false)
    expect(store.markAsRead).toHaveBeenCalledWith('n1')
  })

  it('stays put without anything to open, and marks an unread notice read', async () => {
    const { w, router, row } = await click(null, false)
    expect(row.element.tagName).toBe('DIV')
    expect(router.currentRoute.value.fullPath).toBe('/')
    expect(w.emitted('navigate')).toBeUndefined()
    expect(store.markAsRead).toHaveBeenCalledWith('n1')
  })
})

describe('NotificationList grouping and actions', () => {
  it('puts notices under the day they came', async () => {
    const now = new Date()
    const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1, 12)
    const lastWeek = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6, 12)
    const { w } = await mountList([
      notice(null, { id: 'a', createdAt: now }),
      notice(null, { id: 'b', createdAt: yesterday }),
      notice(null, { id: 'c', createdAt: lastWeek }),
    ])
    expect(w.findAll('h4').map((h) => h.text())).toEqual(['Today', 'Yesterday', 'Earlier'])
  })

  it('marks read and deletes from the row’s own buttons', async () => {
    const { w } = await mountList([notice({ task_id: 't1' }, { isRead: false })])
    await w.find('[data-testid="btn-notification-read"]').trigger('click')
    expect(store.markAsRead).toHaveBeenCalledWith('n1')
    await w.find('[data-testid="btn-notification-dismiss"]').trigger('click')
    expect(store.dismissNotification).toHaveBeenCalledWith('n1')
    // Neither opens the notice.
    expect(w.emitted('navigate')).toBeUndefined()
  })

  it('says when there is nothing yet', async () => {
    const { w } = await mountList([])
    expect(w.text()).toContain('No notifications yet')
  })
})
