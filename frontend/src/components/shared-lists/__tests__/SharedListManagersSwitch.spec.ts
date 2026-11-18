// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSharedListsStore } from '@/stores/sharedLists'

import SharedListManagersSwitch from '@/components/shared-lists/SharedListManagersSwitch.vue'

import i18n from '@/locales/i18n'

/**
 * Event admins decide whether people in charge share their own tasks. Nobody
 * else sees the switch; turning it off says what people in charge can still
 * do, and a refusal puts the switch back.
 */

const toast = vi.hoisted(() => ({ success: vi.fn() }))
const toastApiError = vi.hoisted(() => vi.fn())
vi.mock('vue-sonner', () => ({ toast }))
vi.mock('@/lib/api-errors', () => ({ toastApiError }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }),
}))

function mountSwitch(enabled: boolean, isAdmin = true) {
  return mount(SharedListManagersSwitch, {
    props: { enabled, isAdmin },
    global: { plugins: [i18n] },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  i18n.global.locale.value = 'en'
})

describe('SharedListManagersSwitch', () => {
  it('is only there for event admins', () => {
    expect(mountSwitch(true, false).find('[data-testid="shared-lists-managers"]').exists()).toBe(
      false,
    )
    expect(mountSwitch(true).find('[data-testid="shared-lists-managers"]').exists()).toBe(true)
  })

  it('says what people in charge may do either way', () => {
    expect(mountSwitch(true).text()).toContain('can share, pause and end it themselves')
    expect(mountSwitch(false).text()).toContain('but not reopen them')
  })

  it('turns sharing off for people in charge and says so', async () => {
    const store = useSharedListsStore()
    let saved!: () => void
    const save = vi
      .spyOn(store, 'setManagersShareLists')
      .mockReturnValue(new Promise<void>((resolve) => (saved = resolve)))
    const w = mountSwitch(true)
    const control = () => w.get('[data-testid="shared-lists-managers-switch"]')

    await control().trigger('click')
    // Shows what was asked for, and takes no second click, while the server is
    // told; it keeps focus meanwhile, which a disabled switch would drop.
    expect(control().attributes('aria-checked')).toBe('false')
    expect(control().attributes('aria-disabled')).toBe('true')
    expect(control().attributes('disabled')).toBeUndefined()
    await control().trigger('click')
    saved()
    await flushPromises()

    expect(save).toHaveBeenCalledOnce()
    expect(save).toHaveBeenCalledWith(false)
    expect(control().attributes('aria-disabled')).toBeUndefined()
    expect(toast.success).toHaveBeenCalledWith('Only the organisers can share lists now.')
  })

  it('goes back to what the server has when it refuses', async () => {
    const store = useSharedListsStore()
    const failure = new Error('403')
    vi.spyOn(store, 'setManagersShareLists').mockRejectedValue(failure)
    const w = mountSwitch(false)

    await w.get('[data-testid="shared-lists-managers-switch"]').trigger('click')
    await flushPromises()

    expect(toastApiError).toHaveBeenCalledWith(failure)
    const control = w.get('[data-testid="shared-lists-managers-switch"]')
    expect(control.attributes('aria-checked')).toBe('false')
    expect(control.attributes('aria-disabled')).toBeUndefined()
  })
})
