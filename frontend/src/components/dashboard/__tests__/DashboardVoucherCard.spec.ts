// @vitest-environment jsdom
import { RouterLinkStub, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it } from 'vitest'

import DashboardVoucherCard from '@/components/dashboard/DashboardVoucherCard.vue'

import type { VoucherAccount } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The voucher card beside the next shift: the phone tile's number and line,
 * the numbers block it shares with "My vouchers" (corrections always shown,
 * the same line for what is still to come), and the code button's states.
 */

function account(summary: Partial<VoucherAccount['summary']> = {}): VoucherAccount {
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
    shifts: [],
    entries: [],
  }
}

function mountCard(props: Record<string, unknown> = {}) {
  return mount(DashboardVoucherCard, {
    props: {
      account: account(),
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
  it('shows what is available, earned, used and corrected in the shared block', () => {
    const w = mountCard()
    expect(w.find('[data-testid="dashboard-voucher-available"]').text()).toBe('4')
    const block = w.find('[data-testid="voucher-balance"]')
    expect(block.find('[data-testid="voucher-available"]').text()).toBe('4')
    expect(block.find('[data-testid="voucher-earned"]').text()).toBe('6')
    expect(block.find('[data-testid="voucher-used"]').text()).toBe('2')
    // A correction tile even at 0, as on "My vouchers", so the sum always adds up.
    expect(block.find('[data-testid="voucher-adjusted"]').text()).toBe('0')
  })

  it('signs a correction', () => {
    const tile = (adjusted: number) =>
      mountCard({ account: account({ adjusted }) })
        .find('[data-testid="voucher-adjusted"]')
        .text()
    expect(tile(2)).toBe('+2')
    expect(tile(-1)).toBe('−1')
  })

  it('says nothing about upcoming vouchers when none are due', () => {
    const w = mountCard()
    expect(w.find('[data-testid="dashboard-voucher-available-short"]').text()).toBe('available')
    expect(w.find('[data-testid="voucher-upcoming"]').exists()).toBe(false)
  })

  it('says what is still to come in the words of "My vouchers"', () => {
    const w = mountCard({ account: account({ upcoming: 2 }) })
    expect(w.find('[data-testid="dashboard-voucher-available-short"]').text()).toBe(
      'available, +2 to come',
    )
    expect(w.find('[data-testid="voucher-upcoming"]').text()).toBe(
      '2 more to come from booked shifts',
    )
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
