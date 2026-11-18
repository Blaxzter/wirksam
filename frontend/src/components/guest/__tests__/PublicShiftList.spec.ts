// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import PublicShiftList from '@/components/guest/PublicShiftList.vue'

import type { PublicDay, PublicShift } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The shifts of a shared list by day. A shift whose task gives vouchers says
 * how many, in the organisers' preview too, and a shift without says nothing.
 */

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: null }) }))

function shift(overrides: Partial<PublicShift> = {}): PublicShift {
  return {
    id: 'shift-1',
    task_id: 'task-1',
    task_name: 'Bar',
    location: 'Hall',
    start_time: '10:00:00',
    end_time: '12:00:00',
    capacity: 2,
    free: 2,
    full: false,
    ...overrides,
  }
}

function mountList(shifts: PublicShift[], readonly = false) {
  const days: PublicDay[] = [{ date: '2026-11-20', shifts }]
  return mount(PublicShiftList, {
    props: { days, showNames: false, readonly },
    global: { plugins: [i18n] },
  })
}

const badges = (w: ReturnType<typeof mountList>) =>
  w.findAll('[data-testid="public-shift"]').map((row) => {
    const badge = row.find('[data-testid="public-shift-vouchers"]')
    return badge.exists() ? badge.text() : null
  })

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('PublicShiftList: vouchers', () => {
  it('shows the badge only above 0', () => {
    const w = mountList([
      shift({ vouchers: 1 }),
      shift({ id: 'shift-2', vouchers: 3 }),
      shift({ id: 'shift-3', vouchers: 0 }),
      shift({ id: 'shift-4' }),
    ])
    expect(badges(w)).toEqual(['1 voucher', '3 vouchers', null, null])
  })

  it('shows it in the organisers’ preview too', () => {
    const w = mountList([shift({ vouchers: 2 })], true)
    expect(badges(w)).toEqual(['2 vouchers'])
    expect(w.find('button').exists()).toBe(false)
  })

  it('reads in German', () => {
    i18n.global.locale.value = 'de'
    const w = mountList([shift({ vouchers: 1 }), shift({ id: 'shift-2', vouchers: 2 })])
    expect(badges(w)).toEqual(['1 Marke', '2 Marken'])
  })
})
