// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useBreadcrumbStore } from '@/stores/breadcrumb'
import { useSharedListsStore } from '@/stores/sharedLists'

import { listDetail, overview } from '@/components/shared-lists/__tests__/fixtures'

import type { SharedListDetail } from '@/client/types.gen'
import i18n from '@/locales/i18n'
import SharedListDetailView from '@/views/shared-lists/SharedListDetailView.vue'

/**
 * One list on its own page. Those who manage it get its actions under the
 * heading (a menu for the rest on a phone); a list the viewer only reads says
 * why and offers none. Renewing the link and ending ask first. A person in
 * charge whom the organisers stopped from sharing may still pause and end,
 * nothing else. A list that cannot be loaded leads back to the overview.
 */

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
const dialog = vi.hoisted(() => ({ confirm: vi.fn(), confirmDestructive: vi.fn() }))
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))
const route = vi.hoisted(() => ({
  name: 'shared-list-detail',
  params: { eventId: 'e1', listId: 'l1' } as Record<string, string>,
  query: {},
  hash: '',
}))
const toast = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn() }))
const toastApiError = vi.hoisted(() => vi.fn())
const phone = vi.hoisted(() => ({ value: false }))

vi.mock('@/composables/useAuthenticatedClient', () => ({ useAuthenticatedClient: () => api }))
vi.mock('@/composables/useDialog', () => ({ useDialog: () => dialog }))
vi.mock('vue-router', async (original) => ({
  ...(await original<typeof import('vue-router')>()),
  useRouter: () => router,
  useRoute: () => route,
}))
vi.mock('@vueuse/core', async (original) => ({
  ...(await original<typeof import('@vueuse/core')>()),
  useMediaQuery: () => ref(phone.value),
}))
vi.mock('vue-sonner', () => ({ toast }))
vi.mock('@/lib/api-errors', () => ({ toastApiError }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))

const STUBS = {
  RouterLink: { props: ['to'], template: '<a><slot /></a>' },
  // Its own table, with its own spec of the parts; it needs the router's query.
  SharedListSignups: true,
}

