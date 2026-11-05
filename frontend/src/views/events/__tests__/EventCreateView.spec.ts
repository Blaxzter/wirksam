// @vitest-environment jsdom
import { flushPromises, shallowMount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/locales/i18n'
import EventCreateView from '@/views/events/EventCreateView.vue'

/**
 * Your role per event lives on the profile. Until it is read again it doesn't
 * know the event you just made, and the event's settings show only one tab.
 */

const calls = vi.hoisted(() => [] as string[])
const api = vi.hoisted(() => ({ post: vi.fn() }))
const store = vi.hoisted(() => ({ loadProfile: vi.fn() }))
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({ useAuthenticatedClient: () => api }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => store }))
vi.mock('@/stores/breadcrumb', () => ({
  useBreadcrumbStore: () => ({ setBreadcrumbs: vi.fn() }),
}))
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ query: {} }),
  useRouter: () => router,
}))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))

async function submitForm() {
  const w = shallowMount(EventCreateView, { global: { plugins: [i18n] } })
  const vm = w.vm as unknown as {
    name: string
    startDate: { toString(): string; toDate(zone: string): Date }
    endDate: { toString(): string; toDate(zone: string): Date }
    handleSubmit: () => Promise<void>
  }
  const day = { toString: () => '2027-07-01', toDate: () => new Date(2027, 6, 1) }
  vm.name = 'Summer festival'
  vm.startDate = day
  vm.endDate = day
  await vm.handleSubmit()
  await flushPromises()
}

beforeEach(() => {
  calls.length = 0
  vi.clearAllMocks()
  api.post.mockResolvedValue({ data: { id: 'e1' } })
  router.replace.mockImplementation(async () => {
    calls.push('navigate')
  })
})

describe('EventCreateView', () => {
  it('reads the profile again before leaving, so the new event counts as yours', async () => {
    store.loadProfile.mockImplementation(async () => {
      calls.push('loadProfile')
    })
    await submitForm()
    expect(calls).toEqual(['loadProfile', 'navigate'])
  })

  it('still moves on if reading the profile fails, since the event exists', async () => {
    store.loadProfile.mockRejectedValue(new Error('offline'))
    await submitForm()
    expect(calls).toEqual(['navigate'])
  })
})
