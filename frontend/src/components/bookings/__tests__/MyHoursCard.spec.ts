// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import MyHoursCard from '@/components/bookings/MyHoursCard.vue'

import type { VolunteerHours, VolunteerHoursDetail } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The hours on the bookings page: a tile on a phone ("3 h", "worked, +6
 * planned"), the full card on a wider page, and the breakdown in a sheet or
 * dialog instead of folded open under the numbers.
 */

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: api.get }),
}))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ selectedEventId: 'e1', profile: { id: 'u1', time_format: 'h24' } }),
}))

const passthrough = { template: '<div><slot /></div>' }

function detail(over: Partial<VolunteerHours> = {}): VolunteerHoursDetail {
  return {
    summary: {
      user_id: 'u1',
      shift_count: 1,
      shift_minutes: 180,
      upcoming_shift_count: 2,
      upcoming_shift_minutes: 360,
      untimed_shift_count: 0,
      manual_minutes: 0,
      total_minutes: 180,
      ...over,
    },
    shifts: [],
    work_logs: [],
  }
}

async function mountCard() {
  const w = mount(MyHoursCard, {
    global: {
      plugins: [i18n],
      stubs: {
        ResponsiveDialog: { props: ['open'], template: '<div v-if="open"><slot /></div>' },
        ResponsiveDialogContent: passthrough,
        ResponsiveDialogHeader: passthrough,
        ResponsiveDialogTitle: passthrough,
        ResponsiveDialogDescription: passthrough,
        ResponsiveDialogBody: passthrough,
        HoursBreakdown: { template: '<div data-testid="hours-breakdown-stub" />' },
      },
    },
  })
  await flushPromises()
  return w
}

const text = (w: Awaited<ReturnType<typeof mountCard>>, id: string) =>
  w.find(`[data-testid="${id}"]`).text()

beforeEach(() => {
  i18n.global.locale.value = 'en'
  vi.clearAllMocks()
})

describe('MyHoursCard', () => {
  it('reads the hours of the selected event', async () => {
    api.get.mockResolvedValue({ data: detail() })
    await mountCard()
    expect(api.get).toHaveBeenCalledWith({ url: '/events/e1/hours/u1' })
  })

  it('puts the hours worked and planned in one line on the tile', async () => {
    api.get.mockResolvedValue({ data: detail() })
    const w = await mountCard()
    expect(text(w, 'my-hours-short')).toBe('worked, +6 planned')

    i18n.global.locale.value = 'de'
    const de = await mountCard()
    expect(text(de, 'my-hours-short')).toBe('geleistet, +6 geplant')
  })

  it('shows the hours large on the card, with what is still to come and where they came from', async () => {
    api.get.mockResolvedValue({ data: detail({ manual_minutes: 60, total_minutes: 240 }) })
    const w = await mountCard()
    expect(text(w, 'my-hours-total')).toBe('4')
    expect(w.text()).toContain('h worked')
    expect(text(w, 'my-hours-upcoming')).toBe('6 h more to come from booked shifts')
    expect(w.text()).toContain('From shifts')
    expect(w.text()).toContain('Additional')
  })

  it('opens the breakdown on request', async () => {
    api.get.mockResolvedValue({ data: detail() })
    const w = await mountCard()
    expect(w.find('[data-testid="hours-breakdown-stub"]').exists()).toBe(false)
    await w.find('[data-testid="btn-toggle-hours-breakdown"]').trigger('click')
    expect(w.find('[data-testid="hours-breakdown-stub"]').exists()).toBe(true)
  })

  it('says there is nothing yet, and offers no breakdown of nothing', async () => {
    api.get.mockResolvedValue({
      data: detail({
        shift_count: 0,
        shift_minutes: 0,
        upcoming_shift_count: 0,
        upcoming_shift_minutes: 0,
        total_minutes: 0,
      }),
    })
    const w = await mountCard()
    expect(w.text()).toContain('No hours yet.')
    expect(w.find('[data-testid="btn-toggle-hours-breakdown"]').exists()).toBe(false)
    expect(w.find('[data-testid="btn-hours-breakdown-tile"]').exists()).toBe(false)
    expect(text(w, 'my-hours-short')).toBe('worked')
  })

  it('stays hidden when the hours cannot be read', async () => {
    api.get.mockRejectedValue(new Error('403'))
    const w = await mountCard()
    expect(w.find('[data-testid="my-hours-card"]').exists()).toBe(false)
  })
})