function serve(...lists: SharedListDetail[]) {
  api.get.mockImplementation(({ url }: { url: string }) => {
    if (url === '/events/e1/shared-lists/overview') return Promise.resolve({ data: overview() })
    const list = lists.find((candidate) => url === `/shared-lists/${candidate.id}`)
    return list
      ? Promise.resolve({ data: list })
      : Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

async function mountPage(list: SharedListDetail, overviewPatch = {}) {
  serve(list)
  route.params = { eventId: 'e1', listId: list.id }
  const w = mount(SharedListDetailView, {
    attachTo: document.body,
    global: { plugins: [i18n], stubs: STUBS },
  })
  await flushPromises()
  useSharedListsStore().overview = overview(overviewPatch)
  await flushPromises()
  return w
}

const byTestId = (w: Awaited<ReturnType<typeof mountPage>>, id: string) =>
  w.find(`[data-testid="${id}"]`)

beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  phone.value = false
  i18n.global.locale.value = 'en'
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('SharedListDetailView', () => {
  it('shows an open list with its link, figures, tasks and settings', async () => {
    const w = await mountPage(listDetail('l1', { view_count: 23 }))

    expect(byTestId(w, 'shared-list-detail-title').element.tagName).toBe('H1')
    expect(byTestId(w, 'shared-list-detail-title').text()).toBe('List l1')
    expect(w.text()).toContain('Elternchat 3b · created by Anna on')
    expect(byTestId(w, 'shared-list-url').text()).toBe(`${window.location.origin}/l/codel1`)
    expect(byTestId(w, 'shared-list-figure-views').text()).toBe('23×')
    expect(byTestId(w, 'shared-list-detail-task').text()).toContain('Kuchen · 3 shifts')
    expect(byTestId(w, 'shared-list-setting-asked').text()).toBe('name and email')
    expect(byTestId(w, 'shared-list-setting-perPerson').text()).toBe('as many shifts as are free')
    expect(byTestId(w, 'shared-list-detail-readonly').exists()).toBe(false)
  })

  it('names the list in the breadcrumbs, under the overview of its event', async () => {
    await mountPage(listDetail('l1'))
    expect(useBreadcrumbStore().breadcrumbs).toEqual([
      expect.objectContaining({
        titleKey: 'navigation.sidebar.items.sharedLists.label',
        to: { name: 'shared-lists', params: { eventId: 'e1' } },
      }),
      { title: 'List l1' },
    ])
  })

  it('gives an event admin pause, edit, a new link and end on an open list', async () => {
    const w = await mountPage(listDetail('l1'))

    for (const id of ['pause', 'edit', 'rotate', 'end']) {
      expect(byTestId(w, `shared-list-detail-${id}`).attributes('disabled')).toBeUndefined()
      expect(byTestId(w, `shared-list-detail-${id}`).attributes('aria-disabled')).toBeUndefined()
    }
    expect(byTestId(w, 'shared-list-detail-resume').exists()).toBe(false)
  })

  it('says "reopen" for an expired list and "resume" for a paused one', async () => {
    const expired = await mountPage(listDetail('l1', { effective_status: 'expired' }))
    expect(byTestId(expired, 'shared-list-detail-resume').text()).toBe('Reopen')
    expired.unmount()

    const paused = await mountPage(
      listDetail('l2', { status: 'paused', effective_status: 'paused' }),
    )
    expect(byTestId(paused, 'shared-list-detail-resume').text()).toBe('Resume')
  })

  it('tells a viewer why they cannot change the list, and offers nothing', async () => {
    const w = await mountPage(listDetail('l1', { access: 'viewer' }))

    expect(byTestId(w, 'shared-list-detail-readonly').text()).toContain(
      'only the organisers can change it',
    )
    expect(byTestId(w, 'shared-list-detail-actions').exists()).toBe(false)
  })

  it('lets a locked person in charge pause and end only', async () => {
    const w = await mountPage(listDetail('l1', { access: 'manager' }), {
      is_admin: false,
      managers_share_lists: false,
    })

    expect(byTestId(w, 'shared-list-detail-locked').exists()).toBe(true)
    expect(byTestId(w, 'shared-list-detail-pause').attributes('disabled')).toBeUndefined()
    expect(byTestId(w, 'shared-list-detail-end').attributes('disabled')).toBeUndefined()
    expect(byTestId(w, 'shared-list-detail-edit').attributes('disabled')).toBeDefined()
    expect(byTestId(w, 'shared-list-detail-rotate').attributes('disabled')).toBeDefined()
  })

  it('offers an ended list to be shared again, under a new link', async () => {
    const w = await mountPage(listDetail('l1', { status: 'ended', effective_status: 'ended' }))

    expect(byTestId(w, 'shared-list-link').exists()).toBe(false)
    expect(byTestId(w, 'shared-list-detail-pause').exists()).toBe(false)
    await byTestId(w, 'shared-list-detail-share-again').trigger('click')

    expect(router.push).toHaveBeenCalledWith({
      name: 'shared-list-create',
      params: { eventId: 'e1' },
      query: { from: 'l1' },
    })
  })

  it('opens the notice to print, for a viewer as well', async () => {
    const w = await mountPage(listDetail('l1', { access: 'viewer' }))
    await byTestId(w, 'shared-list-link-print').trigger('click')
    expect(router.push).toHaveBeenCalledWith({ name: 'print-list', params: { listId: 'l1' } })
  })

  it('opens the list as helpers see it in the overview’s preview', async () => {
    const w = await mountPage(listDetail('l1'))
    await byTestId(w, 'shared-list-link-preview').trigger('click')
    expect(router.push).toHaveBeenCalledWith({
      name: 'shared-lists',
      params: { eventId: 'e1' },
      query: { tab: 'preview', preview: 'l1' },
    })
  })

  it('goes to the editor', async () => {
    const w = await mountPage(listDetail('l1'))
    await byTestId(w, 'shared-list-detail-edit').trigger('click')
    expect(router.push).toHaveBeenCalledWith({
      name: 'shared-list-edit',
      params: { eventId: 'e1', listId: 'l1' },
    })
  })

  it('renews the link only after asking', async () => {
    const w = await mountPage(listDetail('l1'))
    api.post.mockResolvedValue({ data: listDetail('l1', { code: 'fresh' }) })

    dialog.confirm.mockResolvedValueOnce(false)
    await byTestId(w, 'shared-list-detail-rotate').trigger('click')
    await flushPromises()
    expect(api.post).not.toHaveBeenCalled()

    dialog.confirm.mockResolvedValueOnce(true)
    await byTestId(w, 'shared-list-detail-rotate').trigger('click')
    await flushPromises()

    expect(dialog.confirm).toHaveBeenLastCalledWith(
      expect.objectContaining({ title: 'Create a new link?' }),
    )
    expect(api.post).toHaveBeenCalledWith({ url: '/shared-lists/l1/rotate' })
    expect(toast.success).toHaveBeenCalledWith('New link created. The old one no longer works.')
    expect(byTestId(w, 'shared-list-url').text()).toContain('/l/fresh')
  })

  it('ends the list only after a warning', async () => {
    const w = await mountPage(listDetail('l1'))
    api.post.mockResolvedValue({ data: listDetail('l1', { effective_status: 'ended' }) })

    dialog.confirmDestructive.mockResolvedValueOnce(true)
    await byTestId(w, 'shared-list-detail-end').trigger('click')
    await flushPromises()

    expect(dialog.confirmDestructive).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'End this list?' }),
    )
    expect(api.post).toHaveBeenCalledWith({ url: '/shared-lists/l1/end' })
  })

  it('pauses without asking', async () => {
    const w = await mountPage(listDetail('l1'))
    api.post.mockResolvedValue({ data: listDetail('l1', { effective_status: 'paused' }) })

    await byTestId(w, 'shared-list-detail-pause').trigger('click')
    await flushPromises()

    expect(dialog.confirm).not.toHaveBeenCalled()
    expect(api.post).toHaveBeenCalledWith({ url: '/shared-lists/l1/pause' })
  })

  it('keeps one main action on a phone and the rest in a menu', async () => {
    phone.value = true
    const w = await mountPage(listDetail('l1'))

    expect(byTestId(w, 'shared-list-detail-pause').exists()).toBe(true)
    expect(byTestId(w, 'shared-list-detail-edit').exists()).toBe(false)
    expect(byTestId(w, 'shared-list-detail-more').attributes('aria-label')).toBe('More actions')
  })

  it('goes back to the overview when the list cannot be loaded', async () => {
    api.get.mockRejectedValue(new Error('404'))
    route.params = { eventId: 'e1', listId: 'gone' }
    mount(SharedListDetailView, { global: { plugins: [i18n], stubs: STUBS } })
    await flushPromises()

    expect(toastApiError).toHaveBeenCalledOnce()
    expect(router.replace).toHaveBeenCalledWith({
      name: 'shared-lists',
      params: { eventId: 'e1' },
    })
  })

  it('keeps focus on the toggle while it runs and when it turns into "resume"', async () => {
    const w = await mountPage(listDetail('l1'))
    let answer!: (value: { data: SharedListDetail }) => void
    api.post.mockReturnValueOnce(new Promise((resolve) => (answer = resolve)))
    const toggle = byTestId(w, 'shared-list-detail-pause')
    ;(toggle.element as HTMLElement).focus()

    await toggle.trigger('click')
    expect(toggle.attributes('aria-disabled')).toBe('true')
    expect(toggle.attributes('disabled')).toBeUndefined()
    await toggle.trigger('click')
    expect(api.post).toHaveBeenCalledOnce()

    answer({ data: listDetail('l1', { status: 'paused', effective_status: 'paused' }) })
    await flushPromises()
    expect(document.activeElement).toBe(byTestId(w, 'shared-list-detail-resume').element)
  })

  it('hands focus to "share again" once ending took its button away', async () => {
    const w = await mountPage(listDetail('l1'))
    api.post.mockResolvedValue({
      data: listDetail('l1', { status: 'ended', effective_status: 'ended' }),
    })
    dialog.confirmDestructive.mockResolvedValueOnce(true)
    const end = byTestId(w, 'shared-list-detail-end')
    ;(end.element as HTMLElement).focus()

    await end.trigger('click')
    await flushPromises()

    const shareAgain = byTestId(w, 'shared-list-detail-share-again').element
    expect(document.activeElement).toBe(shareAgain)
    // The same once the question closes after the list has ended.
    ;(shareAgain as HTMLElement).blur()
    dialog.confirmDestructive.mock.calls[0]![0].focusInstead()
    expect(document.activeElement).toBe(shareAgain)
  })

  it('forgets the list when the page is left', async () => {
    const w = await mountPage(listDetail('l1'))
    expect(useSharedListsStore().detail?.id).toBe('l1')
    w.unmount()
    expect(useSharedListsStore().detail).toBeNull()
  })
})
