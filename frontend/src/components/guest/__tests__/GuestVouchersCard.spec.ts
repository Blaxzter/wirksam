// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import GuestVouchersCard from '@/components/guest/GuestVouchersCard.vue'

import type { GuestVoucherAccount, VoucherBalance } from '@/client/types.gen'
import type { VoucherPassSource } from '@/lib/vouchers'
import i18n from '@/locales/i18n'

/**
 * A guest's vouchers in one event on their manage page: the balance, the code
 * button (which does nothing while there is nothing to redeem), how codes
 * work, and the history without anyone's name. The code screen is the shared
 * `VoucherCodeDialog` (its own spec); here it is a stand-in that shows what it
 * was handed and plays what it reports.
 */

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: null }) }))

const CodeDialogStub = defineComponent({
  props: { open: Boolean, source: { type: Object, required: true } },
  emits: ['update:open', 'redeemed', 'gone'],
  template: `<div data-testid="code-dialog-stub" :data-open="open">
    <button data-testid="stub-redeemed" @click="$emit('redeemed')" />
    <button data-testid="stub-gone" @click="$emit('gone')" />
    <button data-testid="stub-close" @click="$emit('update:open', false)" />
  </div>`,
})

function summary(overrides: Partial<VoucherBalance> = {}): VoucherBalance {
  return {
    user_id: 'guest-1',
    earned: 4,
    upcoming: 2,
    redeemed: 1,
    adjusted: 0,
    available: 3,
    ...overrides,
  }
}

function voucher(overrides: Partial<VoucherBalance> = {}): GuestVoucherAccount {
  return {
    event_id: 'event-1',
    event_name: 'Summer fair',
    account: {
      summary: summary(overrides),
      shifts: [
        {
          booking_id: 'booking-1',
          task_name: 'Bar',
          title: 'Bar',
          date: '2026-11-20',
          start_time: '10:00:00',
          end_time: '12:00:00',
          ends_at: '2026-11-20T11:00:00',
          vouchers: 2,
          completed: true,
        },
      ],
      entries: [
        {
          id: 'entry-1',
          kind: 'redemption',
          amount: -1,
          method: 'code',
          note: null,
          task_name: 'Food stand',
          actor_name: null,
          created_at: '2026-11-20T12:00:00',
          updated_at: '2026-11-20T12:00:00',
        },
      ],
    },
  }
}

const source: VoucherPassSource = {
  issue: vi.fn(),
  status: vi.fn(),
  goneMessage: 'gone',
}

function mountCard(props: { voucher?: GuestVoucherAccount; named?: boolean } = {}) {
  return mount(GuestVouchersCard, {
    props: { voucher: voucher(), source, ...props },
    global: {
      plugins: [i18n],
      stubs: { VoucherCodeDialog: CodeDialogStub },
    },
  })
}

const byTestId = (w: ReturnType<typeof mountCard>, id: string) => w.find(`[data-testid="${id}"]`)
const dialog = (w: ReturnType<typeof mountCard>) => byTestId(w, 'code-dialog-stub')

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('GuestVouchersCard', () => {
  it('shows the balance, the code button and how codes work', () => {
    const w = mountCard()
    expect(w.find('h2').text()).toBe('Your vouchers')
    expect(byTestId(w, 'voucher-available').text()).toBe('3')
    expect(byTestId(w, 'voucher-upcoming').text()).toContain('2')
    expect(byTestId(w, 'btn-guest-show-code').text()).toBe('Show code')
    expect(byTestId(w, 'btn-guest-show-code').attributes('aria-disabled')).toBeUndefined()
    expect(w.text()).toContain('Show the code at the stand. It works once, for two minutes.')
    expect(byTestId(w, 'guest-vouchers-empty').exists()).toBe(false)
  })

  it('opens the code screen with the guest’s own source of codes', async () => {
    const w = mountCard()
    expect(dialog(w).attributes('data-open')).toBe('false')
    await byTestId(w, 'btn-guest-show-code').trigger('click')
    expect(dialog(w).attributes('data-open')).toBe('true')
    expect(w.findComponent(CodeDialogStub).props('source')).toStrictEqual(source)
  })

  it('opens no code screen while there is nothing to redeem, and says why', async () => {
    const w = mountCard({ voucher: voucher({ earned: 0, redeemed: 0, available: 0 }) })
    const button = byTestId(w, 'btn-guest-show-code')
    expect(button.attributes('aria-disabled')).toBe('true')
    expect(button.attributes('disabled')).toBeUndefined()
    await button.trigger('click')
    expect(dialog(w).attributes('data-open')).toBe('false')
    expect(byTestId(w, 'guest-vouchers-empty').text()).toBe(
      'Once a shift with vouchers is over, you can redeem them here.',
    )
    expect(button.attributes('aria-describedby')).toBe(
      byTestId(w, 'guest-vouchers-empty').attributes('id'),
    )
  })

  it('says there are none left once everything earned was used', () => {
    const w = mountCard({ voucher: voucher({ earned: 2, redeemed: 2, available: 0 }) })
    expect(byTestId(w, 'guest-vouchers-empty').text()).toBe(
      'You have no vouchers to use right now.',
    )
  })

  it('lists the history without the name of whoever redeemed', () => {
    const w = mountCard()
    const history = byTestId(w, 'voucher-history')
    expect(history.text()).toContain('Shift: Bar')
    expect(history.text()).toContain('Used at Food stand')
    expect(history.text()).not.toContain('by ')
  })

  it('names the event only when the guest has vouchers in several', () => {
    const w = mountCard({ named: true })
    expect(w.find('h2').text()).toBe('Your vouchers for “Summer fair”')
  })

  it('tells the page when a code was used', async () => {
    const w = mountCard()
    await byTestId(w, 'stub-redeemed').trigger('click')
    expect(w.emitted('redeemed')).toHaveLength(1)
  })

  it('tells the page about a dead link only once the code screen is closed', async () => {
    const w = mountCard()
    await byTestId(w, 'btn-guest-show-code').trigger('click')
    await byTestId(w, 'stub-gone').trigger('click')
    expect(w.emitted('gone')).toBeUndefined()

    await byTestId(w, 'stub-close').trigger('click')
    expect(w.emitted('gone')).toHaveLength(1)

    // Closing it again after a fresh opening says nothing more.
    await byTestId(w, 'btn-guest-show-code').trigger('click')
    await byTestId(w, 'stub-close').trigger('click')
    expect(w.emitted('gone')).toHaveLength(1)
  })

  it('reads in German, with du', () => {
    i18n.global.locale.value = 'de'
    const w = mountCard({ named: true })
    expect(w.find('h2').text()).toBe('Deine Marken bei „Summer fair“')
    expect(byTestId(w, 'btn-guest-show-code').text()).toBe('Code zeigen')
    expect(w.text()).toContain('Zeig den Code am Stand. Er gilt zwei Minuten und nur einmal.')
  })
})
