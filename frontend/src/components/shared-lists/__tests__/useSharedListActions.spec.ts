// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSharedListsStore } from '@/stores/sharedLists'

import { COPIED_MS } from '@/composables/useClipboardCopy'

import {
  canManageList,
  isListSelectable,
  issueFix,
  resumeLabelKey,
  useSharedListActions,
} from '@/components/shared-lists/useSharedListActions'

import i18n from '@/locales/i18n'

import { listDetail, listRow } from './fixtures'

/**
 * A list's own buttons, wherever they are: who may use them, what an issue's
 * fix is, and the toast each change ends with. Copying falls back to showing
 * the link when the clipboard is blocked.
 */

const toast = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn() }))
const toastApiError = vi.hoisted(() => vi.fn())
vi.mock('vue-sonner', () => ({ toast }))
vi.mock('@/lib/api-errors', () => ({ toastApiError }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }),
}))

function actions() {
  let api!: ReturnType<typeof useSharedListActions>
  mount(
    defineComponent({
      setup() {
        api = useSharedListActions()
        return () => null
      },
    }),
    { global: { plugins: [i18n] } },
  )
  return api
}

function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
}

beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  i18n.global.locale.value = 'en'
})

afterEach(() => {
  vi.useRealTimers()
})

describe('who may do what', () => {
  it('lets admins and people in charge of every task manage a list', () => {
    expect(canManageList({ access: 'admin' })).toBe(true)
    expect(canManageList({ access: 'manager' })).toBe(true)
    expect(canManageList({ access: 'viewer' })).toBe(false)
  })

  it('ticks only lists the viewer manages that have not ended', () => {
    expect(isListSelectable(listRow('a'))).toBe(true)
    expect(isListSelectable(listRow('a', { effective_status: 'ended' }))).toBe(false)
    expect(isListSelectable(listRow('a', { access: 'viewer' }))).toBe(false)
  })

  it('calls resuming an expired list reopening it', () => {
    expect(resumeLabelKey('expired')).toBe('sharedLists.actions.reopen')
    expect(resumeLabelKey('paused')).toBe('sharedLists.actions.resume')
  })

  it('fixes an issue by extending or resuming', () => {
    expect(issueFix(listRow('a'))).toBeNull()
    expect(
      issueFix(listRow('a', { issue: { kind: 'expires_soon', free: 1, task_names: [] } })),
    ).toEqual({ action: 'extend', labelKey: 'sharedLists.actions.extend' })
    expect(
      issueFix(
        listRow('a', {
          effective_status: 'expired',
          issue: { kind: 'stranded', free: 1, task_names: [] },
        }),
      ),
    ).toEqual({ action: 'resume', labelKey: 'sharedLists.actions.reopen' })
  })
})

describe('useSharedListActions', () => {
  it('copies the link and shows a tick for a moment', async () => {
    vi.useFakeTimers()
    const writeText = vi.fn().mockResolvedValue(undefined)
    stubClipboard(writeText)
    const { copyLink, copiedId } = actions()

    await copyLink({ id: 'a', code: 'abc' })

    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/l/abc`)
    expect(toast.success).toHaveBeenCalledWith('Link copied.')
    expect(copiedId.value).toBe('a')
    vi.advanceTimersByTime(COPIED_MS)
    expect(copiedId.value).toBeNull()
  })

  it('keeps the newer tick when another link was copied meanwhile', async () => {
    vi.useFakeTimers()
    stubClipboard(vi.fn().mockResolvedValue(undefined))
    const { copyLink, copiedId } = actions()

    await copyLink({ id: 'a', code: 'abc' })
    vi.advanceTimersByTime(COPIED_MS / 2)
    await copyLink({ id: 'b', code: 'def' })
    vi.advanceTimersByTime(COPIED_MS / 2)

    expect(copiedId.value).toBe('b')
  })

  it('shows the link when the clipboard is blocked', async () => {
    stubClipboard(vi.fn().mockRejectedValue(new Error('denied')))
    const { copyLink, copiedId } = actions()

    await copyLink({ id: 'a', code: 'abc' })

    expect(toast.info).toHaveBeenCalledWith(`${window.location.origin}/l/abc`)
    expect(copiedId.value).toBeNull()
  })

  it.each([
    ['pause', 'live', '“Kuchen” is paused. Anyone who opens the link cannot sign up for now.'],
    ['resume', 'paused', '“Kuchen” is open again.'],
    ['resume', 'expired', '“Kuchen” is open again until its last shift starts.'],
    ['extend', 'live', '“Kuchen” stays open until its last shift starts.'],
    ['end', 'live', '“Kuchen” has ended. Everyone signed up stays signed up.'],
    ['rotate', 'live', 'New link created. The old one no longer works.'],
  ] as const)('ends %s of a %s list with a toast', async (action, status, message) => {
    const act = vi.spyOn(useSharedListsStore(), 'act').mockResolvedValue(listDetail('a'))
    const { run, busyId } = actions()

    const done = run({ id: 'a', title: 'Kuchen', effective_status: status }, action)
    expect(busyId.value).toBe('a')

    await expect(done).resolves.toBe(true)
    expect(act).toHaveBeenCalledWith('a', action)
    expect(toast.success).toHaveBeenCalledWith(message)
    expect(busyId.value).toBeNull()
  })

  it('reports a refusal and resolves to false', async () => {
    const failure = new Error('409')
    vi.spyOn(useSharedListsStore(), 'act').mockRejectedValue(failure)
    const { run, busyId } = actions()

    await expect(
      run({ id: 'a', title: 'Kuchen', effective_status: 'live' }, 'pause'),
    ).resolves.toBe(false)
    await flushPromises()

    expect(toastApiError).toHaveBeenCalledWith(failure)
    expect(toast.success).not.toHaveBeenCalled()
    expect(busyId.value).toBeNull()
  })
})
