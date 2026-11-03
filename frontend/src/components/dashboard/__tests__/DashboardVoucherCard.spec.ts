// @vitest-environment jsdom
import { RouterLinkStub, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it } from 'vitest'

import DashboardVoucherCard from '@/components/dashboard/DashboardVoucherCard.vue'

import type { VoucherAccount, VoucherShift } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The voucher card beside the next shift: the balance, what is still to come
 * (said as "after your shift today" only when that is the whole truth), the
 * corrections tile only when there are any, and the code button's states.
 */

const NOW = new Date(2026, 6, 18, 9, 0)

function voucherShift(overrides: Partial<VoucherShift> = {}): VoucherShift {
  return {
    booking_id: 'b1',
    shift_id: 's1',
    task_id: 't1',
    task_name: 'Cafétheke',
    title: 'Cafétheke 14:00-17:00',
    date: '2026-07-18',
    start_time: '14:00',
    end_time: '17:00',
    ends_at: '2026-07-18T17:00:00',
    vouchers: 2,
    completed: false,
    ...overrides,
  }
}

function account(
  summary: Partial<VoucherAccount['summary']> = {},
  shifts: VoucherShift[] = [],
): VoucherAccount {
  return {
    summary: {
      user_id: 'u1',
      earned: 6,
      upcoming: 0,
      redeemed: 2,
      adjusted: 0,
      available: 4,
      ...summary,
    },
    shifts,
    entries: [],
  }
}

function mountCard(props: Record<string, unknown> = {}) {
  return mount(DashboardVoucherCard, {
    props: {
      account: account(),
      now: NOW,
      eventId: 'e1',
      expired: false,
      canShowCode: true,
      ...props,
    },
    global: { plugins: [i18n], stubs: { RouterLink: RouterLinkStub } },
  })
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('DashboardVoucherCard', () => {
  it('shows what is available, earned and used', () => {
    const w = mountCard()
    expect(w.find('[data-testid="dashboard-voucher-available"]').text()).toBe('4')
    expect(w.text()).toContain('Earned')
    expect(w.text()).toContain('6')
    expect(w.text()).toContain('Used')
  })

  it('says nothing about upcoming vouchers when none are due', () => {
    const w = mountCard()
    expect(w.find('[data-testid="dashboard-voucher-available-short"]').text()).toBe('available')
    expect(w.find('[data-testid="dashboard-voucher-upcoming"]').exists()).toBe(false)
  })

  it('says "after your shift today" when every upcoming voucher is from today', () => {
    const w = mountCard({ account: account({ upcoming: 2 }, [voucherShift()]) })
    expect(w.find('[data-testid="dashboard-voucher-available-short"]').text()).toBe(
      'available, +2 to come',
    )
    expect(w.find('[data-testid="dashboard-voucher-upcoming"]').text()).toBe(
      '+2 more after your shift today',
    )
  })

  it('says "shifts" when today holds more than one', () => {
    const w = mountCard({
      account: account({ upcoming: 3 }, [
        voucherShift(),
        voucherShift({ booking_id: 'b2', shift_id: 's2', vouchers: 1 }),
      ]),
    })
    expect(w.find('[data-testid="dashboard-voucher-upcoming"]').text()).toBe(
      '+3 more after your shifts today',
    )
  })

  it('falls back to the plain line when some upcoming vouchers are another day’s', () => {
    const w = mountCard({
      account: account({ upcoming: 4 }, [
        voucherShift(),
        voucherShift({ booking_id: 'b2', date: '2026-07-19' }),
      ]),
    })
    expect(w.find('[data-testid="dashboard-voucher-upcoming"]').text()).toBe(
      '4 more for shifts you have booked',
    )
  })

  it('shows corrections only when there are any', () => {
    expect(mountCard().find('[data-testid="dashboard-voucher-adjusted"]').exists()).toBe(false)
    expect(
      mountCard({ account: account({ adjusted: 2 }) })
        .find('[data-testid="dashboard-voucher-adjusted"]')
        .text(),
    ).toContain('+2')
    expect(
      mountCard({ account: account({ adjusted: -1 }) })
        .find('[data-testid="dashboard-voucher-adjusted"]')
        .text(),
    ).toContain('-1')
  })

  it('shows the code on request, disables it with nothing to show, and hides it after the event', async () => {
    const w = mountCard()
    await w.find('[data-testid="btn-show-voucher-code"]').trigger('click')
    expect(w.emitted('showCode')).toHaveLength(1)

    const none = mountCard({ canShowCode: false })
    expect(none.find('[data-testid="btn-show-voucher-code"]').attributes('disabled')).toBeDefined()

    const over = mountCard({ expired: true })
    expect(over.find('[data-testid="btn-show-voucher-code"]').exists()).toBe(false)
    expect(over.find('[data-testid="btn-my-vouchers-details"]').exists()).toBe(true)
  })

  it('links to the voucher page of the event', () => {
    const link = mountCard()
      .findAllComponents(RouterLinkStub)
      .find((c) => c.attributes('data-testid') === 'btn-my-vouchers-details')!
    expect(link.props('to')).toEqual({ name: 'my-vouchers', params: { eventId: 'e1' } })
  })

  // Stretched to the next-shift card beside it, which is taller once it has a
  // map button, the side card had a hole between its numbers and the button.
  // As a phone tile it still stretches, so both tiles keep their buttons level.
  it('keeps its own height as the desktop side card', () => {
    const classes = mountCard().find('[data-testid="my-vouchers-card"]').classes()
    expect(classes).toContain('@4xl:self-start')
    expect(classes).not.toContain('self-start')
  })
})
