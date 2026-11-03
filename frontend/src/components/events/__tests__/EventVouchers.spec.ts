// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import EventVouchers from '@/components/events/EventVouchers.vue'

import type { VoucherBalance } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * "Who has how many vouchers" in the event settings: a summary over everyone
 * with anything to their name, and a search that narrows the rows by name or
 * e-mail address without changing that summary.
 */

const api = vi.hoisted(() => ({ get: vi.fn(), delete: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: api.get, delete: api.delete }),
}))
vi.mock('@/composables/useDialog', () => ({
  useDialog: () => ({ confirmDestructive: vi.fn() }),
}))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ profile: { id: 'u-org', time_format: 'h24' } }),
}))
vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))

function balance(overrides: Partial<VoucherBalance>): VoucherBalance {
  return {
    user_id: 'u',
    name: null,
    email: null,
    role: 'member',
    earned: 0,
    upcoming: 0,
    redeemed: 0,
    adjusted: 0,
    available: 0,
    ...overrides,
  }
}

const BALANCES: VoucherBalance[] = [
  balance({ user_id: 'u1', name: 'Mira Lindqvist', earned: 72, upcoming: 46, available: 72 }),
  balance({
    user_id: 'u2',
    name: 'Tomas Neruda',
    email: 'tomas@example.org',
    earned: 58,
    redeemed: 6,
    upcoming: 48,
    available: 52,
  }),
  balance({ user_id: 'u3', name: 'Vroni Hartmann', earned: 2, redeemed: 2, adjusted: 2, available: 2 }),
  // Nothing to their name: not a row, and not counted.
  balance({ user_id: 'u4', name: 'Nobody Yet' }),
]

const passthrough = { template: '<div><slot /></div>' }

async function mountOverview(balances: VoucherBalance[] = BALANCES) {
  api.get.mockResolvedValue({ data: balances })
  const w = mount(EventVouchers, {
    props: { eventId: 'e1', members: [] },
    global: {
      plugins: [i18n],
      stubs: {
        ResponsiveDialog: passthrough,
        ResponsiveDialogContent: passthrough,
        ResponsiveDialogHeader: passthrough,
        ResponsiveDialogTitle: passthrough,
        ResponsiveDialogDescription: passthrough,
        ResponsiveDialogBody: passthrough,
        ResponsiveDialogFooter: passthrough,
        VoucherAdjustmentDialog: true,
      },
    },
  })
  await new Promise((r) => setTimeout(r, 0))
  return w
}

const rowNames = (w: Awaited<ReturnType<typeof mountOverview>>) =>
  w.findAll('[data-testid="event-vouchers-row"]').map((r) => r.find('p').text())

beforeEach(() => {
  i18n.global.locale.value = 'en'
  vi.clearAllMocks()
})

describe('EventVouchers', () => {
  it('sums up everyone with vouchers and lists them', async () => {
    const w = await mountOverview()
    expect(api.get).toHaveBeenCalledWith({ url: '/events/e1/vouchers/people' })
    expect(w.find('[data-testid="event-vouchers-summary"]').text()).toBe(
      '3 people · 8 vouchers used · 94 still to come',
    )
    // A phone has less room for the line.
    expect(w.find('[data-testid="event-vouchers-summary-short"]').text()).toBe(
      '3 people · 8 used · 94 still to come',
    )
    expect(rowNames(w)).toEqual(['Mira Lindqvist', 'Tomas Neruda', 'Vroni Hartmann'])
    expect(w.findAll('[data-testid="event-vouchers-adjusted"]').map((c) => c.text())).toEqual([
      '0',
      '0',
      '+2',
    ])
  })

  it('narrows the rows by name or e-mail, keeping the summary', async () => {
    const w = await mountOverview()
    const search = w.find('[data-testid="event-vouchers-search"]')

    await search.setValue('  VRONI ')
    expect(rowNames(w)).toEqual(['Vroni Hartmann'])

    await search.setValue('example.org')
    expect(rowNames(w)).toEqual(['Tomas Neruda'])
    expect(w.find('[data-testid="event-vouchers-summary"]').text()).toContain('3 people')

    await search.setValue('zzz')
    expect(rowNames(w)).toEqual([])
    expect(w.find('[data-testid="event-vouchers-no-match"]').text()).toBe('Nobody matches “zzz”.')
  })

  it('offers no search while nobody has vouchers, but still a correction', async () => {
    const w = await mountOverview([balance({ user_id: 'u4', name: 'Nobody Yet' })])
    expect(w.text()).toContain('Nobody has earned vouchers yet.')
    expect(w.find('[data-testid="event-vouchers-search"]').exists()).toBe(false)
    expect(w.find('[data-testid="event-vouchers-legend"]').exists()).toBe(false)
    expect(w.find('[data-testid="btn-add-voucher-correction"]').exists()).toBe(true)
    expect(w.find('[data-testid="event-vouchers-summary"]').text()).toBe(
      '0 people · 0 vouchers used · 0 still to come',
    )
  })

  it('opens one person with their numbers in a card, their history and a way to correct', async () => {
    const w = await mountOverview()
    api.get.mockResolvedValueOnce({ data: { summary: BALANCES[2], shifts: [], entries: [] } })
    await w.findAll('[data-testid="event-vouchers-row"]')[2].trigger('click')
    await flushPromises()

    const detail = w.find('[data-testid="event-vouchers-detail"]')
    expect(api.get).toHaveBeenLastCalledWith({ url: '/events/e1/vouchers/people/u3' })
    expect(detail.text()).toContain('Vouchers of Vroni Hartmann')
    const summary = detail.find('[data-testid="event-vouchers-detail-summary"]')
    expect(summary.find('[data-testid="voucher-available"]').text()).toBe('2')
    expect(summary.text()).toContain('No more shifts booked.')
    expect(detail.text()).toContain('History')
    expect(detail.find('[data-testid="btn-person-add-correction"]').text()).toBe('Add correction')
  })
})
