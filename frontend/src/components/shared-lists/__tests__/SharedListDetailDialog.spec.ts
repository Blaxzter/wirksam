// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { computed, defineComponent, h } from 'vue'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSharedListsStore } from '@/stores/sharedLists'

import { provideResponsiveDialogContext } from '@/components/ui/responsive-dialog/utils'

import SharedListDetailDialog from '@/components/shared-lists/SharedListDetailDialog.vue'

import type { SharedListDetail } from '@/client/types.gen'
import i18n from '@/locales/i18n'

import { listDetail, overview } from './fixtures'

/**
 * One list in full. Those who manage it get its actions at the foot (a menu
 * for the rest on a phone); a list the viewer only reads says why and offers
 * none. Renewing the link and ending ask first. A person in charge whom the
 * organisers stopped from sharing may still pause and end, nothing else.
 */

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
const dialog = vi.hoisted(() => ({ confirm: vi.fn(), confirmDestructive: vi.fn() }))
const push = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn() }))
const toastApiError = vi.hoisted(() => vi.fn())

vi.mock('@/composables/useAuthenticatedClient', () => ({ useAuthenticatedClient: () => api }))
vi.mock('@/composables/useDialog', () => ({ useDialog: () => dialog }))
vi.mock('vue-router', async (original) => ({
  ...(await original<typeof import('vue-router')>()),
  useRouter: () => ({ push }),
}))
vi.mock('vue-sonner', () => ({ toast }))
vi.mock('@/lib/api-errors', () => ({ toastApiError }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))

let mobile = false

/** The dialog shell, minus reka's portal: open or not, phone or not. */
const ShellStub = defineComponent({
  props: { open: Boolean },
  setup(props, { slots }) {
    provideResponsiveDialogContext({ isMobile: computed(() => mobile) })
    return () => (props.open ? h('div', slots.default?.()) : null)
  },
})
const passthrough = { template: '<div><slot /></div>' }
const STUBS = {
  ResponsiveDialog: ShellStub,
  ResponsiveDialogContent: passthrough,
  ResponsiveDialogTitle: passthrough,
  ResponsiveDialogDescription: passthrough,
  ResponsiveDialogBody: passthrough,
  // Its own table, with its own spec of the parts; it needs the router's query.
  SharedListSignups: true,
}

function serve(list: SharedListDetail) {
  api.get.mockImplementation(({ url }: { url: string }) =>
    url === `/shared-lists/${list.id}`
      ? Promise.resolve({ data: list })
      : Promise.reject(new Error(`unexpected GET ${url}`)),
  )
}

async function mountDialog(list: SharedListDetail, overviewPatch = {}) {
  serve(list)
  const store = useSharedListsStore()
  store.setEvent('e1')
  store.overview = overview(overviewPatch)
  const w = mount(SharedListDetailDialog, {
    props: { listId: list.id },
    attachTo: document.body,
    global: {
      plugins: [i18n],
      stubs: STUBS,
    },
  })
  await flushPromises()
  return w
}

const byTestId = (w: Awaited<ReturnType<typeof mountDialog>>, id: string) =>
  w.find(`[data-testid="${id}"]`)

beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  mobile = false
  i18n.global.locale.value = 'en'
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('SharedListDetailDialog', () => {
  it('shows an open list with its link, figures, tasks and settings', async () => {
    const w = await mountDialog(listDetail('l1', { view_count: 23 }))

    expect(byTestId(w, 'shared-list-detail-title').text()).toBe('List l1')
    expect(w.text()).toContain('Elternchat 3b · created by Anna on')
    expect(byTestId(w, 'shared-list-url').text()).toBe(`${window.location.origin}/l/codel1`)
    expect(byTestId(w, 'shared-list-figure-views').text()).toBe('23×')
    expect(byTestId(w, 'shared-list-detail-task').text()).toContain('Kuchen · 3 shifts')
    expect(byTestId(w, 'shared-list-setting-asked').text()).toBe('name and email')
    expect(byTestId(w, 'shared-list-setting-perPerson').text()).toBe('as many shifts as are free')
    expect(byTestId(w, 'shared-list-detail-readonly').exists()).toBe(false)
  })

  it('gives an event admin pause, edit, a new link and end on an open list', async () => {
    const w = await mountDialog(listDetail('l1'))

    for (const id of ['pause', 'edit', 'rotate', 'end']) {
      expect(byTestId(w, `shared-list-detail-${id}`).attributes('disabled')).toBeUndefined()
      expect(byTestId(w, `shared-list-detail-${id}`).attributes('aria-disabled')).toBeUndefined()
    }
    expect(byTestId(w, 'shared-list-detail-resume').exists()).toBe(false)
  })

  it('says "reopen" for an expired list and "resume" for a paused one', async () => {
    const expired = await mountDialog(listDetail('l1', { effective_status: 'expired' }))
    expect(byTestId(expired, 'shared-list-detail-resume').text()).toBe('Reopen')
    expired.unmount()

    const paused = await mountDialog(
      listDetail('l2', { status: 'paused', effective_status: 'paused' }),
    )
    expect(byTestId(paused, 'shared-list-detail-resume').text()).toBe('Resume')
  })

  it('tells a viewer why they cannot change the list, and offers nothing', async () => {
    const w = await mountDialog(listDetail('l1', { access: 'viewer' }))

    expect(byTestId(w, 'shared-list-detail-readonly').text()).toContain(
      'only the organisers can change it',
    )
    expect(byTestId(w, 'shared-list-detail-footer').exists()).toBe(false)
  })

  it('lets a locked person in charge pause and end only', async () => {
    const w = await mountDialog(listDetail('l1', { access: 'manager' }), {
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
    const w = await mountDialog(listDetail('l1', { status: 'ended', effective_status: 'ended' }))

    expect(byTestId(w, 'shared-list-link').exists()).toBe(false)
    expect(byTestId(w, 'shared-list-detail-pause').exists()).toBe(false)
    await byTestId(w, 'shared-list-detail-share-again').trigger('click')

    expect(push).toHaveBeenCalledWith({
      name: 'shared-list-create',
      params: { eventId: 'e1' },
      query: { from: 'l1' },
    })
  })

  it('opens the notice to print, for a viewer as well', async () => {
    const w = await mountDialog(listDetail('l1', { access: 'viewer' }))
    await byTestId(w, 'shared-list-link-print').trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'print-list', params: { listId: 'l1' } })
  })

  it('goes to the editor', async () => {
    const w = await mountDialog(listDetail('l1'))
    await byTestId(w, 'shared-list-detail-edit').trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: 'shared-list-edit',
      params: { eventId: 'e1', listId: 'l1' },
    })
  })

  it('renews the link only after asking', async () => {
    const w = await mountDialog(listDetail('l1'))
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
    const w = await mountDialog(listDetail('l1'))
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
    const w = await mountDialog(listDetail('l1'))
    api.post.mockResolvedValue({ data: listDetail('l1', { effective_status: 'paused' }) })

    await byTestId(w, 'shared-list-detail-pause').trigger('click')
    await flushPromises()

    expect(dialog.confirm).not.toHaveBeenCalled()
    expect(api.post).toHaveBeenCalledWith({ url: '/shared-lists/l1/pause' })
  })

  it('keeps one main action on a phone and the rest in a menu', async () => {
    mobile = true
    const w = await mountDialog(listDetail('l1'))

    expect(byTestId(w, 'shared-list-detail-pause').exists()).toBe(true)
    expect(byTestId(w, 'shared-list-detail-edit').exists()).toBe(false)
    expect(byTestId(w, 'shared-list-detail-more').attributes('aria-label')).toBe('More actions')
  })

  it('closes when the list cannot be loaded', async () => {
    api.get.mockRejectedValue(new Error('404'))
    const store = useSharedListsStore()
    store.setEvent('e1')
    const w = mount(SharedListDetailDialog, {
      props: { listId: 'gone' },
      global: { plugins: [i18n], stubs: STUBS },
    })
    await flushPromises()

    expect(toastApiError).toHaveBeenCalled()
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('keeps focus on the toggle while it runs and when it turns into "resume"', async () => {
    const w = await mountDialog(listDetail('l1'))
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
    const w = await mountDialog(listDetail('l1'))
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

  it('stays open when a list it no longer shows fails to load', async () => {
    let fail!: (error: Error) => void
    api.get.mockImplementation(({ url }: { url: string }) =>
      url === '/shared-lists/gone'
        ? new Promise((_, reject) => (fail = reject))
        : Promise.resolve({ data: listDetail('l2') }),
    )
    const store = useSharedListsStore()
    store.setEvent('e1')
    store.overview = overview()
    const w = mount(SharedListDetailDialog, {
      props: { listId: 'gone' },
      global: { plugins: [i18n], stubs: STUBS },
    })
    await w.setProps({ listId: 'l2' })
    await flushPromises()

    fail(new Error('404'))
    await flushPromises()

    expect(toastApiError).not.toHaveBeenCalled()
    expect(w.emitted('close')).toBeUndefined()
    expect(byTestId(w, 'shared-list-detail-title').text()).toBe('List l2')
  })

  it('opens the preview of the list', async () => {
    const w = await mountDialog(listDetail('l1'))
    await byTestId(w, 'shared-list-link-preview').trigger('click')
    expect(w.emitted('preview')).toEqual([['l1']])
  })
})
