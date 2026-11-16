// @vitest-environment jsdom
import { shallowMount } from '@vue/test-utils'
import { ref } from 'vue'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import AppSidebar from '@/components/navigation/AppSidebar.vue'
import NavMain, { type NavItem } from '@/components/navigation/NavMain.vue'

import i18n from '@/locales/i18n'

/**
 * The shared-lists entry: for whoever runs the selected event or is in charge
 * of one of its tasks, never for a plain member, in a demo event or on a
 * deployment that switched the feature off. It sits in the event's own group,
 * not in the management one, which people only in charge never see.
 */

const auth = vi.hoisted(() => ({
  selectedEvent: null as Record<string, unknown> | null,
  profile: null,
  isManager: false,
  isAdmin: false,
  canManageEvent: () => false,
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))

vi.mock('@/stores/sidebar', () => ({
  useSidebarStore: () => ({ tasks: [], bookings: [], fetch: () => {} }),
}))

vi.mock('@/stores/notification', () => ({
  useNotificationStore: () => ({ unreadCount: 0, hasUnread: false }),
}))

vi.mock('@/composables/useChangelogStatus', () => ({
  useChangelogStatus: () => ({ hasNewVersions: ref(false) }),
}))

// The real one injects the provider's context, which a shallow mount has none of.
vi.mock('@/components/ui/sidebar', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/components/ui/sidebar')>()),
  useSidebar: () => ({ isMobile: ref(false), setOpenMobile: () => {}, state: ref('expanded') }),
}))

const PLAIN_MEMBER = {
  id: 'e1',
  is_sandbox: false,
  can_manage: false,
  managed_task_count: 0,
}

async function mountSidebar() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ name: 'home', path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()
  // The groups sit in the stubbed sidebar's slots, so those still render.
  return shallowMount(AppSidebar, {
    global: { plugins: [i18n, router], renderStubDefaultSlot: true },
  })
}

async function groups() {
  const w = await mountSidebar()
  return w.findAllComponents(NavMain).map((nav) => nav.props('items') as NavItem[])
}

async function eventItems(): Promise<string[]> {
  const [platform] = await groups()
  return platform.map((item) => item.routeName ?? '')
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
  auth.selectedEvent = { ...PLAIN_MEMBER }
  auth.isManager = false
})

afterEach(() => {
  delete globalThis.__APP_CONFIG__
})

describe('AppSidebar: shared lists', () => {
  it('is offered to whoever runs the event', async () => {
    auth.selectedEvent = { ...PLAIN_MEMBER, can_manage: true }
    auth.isManager = true
    const [platform, ...management] = await groups()
    const entry = platform.find((item) => item.routeName === 'shared-lists')
    expect(entry).toMatchObject({ titleKey: 'navigation.sidebar.items.sharedLists.label' })
    const elsewhere = management.flat().map((item) => item.routeName)
    expect(elsewhere).not.toContain('shared-lists')
  })

  it('is offered to someone only in charge of one of its tasks', async () => {
    auth.selectedEvent = { ...PLAIN_MEMBER, managed_task_count: 1 }
    expect(await eventItems()).toContain('shared-lists')
  })

  it('sits right after the teams', async () => {
    auth.selectedEvent = { ...PLAIN_MEMBER, can_manage: true, team_count: 1 }
    const items = await eventItems()
    expect(items.indexOf('shared-lists')).toBe(items.indexOf('teams') + 1)
  })

  it('is not offered to a plain member, or without an event', async () => {
    expect(await eventItems()).not.toContain('shared-lists')
    auth.selectedEvent = null
    expect(await eventItems()).not.toContain('shared-lists')
  })

  it('is not offered in a demo event', async () => {
    auth.selectedEvent = { ...PLAIN_MEMBER, can_manage: true, is_sandbox: true }
    expect(await eventItems()).not.toContain('shared-lists')
  })

  it('is not offered while the deployment has switched it off', async () => {
    globalThis.__APP_CONFIG__ = { SHARED_LISTS_ENABLED: 'false' }
    auth.selectedEvent = { ...PLAIN_MEMBER, can_manage: true }
    expect(await eventItems()).not.toContain('shared-lists')
  })
})
