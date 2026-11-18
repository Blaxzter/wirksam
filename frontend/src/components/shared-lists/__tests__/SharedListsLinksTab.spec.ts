// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { useSharedListsStore } from '@/stores/sharedLists'

import SharedListsLinksTab from '@/components/shared-lists/SharedListsLinksTab.vue'

import type { SharedListListResponse, SharedListRow } from '@/client/types.gen'
import i18n from '@/locales/i18n'

import { listRow, overview, stubMatchMedia } from './fixtures'

/**
 * The links tab: chips with counts from the server, the lists of the page,
 * the ticked ones paused or ended together (ending asks, in the singular or
 * the plural), the emergency stop with its lock, and what an empty view says.
 */

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
const toast = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), info: vi.fn() }))
const toastApiError = vi.hoisted(() => vi.fn())
vi.mock('@/composables/useAuthenticatedClient', () => ({ useAuthenticatedClient: () => api }))
vi.mock('vue-sonner', () => ({ toast }))
vi.mock('@/lib/api-errors', () => ({ toastApiError }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))

const EVENT = 'e1'

function page(items: SharedListRow[], patch: Partial<SharedListListResponse> = {}) {
  return {
    items,
    total: items.length,
    skip: 0,
    limit: 20,
    counts: { active: items.length, todo: 1, live: items.length, paused: 0, ended: 3 },
    ended_matching: 0,
    ...patch,
  }
}

function serve(lists: SharedListListResponse) {
  api.get.mockImplementation(({ url }: { url: string }) => {
    if (url === `/events/${EVENT}/shared-lists`) return Promise.resolve({ data: lists })
    if (url === `/events/${EVENT}/shared-lists/overview`)
      return Promise.resolve({ data: overview() })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

async function mountTab(lists: SharedListListResponse, query: Record<string, string> = {}) {
  serve(lists)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/app/shared-lists/:eventId?',
        name: 'shared-lists',
        component: { template: '<div />' },
      },
    ],
  })
  await router.push({ name: 'shared-lists', params: { eventId: EVENT }, query })
  const store = useSharedListsStore()
  store.setEvent(EVENT)
  store.overview = overview()
  const w = mount(SharedListsLinksTab, {
    attachTo: document.body,
    global: { plugins: [i18n, router] },
  })
  await flushPromises()
  return { w, router }
}

const tick = async (w: Awaited<ReturnType<typeof mountTab>>['w'], id: string) => {
  await w
    .get(`[data-testid="shared-list-row-${id}"] [data-testid="shared-list-select"]`)
    .trigger('click')
}

beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  stubMatchMedia(() => true)
  i18n.global.locale.value = 'en'
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('SharedListsLinksTab', () => {
  it('asks for the active lists first and shows the chips with their counts', async () => {
    const { w } = await mountTab(page([listRow('a'), listRow('b')]))

    expect(api.get).toHaveBeenCalledWith({
      url: `/events/${EVENT}/shared-lists`,
      query: { status_filter: 'active', sort_by: 'status', sort_dir: 'asc', skip: 0, limit: 20 },
    })
    expect(w.get('[data-testid="filter-chip-active"]').attributes('aria-pressed')).toBe('true')
    expect(w.get('[data-testid="filter-chip-ended"]').text()).toContain('3')
    expect(w.find('[data-testid="shared-lists-table"]').exists()).toBe(true)
  })

  it('shows cards on a narrow screen', async () => {
    stubMatchMedia(() => false)
    const { w } = await mountTab(page([listRow('a')]))
    expect(w.find('[data-testid="shared-lists-cards"]').exists()).toBe(true)
    expect(w.find('[data-testid="sort-select"]').exists()).toBe(true)
  })

  it('asks before ending the ticked lists, in the plural', async () => {
    const { w } = await mountTab(page([listRow('a'), listRow('b')]))
    await tick(w, 'a')
    await tick(w, 'b')

    await w.get('[data-testid="selection-action-end"]').trigger('click')
    expect(w.get('[data-testid="selection-confirm"]').text()).toContain('End 2 lists?')

    api.post.mockResolvedValueOnce({ data: { changed: ['a', 'b'], skipped: [] } })
    await w.get('[data-testid="shared-lists-bulk-end-confirm"]').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith({
      url: `/events/${EVENT}/shared-lists/bulk`,
      body: { action: 'end', list_ids: ['a', 'b'] },
    })
    expect(toast.success).toHaveBeenCalledWith('2 lists ended.')
    expect(w.find('[data-testid="selection-bar"]').exists()).toBe(false)
  })

  it('asks about one list in the singular, and can be called off', async () => {
    const { w } = await mountTab(page([listRow('a')]))
    await tick(w, 'a')

    await w.get('[data-testid="selection-action-end"]').trigger('click')
    expect(w.get('[data-testid="selection-confirm"]').text()).toContain('End this list?')
    expect(w.get('[data-testid="selection-confirm"]').text()).toContain('Its link stops working.')

    const cancel = w.get('[data-testid="selection-confirm"]').findAll('button').at(-1)!
    await cancel.trigger('click')
    expect(w.find('[data-testid="selection-confirm"]').exists()).toBe(false)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('pauses only when an open list is ticked, and says what was skipped', async () => {
    const { w } = await mountTab(
      page([listRow('a'), listRow('p', { status: 'paused', effective_status: 'paused' })]),
    )
    await tick(w, 'p')
    expect(w.get('[data-testid="selection-action-pause"]').attributes('aria-disabled')).toBe('true')

    await tick(w, 'a')
    api.post.mockResolvedValueOnce({
      data: { changed: ['a'], skipped: [{ id: 'p', code: 'shared_list.not_live' }] },
    })
    await w.get('[data-testid="selection-action-pause"]').trigger('click')
    await flushPromises()

    expect(toast.success).toHaveBeenCalledWith('1 list paused.')
    expect(toast.warning).toHaveBeenCalledWith('1 list could not be changed.')
  })

  it('stops everything, locking people in charge out when asked', async () => {
    const { w } = await mountTab(page([listRow('a')]))

    await w.get('[data-testid="shared-lists-pause-all"]').trigger('click')
    const confirm = w.get('[data-testid="shared-lists-pause-all-confirm"]')
    expect(confirm.text()).toContain('Pause the open list?')
    await confirm.get('[data-testid="shared-lists-pause-all-lock"]').trigger('click')

    api.post.mockResolvedValueOnce({ data: { changed: ['a'], skipped: [] } })
    await confirm.get('[data-testid="shared-lists-pause-all-confirm-button"]').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith({
      url: `/events/${EVENT}/shared-lists/pause-all`,
      body: { lock_managers: true },
    })
    expect(toast.success).toHaveBeenCalledWith('1 open list is paused.')
    expect(w.find('[data-testid="shared-lists-pause-all-confirm"]').exists()).toBe(false)
  })

  it('says there is nothing to do under "To do"', async () => {
    const { w } = await mountTab(page([]), { filter: 'todo' })
    expect(w.get('[data-testid="shared-lists-empty"]').text()).toBe(
      'Nothing to do. Every list is running as it should.',
    )
  })

  it('says nothing matched a search, and that ended lists match too', async () => {
    const { w, router } = await mountTab(page([], { ended_matching: 2 }), { q: 'Kuchen' })

    expect(w.get('[data-testid="shared-lists-empty"]').text()).toBe('No list matches “Kuchen”.')
    expect(w.get('[data-testid="shared-lists-ended-hidden"]').text()).toContain(
      '2 ended lists match too.',
    )
    await w.get('[data-testid="shared-lists-show-ended"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.filter).toBe('ended')
  })

  it('gives focus to the table when the selection is cleared from the bar', async () => {
    const { w } = await mountTab(page([listRow('a'), listRow('b')]))
    await tick(w, 'a')
    const clear = w.get('[data-testid="selection-clear"]')
    ;(clear.element as HTMLElement).focus()

    await clear.trigger('click')
    await flushPromises()

    expect(document.activeElement).toBe(w.get('[data-testid="shared-lists-select-all"]').element)
  })

  it('puts focus on the list once its fix has taken the issue strip away', async () => {
    const expiring = listRow('a', {
      issue: { kind: 'expires_soon', free: 2, task_names: [], days_left: 1 },
    })
    const { w } = await mountTab(page([expiring, listRow('b')]))
    const fix = w.get('[data-testid="shared-list-issue-fix"]')
    ;(fix.element as HTMLElement).focus()
    api.patch.mockResolvedValueOnce({ data: { id: 'a' } })
    serve(page([listRow('a'), listRow('b')]))

    await fix.trigger('click')
    await flushPromises()

    expect(w.find('[data-testid="shared-list-issue-fix"]').exists()).toBe(false)
    expect(document.activeElement).toBe(
      w.get('[data-testid="shared-list-row-a"] [data-testid="shared-list-title"]').element,
    )
  })

  it('keeps quiet about a page that a newer search has replaced', async () => {
    const { w, router } = await mountTab(page([listRow('a')]))
    let fail!: (error: Error) => void
    api.get.mockImplementationOnce(() => new Promise((_, reject) => (fail = reject)))
    await router.replace({ query: { q: 'Kuchen' } })
    await flushPromises()
    await router.replace({ query: { q: 'Kasse' } })
    await flushPromises()

    fail(new Error('502'))
    await flushPromises()

    expect(toastApiError).not.toHaveBeenCalled()
    expect(w.find('[data-testid="shared-lists-table"]').exists()).toBe(true)
  })

  it('invites to share the first list when there is none', async () => {
    const { w } = await mountTab(
      page([], { counts: { active: 0, todo: 0, live: 0, paused: 0, ended: 0 } }),
    )
    expect(w.get('[data-testid="shared-lists-empty"]').text()).toContain('No list shared yet.')
  })
})
