// @vitest-environment jsdom
import { RouterLinkStub, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it } from 'vitest'

import MyVouchersCard from '@/components/vouchers/MyVouchersCard.vue'

import type { VoucherAccount, VoucherBalance } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The vouchers on the bookings page: a tile on a phone ("2", "available, +4
 * to come", the code button), the full numbers block on a wider page, and the
 * way to the history either way.
 */

const account = (over: Partial<VoucherBalance> = {}): VoucherAccount => ({
  summary: {
    user_id: 'u1',
    earned: 2,
    upcoming: 4,
    redeemed: 2,
    adjusted: 2,
    available: 2,
    ...over,
  },
  shifts: [],
  entries: [],
})

function mountCard(props: Record<string, unknown> = {}) {
  return mount(MyVouchersCard, {
    props: { account: account(), eventId: 'e1', expired: false, canShowCode: true, ...props },
    global: { plugins: [i18n], stubs: { RouterLink: RouterLinkStub } },
  })
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('MyVouchersCard', () => {
  it('says in one line what is available and what is still to come', () => {
    const w = mountCard()
    expect(w.find('[data-testid="my-vouchers-available-short"]').text()).toBe(
      'available, +4 to come',
    )
    i18n.global.locale.value = 'de'
    const de = mountCard()
    expect(de.find('[data-testid="my-vouchers-available-short"]').text()).toBe(
      'verfügbar, +4 kommen',
    )
  })

  it('leaves out what is to come when no booked shift brings more', () => {
    const w = mountCard({ account: account({ upcoming: 0 }) })
    expect(w.find('[data-testid="my-vouchers-available-short"]').text()).toBe('available')
  })

  it('carries the full numbers block for the wider card', () => {
    const w = mountCard()
    expect(w.find('[data-testid="voucher-earned"]').text()).toBe('2')
    expect(w.find('[data-testid="voucher-adjusted"]').text()).toBe('+2')
  })

  it('leads to the history of this event', () => {
    const w = mountCard()
    const links = w.findAllComponents(RouterLinkStub)
    expect(links.length).toBeGreaterThan(0)
    for (const link of links) {
      expect(link.props('to')).toEqual({ name: 'my-vouchers', params: { eventId: 'e1' } })
    }
    // One link, chevron in the tile and "History" on the card, so the test id
    // never lands on a copy hidden at the current width.
    const details = w.findAll('[data-testid="btn-my-vouchers-details"]')
    expect(details).toHaveLength(1)
    expect(details[0]!.attributes('aria-label')).toBe('My vouchers, history')
    expect(details[0]!.text()).toBe('History')
  })

  it('shows the code on request, disabled with nothing to use, and not after the event', async () => {
    const w = mountCard()
    await w.find('[data-testid="btn-show-voucher-code"]').trigger('click')
    expect(w.emitted('showCode')).toHaveLength(1)

    const none = mountCard({ canShowCode: false })
    expect(none.find('[data-testid="btn-show-voucher-code"]').attributes('disabled')).toBeDefined()

    const over = mountCard({ expired: true })
    expect(over.find('[data-testid="btn-show-voucher-code"]').exists()).toBe(false)
  })
})
