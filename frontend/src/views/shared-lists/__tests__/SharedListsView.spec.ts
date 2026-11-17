// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { overview } from '@/components/shared-lists/__tests__/fixtures'

import i18n from '@/locales/i18n'
import SharedListsView from '@/views/shared-lists/SharedListsView.vue'

/**
 * The shared-lists page around its tabs: which event it is about, what it
 * says when the server refuses, the tab kept in the address, the way to a
 * list's own page, and who gets "Share a list".
 */

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
const auth = vi.hoisted(() => ({
  profile: { id: 'u1' } as { id: string } | null,
  selectedEventId: 'e1' as string | null,
  selectedEvent: { id: 'e1', name: 'Adventsbasar' } as { id: string; name: string } | null,
}))
vi.mock('@/composables/useAuthenticatedClient', () => ({ useAuthenticatedClient: () => api }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))

function axiosError(status: number, code: string) {
  return { isAxiosError: true, response: { status, data: { status, code } } }
}

async function mountView(path = '/app/shared-lists') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: { template: '<div />' } },
      { path: '/app/select-event', name: 'select-event', component: { template: '<div />' } },
      { path: '/app/shared-lists/:eventId?', name: 'shared-lists', component: SharedListsView },
      {
        path: '/app/shared-lists/:eventId/new',
        name: 'shared-list-create',
        component: { template: '<div />' },
      },
      {
        path: '/app/shared-lists/:eventId/:listId',
        name: 'shared-list-detail',
        component: { template: '<div />' },
      },
    ],
  })
  await router.push(path)
  const w = mount(SharedListsView, {
    attachTo: document.body,
    global: {
      plugins: [i18n, router],
      stubs: {
        SharedListsLinksTab: {
          emits: ['open'],
          template: `<button data-testid="links-tab" @click="$emit('open', 'l7')" />`,
        },
        SharedListsTasksTab: { template: '<div data-testid="tasks-tab" />' },
        SharedListsPreviewTab: { template: '<div data-testid="preview-tab" />' },
      },
    },
  })
  await flushPromises()
  return { w, router }
}

const byTestId = (w: Awaited<ReturnType<typeof mountView>>['w'], id: string) =>
  w.find(`[data-testid="${id}"]`)

beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  i18n.global.locale.value = 'en'
  auth.profile = { id: 'u1' }
  auth.selectedEventId = 'e1'
  auth.selectedEvent = { id: 'e1', name: 'Adventsbasar' }
  api.get.mockResolvedValue({ data: overview() })
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('SharedListsView', () => {
  it('shows the selected event’s lists without an id in the address', async () => {
    const { w } = await mountView()

    expect(api.get).toHaveBeenCalledWith({ url: '/events/e1/shared-lists/overview' })
    expect(byTestId(w, 'page-heading').text()).toBe('Shared lists')
    expect(w.text()).toContain('Adventsbasar')
    expect(byTestId(w, 'links-tab').exists()).toBe(true)
    expect(byTestId(w, 'btn-share-list').attributes('disabled')).toBeUndefined()
  })

  it('takes the event from the address when there is one', async () => {
    const { w } = await mountView('/app/shared-lists/e2')
    expect(api.get).toHaveBeenCalledWith({ url: '/events/e2/shared-lists/overview' })
    // Another event than the selected one: its name is not at hand.
    expect(w.text()).not.toContain('Adventsbasar')
  })

  it('asks to choose an event when none is selected', async () => {
    auth.selectedEventId = null
    auth.selectedEvent = null
    const { w } = await mountView()
    expect(byTestId(w, 'shared-lists-no-event').exists()).toBe(true)
    expect(api.get).not.toHaveBeenCalled()
  })

  it('waits for the profile before saying no event is selected', async () => {
    auth.profile = null
    auth.selectedEventId = null
    const { w } = await mountView()
    expect(byTestId(w, 'shared-lists-no-event').exists()).toBe(false)
  })

  it('explains a refusal and offers the way home instead of a retry', async () => {
    api.get.mockRejectedValue(axiosError(403, 'shared_list.forbidden'))
    const { w } = await mountView()

    const error = byTestId(w, 'shared-lists-error')
    expect(error.text()).toContain('You are not in charge of any task in this event.')
    expect(byTestId(w, 'shared-lists-retry').exists()).toBe(false)
    expect(byTestId(w, 'btn-share-list').exists()).toBe(false)
  })

  it('offers to try again after a failure that may pass', async () => {
    api.get.mockRejectedValueOnce(axiosError(503, 'server.unavailable'))
    const { w } = await mountView()

    await byTestId(w, 'shared-lists-retry').trigger('click')
    await flushPromises()

    expect(byTestId(w, 'shared-lists-error').exists()).toBe(false)
    expect(byTestId(w, 'links-tab').exists()).toBe(true)
  })

  it('opens the tab the address names', async () => {
    const { w } = await mountView('/app/shared-lists/e1?tab=tasks')
    expect(byTestId(w, 'tasks-tab').exists()).toBe(true)
  })

  it('opens a list on its own page', async () => {
    const { w, router } = await mountView('/app/shared-lists/e1')
    await byTestId(w, 'links-tab').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/app/shared-lists/e1/l7')
  })

  it('takes an old link to a list’s details to its page, with its sign-ups’ view', async () => {
    const { router } = await mountView('/app/shared-lists/e1?tab=tasks&list=l1&signups_page=2')
    expect(router.currentRoute.value.name).toBe('shared-list-detail')
    expect(router.currentRoute.value.fullPath).toBe('/app/shared-lists/e1/l1?signups_page=2')
  })

  it('counts the open lists on the Links tab whichever tab is shown', async () => {
    const { w } = await mountView('/app/shared-lists/e1?tab=preview')
    expect(byTestId(w, 'links-tab').exists()).toBe(false)
    expect(byTestId(w, 'tab-links-count').text()).toBe('2')
  })

  it('counts afresh on every visit, after lists were made elsewhere', async () => {
    const first = await mountView('/app/shared-lists/e1?tab=tasks')
    first.w.unmount()
    api.get.mockResolvedValue({
      data: overview({ summary: { ...overview().summary, active_lists: 3 } }),
    })
    const { w } = await mountView('/app/shared-lists/e1?tab=preview')
    expect(byTestId(w, 'tab-links-count').text()).toBe('3')
  })

  it('keeps the tab in the address', async () => {
    const { w, router } = await mountView('/app/shared-lists/e1?q=Kuchen')

    await byTestId(w, 'tab-preview').trigger('mousedown', { button: 0 })
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ q: 'Kuchen', tab: 'preview' })
  })

  it('starts a new list for the event', async () => {
    const { w, router } = await mountView()
    await byTestId(w, 'btn-share-list').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/app/shared-lists/e1/new')
  })

  it('cannot start a list without a task to share', async () => {
    api.get.mockResolvedValue({ data: overview({ is_admin: false, can_create: false }) })
    const { w } = await mountView()
    expect(byTestId(w, 'btn-share-list').attributes('disabled')).toBeDefined()
  })

  it('tells a person in charge when sharing is off for them', async () => {
    api.get.mockResolvedValue({
      data: overview({ is_admin: false, can_create: false, managers_share_lists: false }),
    })
    const { w } = await mountView()
    expect(byTestId(w, 'shared-lists-managers-off').exists()).toBe(true)
    expect(byTestId(w, 'btn-share-list').exists()).toBe(false)
  })
})
