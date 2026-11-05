// @vitest-environment jsdom
import { flushPromises, shallowMount } from '@vue/test-utils'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/locales/i18n'
import ReportingView from '@/views/admin/ReportingView.vue'

/**
 * The default range ends on the last of next month. Worked out from a local
 * midnight, which in Berlin is still the day before in UTC, it came out a day
 * early, so this runs in a zone ahead of UTC whatever the machine's own is.
 */

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({ useAuthenticatedClient: () => api }))
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: vi.fn() }),
}))
vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))

const systemTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone

beforeEach(() => {
  process.env.TZ = 'Europe/Berlin'
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 10, 4, 12))
  api.get.mockReset()
  // Only the request matters here, not what the page does with an answer.
  api.get.mockRejectedValue(new Error('not needed'))
})

afterEach(() => {
  vi.useRealTimers()
  process.env.TZ = systemTimeZone
})

describe('ReportingView', () => {
  it('runs from the first of this month to the last of next month', async () => {
    shallowMount(ReportingView, { global: { plugins: [i18n] } })
    await flushPromises()

    const url: string = api.get.mock.calls[0][0].url
    expect(url).toContain('date_from=2026-11-01')
    expect(url).toContain('date_to=2026-12-31')
  })
})
