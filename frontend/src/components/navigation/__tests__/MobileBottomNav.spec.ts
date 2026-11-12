// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { type RouteRecordRaw, createMemoryHistory, createRouter } from 'vue-router'

import MobileBottomNav from '@/components/navigation/MobileBottomNav.vue'

import i18n from '@/locales/i18n'

/**
 * The phone's bottom nav: Home first of five tabs, the current tab announced
 * (also on a page below it, like a task's details), and Home gone from the
 * More sheet now that it has a tab of its own.
 */

const auth = vi.hoisted(() => ({
  selectedEvent: null as Record<string, unknown> | null,
  isManager: false,
  isAdmin: false,
  canManageEvent: (): boolean => false,
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))

vi.mock('@/stores/notification', () => ({
  useNotificationStore: () => ({ unreadCount: 3, hasUnread: true }),
}))

vi.mock('@/composables/useChangelogStatus', () => ({
  useChangelogStatus: () => ({ hasNewVersions: ref(false) }),
}))

const passthrough = { template: '<div><slot /></div>' }
const drawerStubs = {
  Drawer: { props: ['open'], template: '<div v-if="open"><slot /></div>' },
  DrawerContent: passthrough,
  DrawerHeader: passthrough,
  DrawerTitle: passthrough,
  DrawerDescription: passthrough,
}

const page = { template: '<div />' }
const routes: RouteRecordRaw[] = [
  ['home', '/app/home'],
  ['tasks', '/app/tasks'],
  ['task-detail', '/app/tasks/:taskId'],
  ['my-bookings', '/app/bookings'],
  ['notifications', '/app/notifications'],
  ['availability', '/app/availability'],
  ['select-event', '/app/select-event'],
  ['changelog', '/app/changelog'],
  ['my-vouchers', '/app/vouchers/:eventId?'],
  ['teams', '/app/teams/:eventId?'],
  ['event-map', '/app/map/:eventId?'],
  ['event-settings', '/app/event-settings/:eventId?'],
  ['reporting', '/app/reporting'],
  ['my-events', '/app/events'],
  ['admin-users', '/app/admin/users'],
].map(([name, path]) => ({ name, path, component: page }))

async function mountAt(name: string, params: Record<string, string> = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push({ name, params })
  await router.isReady()
  return mount(MobileBottomNav, { global: { plugins: [i18n, router], stubs: drawerStubs } })
}

const TABS = ['home', 'tasks', 'bookings', 'inbox', 'more'] as const

beforeEach(() => {
  i18n.global.locale.value = 'en'
  auth.selectedEvent = null
  auth.canManageEvent = () => false
})

describe('MobileBottomNav', () => {
  it('has five tabs, Home first', async () => {
    const w = await mountAt('home')
    const tabs = w.find('[data-testid="mobile-bottom-nav"]').findAll('a, button')
    expect(tabs.map((t) => t.attributes('data-testid'))).toEqual(
      TABS.map((tab) => `mobile-nav-${tab}`),
    )
    expect(tabs[0].text()).toBe('Home')
  })

  it('announces Home as the current page on the dashboard', async () => {
    const w = await mountAt('home')
    for (const tab of TABS) {
      const el = w.find(`[data-testid="mobile-nav-${tab}"]`)
      expect(el.attributes('aria-current')).toBe(tab === 'home' ? 'page' : undefined)
    }
    expect(w.find('[data-testid="mobile-nav-home"]').classes()).toContain('text-primary')
  })

  it('announces Tasks on a task’s detail page, not only on the board', async () => {
    const w = await mountAt('task-detail', { taskId: 't1' })
    expect(w.find('[data-testid="mobile-nav-tasks"]').attributes('aria-current')).toBe('page')
    expect(w.find('[data-testid="mobile-nav-home"]').attributes('aria-current')).toBeUndefined()
  })

  it('lights More for a page from the sheet, without claiming a tab', async () => {
    const w = await mountAt('availability')
    const more = w.find('[data-testid="mobile-nav-more"]')
    expect(more.classes()).toContain('text-primary')
    expect(more.attributes('aria-current')).toBeUndefined()
    expect(w.find('[data-testid="mobile-bottom-nav"] [aria-current]').exists()).toBe(false)
  })

  it('keeps the unread count on the inbox tab', async () => {
    const w = await mountAt('home')
    expect(w.find('[data-testid="mobile-nav-inbox"]').text()).toContain('3')
  })

  it('no longer lists Home in the More sheet', async () => {
    const w = await mountAt('tasks')
    await w.find('[data-testid="mobile-nav-more"]').trigger('click')
    expect(w.find('[data-testid="mobile-nav-more"]').attributes('aria-expanded')).toBe('true')
    expect(w.find('[data-testid="mobile-more-home"]').exists()).toBe(false)
    expect(w.find('[data-testid="mobile-more-availability"]').exists()).toBe(true)
    expect(w.find('[data-testid="mobile-more-select-event"]').exists()).toBe(true)
  })

  it('lists the event’s own pages in the sheet when it has them', async () => {
    auth.selectedEvent = { id: 'e1', voucher_task_count: 1, venue_plan_count: 1, team_count: 2 }
    const w = await mountAt('home')
    await w.find('[data-testid="mobile-nav-more"]').trigger('click')
    expect(w.find('[data-testid="mobile-more-my-vouchers"]').exists()).toBe(true)
    expect(w.find('[data-testid="mobile-more-teams"]').exists()).toBe(true)
    expect(w.find('[data-testid="mobile-more-event-map"]').exists()).toBe(true)
  })

  it('offers the event’s settings to whoever runs it, with the requests waiting', async () => {
    auth.selectedEvent = { id: 'e1', pending_request_count: 2, pending_team_request_count: 1 }
    auth.canManageEvent = () => true
    const w = await mountAt('home')
    const more = w.find('[data-testid="mobile-nav-more"]')
    expect(more.attributes('aria-label')).toBe('More, 3 requests to decide')
    expect(w.find('[data-testid="mobile-nav-more-dot"]').exists()).toBe(true)
    await more.trigger('click')
    expect(w.find('[data-testid="mobile-more-event-settings"]').exists()).toBe(true)
    expect(w.find('[data-testid="mobile-more-badge-event-settings"]').text()).toContain('2')
  })

  it('keeps the event’s settings from a plain member', async () => {
    // The server counts requests for admins only; a member gets nothing anyway.
    auth.selectedEvent = { id: 'e1', pending_request_count: 2 }
    const w = await mountAt('home')
    expect(w.find('[data-testid="mobile-nav-more-dot"]').exists()).toBe(false)
    await w.find('[data-testid="mobile-nav-more"]').trigger('click')
    expect(w.find('[data-testid="mobile-more-event-settings"]').exists()).toBe(false)
  })

  // The sheet puts focus on its first link as it opens. Styled with plain
  // `focus:`, that link looked like the current page every time the sheet
  // was opened by touch; `focus-visible:` keeps the highlight for keyboards.
  it('highlights a sheet link for keyboard focus only', async () => {
    const w = await mountAt('home')
    await w.find('[data-testid="mobile-nav-more"]').trigger('click')
    const link = w.find('[data-testid="mobile-more-availability"]')
    expect(link.classes()).toContain('focus-visible:bg-accent')
    expect(link.classes().filter((c) => c.startsWith('focus:'))).toEqual([])
  })
})
