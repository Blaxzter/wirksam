// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import VoucherHistory from '@/components/vouchers/VoucherHistory.vue'

import type { VoucherAccount, VoucherEntryRead, VoucherShift } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * Where vouchers came from and went. On the volunteer's own page the shifts
 * still to come sit on top under their own heading; in an organiser's dialog
 * it is one list, with a menu on each correction.
 */

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ profile: { id: 'u1', time_format: 'h24' } }),
}))

const shift = (over: Partial<VoucherShift> = {}): VoucherShift => ({
  booking_id: 'b1',
  shift_id: 's1',
  task_id: 't1',
  task_name: 'Wristband check',
  title: 'Wristband check 16:00',
  date: '2026-07-17',
  start_time: '16:00:00',
  end_time: '19:00:00',
  ends_at: '2026-07-17T17:00:00',
  vouchers: 2,
  completed: true,
  ...over,
})

const entry = (over: Partial<VoucherEntryRead> = {}): VoucherEntryRead => ({
  id: 'e1',
  kind: 'redemption',
  amount: -2,
  task_name: 'Café counter',
  actor_name: 'Pia Incharge',
  created_at: '2026-07-18T13:03:00',
  updated_at: '2026-07-18T13:03:00',
  ...over,
})

const ACCOUNT: Pick<VoucherAccount, 'shifts' | 'entries'> = {
  shifts: [
    shift(),
    shift({
      booking_id: 'b2',
      task_name: 'Grill stand',
      date: '2026-07-18',
      start_time: '17:00:00',
      end_time: '20:00:00',
      ends_at: '2026-07-18T18:00:00',
      completed: false,
    }),
  ],
  entries: [
    entry(),
    entry({
      id: 'e2',
      kind: 'adjustment',
      amount: 2,
      task_name: null,
      note: 'Helped with the set-up without a shift',
      actor_name: 'Anna Berger',
      created_at: '2026-07-17T19:10:00',
    }),
  ],
}

function mountHistory(props: Record<string, unknown> = {}) {
  return mount(VoucherHistory, {
    props: { account: ACCOUNT, ...props },
    global: { plugins: [i18n] },
  })
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('VoucherHistory', () => {
  it('puts the shifts still to come on top of the page, apart from the rest', () => {
    const w = mountHistory({ withUpcoming: true })
    expect(w.findAll('h3').map((h) => h.text())).toEqual(['Still to come', 'So far'])

    const upcoming = w.findAll('[data-testid="voucher-history-upcoming"]')
    expect(upcoming).toHaveLength(1)
    expect(upcoming[0].text()).toContain('Grill stand')
    expect(upcoming[0].text()).toContain('17:00 – 20:00')
    expect(upcoming[0].text()).toContain('+2')
  })

  it('names a shift, a redemption and a correction, newest first', () => {
    const w = mountHistory({ withUpcoming: true })
    const texts = w
      .findAll('li')
      .filter((li) => li.attributes('data-testid') !== 'voucher-history-upcoming')
      .map((li) => li.text())

    expect(texts[0]).toContain('Used at Café counter')
    expect(texts[0]).toContain('by Pia Incharge')
    expect(texts[0]).toContain('−2')

    expect(texts[1]).toContain('Correction')
    expect(texts[1]).toContain('Helped with the set-up without a shift')
    expect(texts[1]).toContain('by Anna Berger')
    expect(texts[1]).toContain('+2')

    expect(texts[2]).toContain('Shift: Wristband check')
    expect(texts[2]).toContain('16:00 – 19:00')
  })

  it('says who took the vouchers "bei" and who corrected "von" in German', () => {
    i18n.global.locale.value = 'de'
    const w = mountHistory()
    const text = w.text()
    expect(text).toContain('Eingelöst bei Café counter')
    expect(text).toContain('bei Pia Incharge')
    expect(text).toContain('von Anna Berger')
    expect(text).toContain('Schicht: Wristband check')
  })

  it('is one list without headings in a dialog, and leaves the shifts to come out', () => {
    const w = mountHistory()
    expect(w.findAll('h3')).toHaveLength(0)
    expect(w.find('[data-testid="voucher-history-upcoming"]').exists()).toBe(false)
    expect(w.findAll('[data-testid="voucher-history-shift"]')).toHaveLength(1)
    expect(w.findAll('[data-testid="voucher-history-entry"]')).toHaveLength(2)
  })

  it('offers organisers a menu on corrections only', () => {
    expect(mountHistory().find('[data-testid="btn-voucher-correction-actions"]').exists()).toBe(
      false,
    )
    const w = mountHistory({ canEdit: true })
    expect(w.findAll('[data-testid="btn-voucher-correction-actions"]')).toHaveLength(1)
  })

  it('says when there is nothing yet', () => {
    const w = mountHistory({ account: { shifts: [], entries: [] }, withUpcoming: true })
    expect(w.text()).toBe('Nothing yet.')
  })
})
