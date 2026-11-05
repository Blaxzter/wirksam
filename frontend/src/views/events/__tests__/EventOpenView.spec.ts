// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/locales/i18n'
import EventOpenView from '@/views/events/EventOpenView.vue'

/** Where the QR code on a printed event sheet takes someone. */

const router = vi.hoisted(() => ({ replace: vi.fn() }))
const store = vi.hoisted(() => ({
  selectedEventId: 'other' as string | null,
  isEventMember: vi.fn(),
  setSelectedEvent: vi.fn(),
}))
const errors = vi.hoisted(() => ({ toastApiError: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => store }))
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ params: { eventId: 'e1' } }),
  useRouter: () => router,
}))
vi.mock('@/lib/api-errors', () => errors)

async function open() {
  mount(EventOpenView, { global: { plugins: [i18n] } })
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  store.selectedEventId = 'other'
  store.setSelectedEvent.mockResolvedValue({})
})

describe('EventOpenView', () => {
  it('selects the event and opens its tasks for someone in it', async () => {
    store.isEventMember.mockReturnValue(true)
    await open()
    expect(store.setSelectedEvent).toHaveBeenCalledWith('e1')
    expect(router.replace).toHaveBeenCalledWith({ name: 'tasks' })
  })

  it('leaves the selection alone when the event is already selected', async () => {
    store.isEventMember.mockReturnValue(true)
    store.selectedEventId = 'e1'
    await open()
    expect(store.setSelectedEvent).not.toHaveBeenCalled()
    expect(router.replace).toHaveBeenCalledWith({ name: 'tasks' })
  })

  it('offers Discover to someone who is not in the event', async () => {
    store.isEventMember.mockReturnValue(false)
    await open()
    expect(store.setSelectedEvent).not.toHaveBeenCalled()
    expect(router.replace).toHaveBeenCalledWith({
      name: 'select-event',
      query: { mode: 'switch', tab: 'discover' },
    })
  })

  it('treats someone without any event as a newcomer', async () => {
    store.isEventMember.mockReturnValue(false)
    store.selectedEventId = null
    await open()
    expect(router.replace).toHaveBeenCalledWith({
      name: 'select-event',
      query: { mode: 'onboarding', tab: 'discover' },
    })
  })

  it('goes home if the event cannot be selected', async () => {
    store.isEventMember.mockReturnValue(true)
    store.setSelectedEvent.mockRejectedValue(new Error('nope'))
    await open()
    expect(errors.toastApiError).toHaveBeenCalled()
    expect(router.replace).toHaveBeenCalledWith({ name: 'home' })
  })
})
