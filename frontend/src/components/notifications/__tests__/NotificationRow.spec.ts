// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { NotificationItem } from '@/stores/notification'

import NotificationRow from '@/components/notifications/NotificationRow.vue'

import i18n from '@/locales/i18n'

/**
 * One notice as the Inbox design draws it: an icon for its type instead of
 * an emoji; unread with a green tile, a green edge, a bold title, a dot and
 * "Open task ›"; read with a grey tile and none of that.
 */

const auth = vi.hoisted(() => ({ profile: { time_format: 'locale' } as { time_format: string } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))

const page = { template: '<div />' }
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: page },
    { path: '/app/tasks/:eventId', name: 'task-detail', component: page },
    { path: '/invite/:token', name: 'invite-accept', component: page },
  ],
})

const NOW = new Date(2026, 10, 3, 14, 0)
const naive = (d: Date) => d.toISOString().slice(0, -1)

function notice(over: Partial<NotificationItem> = {}): NotificationItem {
  return {
    id: 'n1',
    recipient_id: 'u1',
    notification_type_code: 'task.manager_added',
    classification: 'announcement',
    title: 'You’re now in charge of Café counter · Summer fair',
    body: 'Anna put you in charge.',
    data: { task_id: 't1' },
    is_read: false,
    read_at: null,
    channels_sent: [],
    channels_failed: [],
    created_at: naive(new Date(2026, 10, 3, 13, 55)),
    ...over,
  }
}

function mountRow(n: NotificationItem, dense = false) {
  return mount(NotificationRow, {
    props: { notification: n, now: NOW, dense },
    global: {
      plugins: [i18n, router],
      stubs: { HintTooltip: { template: '<div><slot /></div>' } },
    },
  })
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
  auth.profile.time_format = 'locale'
})

describe('NotificationRow', () => {
  it('draws an unread notice as the design does, with where it opens', () => {
    const w = mountRow(notice())
    const card = w.find('a')
    expect(card.attributes('href')).toBe('/app/tasks/t1')
    expect(card.classes()).toContain('border-primary/30')
    expect(w.find('.lucide-user-check').exists()).toBe(true)
    expect(w.find('[data-testid="notification-unread-dot"]').exists()).toBe(true)
    expect(w.find('[data-testid="notification-open"]').text()).toBe('Open task')
    expect(w.find('[data-testid="notification-time"]').text()).toBe('5 min ago')
    expect(w.text()).toContain('Unread')
  })

  it('lets a read notice recede: grey tile, no dot, no "Open"', () => {
    const w = mountRow(notice({ is_read: true }))
    expect(w.find('a').classes()).not.toContain('border-primary/30')
    expect(w.find('[data-testid="notification-unread-dot"]').exists()).toBe(false)
    expect(w.find('[data-testid="notification-open"]').exists()).toBe(false)
    expect(w.find('[data-testid="btn-notification-read"]').exists()).toBe(false)
    expect(w.find('[data-testid="btn-notification-dismiss"]').exists()).toBe(true)
  })

  it('names what an invitation opens, in German too', () => {
    i18n.global.locale.value = 'de'
    const w = mountRow(
      notice({
        notification_type_code: 'event.invitation',
        data: { token: 'tok', event_id: 'e1' },
      }),
    )
    expect(w.find('a').attributes('href')).toBe('/invite/tok')
    expect(w.find('.lucide-mail').exists()).toBe(true)
    expect(w.find('[data-testid="notification-open"]').text()).toBe('Einladung öffnen')
    expect(w.find('[data-testid="notification-time"]').text()).toBe('vor 5 Min.')
  })

  it('falls back to a bell for a type it does not know, and is no link without a target', () => {
    const w = mountRow(notice({ notification_type_code: 'something.new', data: null }))
    expect(w.find('a').exists()).toBe(false)
    expect(w.find('.lucide-bell').exists()).toBe(true)
  })

  it('tells the parent about a click, mark-read and delete', async () => {
    const w = mountRow(notice())
    await w.find('a').trigger('click')
    await w.find('[data-testid="btn-notification-read"]').trigger('click')
    await w.find('[data-testid="btn-notification-dismiss"]').trigger('click')
    expect(w.emitted('open')).toHaveLength(1)
    expect(w.emitted('read')).toHaveLength(1)
    expect(w.emitted('dismiss')).toHaveLength(1)
  })

  it("follows the reader's 12 or 24 hour clock for older notices", () => {
    const yesterday = notice({ created_at: naive(new Date(2026, 10, 2, 18, 40)) })
    auth.profile.time_format = 'h12'
    expect(mountRow(yesterday).find('[data-testid="notification-time"]').text()).toMatch(
      /^Yesterday, 06:40\sPM$/,
    )
    auth.profile.time_format = 'h24'
    expect(mountRow(yesterday).find('[data-testid="notification-time"]').text()).toBe(
      'Yesterday, 18:40',
    )
  })

  it('keeps the dropdown’s card smaller and its text to two lines', () => {
    const w = mountRow(notice(), true)
    expect(w.find('a').classes()).toContain('p-3')
    expect(w.find('.line-clamp-2').text()).toBe('Anna put you in charge.')
  })
})
