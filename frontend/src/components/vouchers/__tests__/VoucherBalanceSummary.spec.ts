// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it } from 'vitest'

import VoucherBalanceSummary from '@/components/vouchers/VoucherBalanceSummary.vue'

import type { VoucherBalance } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The voucher numbers as one block: what is available, large, what booked
 * shifts will still bring, and where the number comes from.
 */

const balance = (over: Partial<VoucherBalance> = {}): VoucherBalance => ({
  user_id: 'u1',
  earned: 2,
  upcoming: 4,
  redeemed: 2,
  adjusted: 2,
  available: 2,
  ...over,
})

const text = (w: ReturnType<typeof mount>, id: string) => w.find(`[data-testid="${id}"]`).text()

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('VoucherBalanceSummary', () => {
  it('shows what is available, what is still to come and where it comes from', () => {
    const w = mount(VoucherBalanceSummary, {
      props: { summary: balance() },
      global: { plugins: [i18n] },
    })
    expect(text(w, 'voucher-available')).toBe('2')
    expect(w.text()).toContain('available')
    expect(text(w, 'voucher-upcoming')).toBe('4 more to come from booked shifts')
    expect(text(w, 'voucher-earned')).toBe('2')
    expect(text(w, 'voucher-used')).toBe('2')
    expect(text(w, 'voucher-adjusted')).toBe('+2')
  })

  it('signs a correction that took vouchers away with a real minus', () => {
    const w = mount(VoucherBalanceSummary, {
      props: { summary: balance({ adjusted: -1 }) },
      global: { plugins: [i18n] },
    })
    expect(text(w, 'voucher-adjusted')).toBe('−1')
  })

  it('stays quiet about shifts to come for yourself when there are none', () => {
    const w = mount(VoucherBalanceSummary, {
      props: { summary: balance({ upcoming: 0 }) },
      global: { plugins: [i18n] },
    })
    expect(w.find('[data-testid="voucher-upcoming"]').exists()).toBe(false)
  })

  it('tells an organiser that nobody booked more for this person', () => {
    i18n.global.locale.value = 'de'
    const w = mount(VoucherBalanceSummary, {
      props: { summary: balance({ upcoming: 0 }), other: true },
      global: { plugins: [i18n] },
    })
    expect(text(w, 'voucher-upcoming')).toBe('Keine weiteren Schichten gebucht.')
    expect(w.text()).toContain('verfügbar')
    expect(w.text()).toContain('Korrektur')
  })
})
