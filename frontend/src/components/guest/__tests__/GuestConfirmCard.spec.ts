// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it } from 'vitest'

import GuestConfirmCard from '@/components/guest/GuestConfirmCard.vue'

import type { GuestSignupManage, GuestVoucherAccount } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * "Ist das deine Adresse?": the card a guest's page shows when it was opened
 * from a mail, with "Ja, das bin ich" and "Das war ich nicht". Opened from the
 * link the sign-up page showed, it only says where confirming happens, and on
 * a confirmed address, or without one, nothing.
 */

function view(overrides: Partial<GuestSignupManage> = {}): GuestSignupManage {
  return {
    name: 'Anna Berg',
    email: 'anna@example.org',
    event: {
      name: 'Summer fair',
      start_date: '2026-11-20',
      end_date: '2026-11-21',
      timezone: 'Europe/Berlin',
    },
    bookings: [],
    can_set_reminders: true,
    confirmed: false,
    can_confirm: true,
    can_reject: true,
    reject_suppresses: true,
    has_phone: false,
    retention_days: 30,
    erase_on: '2026-12-22',
    vouchers: [],
    ...overrides,
  }
}

const VOUCHERS: GuestVoucherAccount = {
  event_id: 'event-1',
  event_name: 'Summer fair',
  account: {
    summary: {
      user_id: 'guest-1',
      earned: 2,
      upcoming: 0,
      redeemed: 0,
      adjusted: 0,
      available: 2,
    },
    shifts: [],
    entries: [],
  },
}

function mountCard(props: { view: GuestSignupManage; busy?: boolean; confirming?: boolean }) {
  return mount(GuestConfirmCard, { props, global: { plugins: [i18n] } })
}

const byTestId = (w: ReturnType<typeof mountCard>, id: string) => w.find(`[data-testid="${id}"]`)

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('GuestConfirmCard', () => {
  it('asks whether the address is theirs, and says each sign-up keeps its name', () => {
    const w = mountCard({ view: view() })
    expect(w.find('h2').text()).toBe('Is this your address?')
    expect(byTestId(w, 'guest-confirm-text').text()).toBe(
      'Confirm anna@example.org. Every sign-up you confirm with this address for “Summer fair” is then shown on this page. Each sign-up keeps its own name.',
    )
    expect(byTestId(w, 'btn-guest-confirm').text()).toBe("Yes, that's me")
    expect(byTestId(w, 'btn-guest-not-me').text()).toBe("That wasn't me")
  })

  it('says the vouchers are added up once there are any', () => {
    const w = mountCard({ view: view({ vouchers: [VOUCHERS] }) })
    expect(byTestId(w, 'guest-confirm-text').text()).toContain('and your vouchers are added up')
  })

  it('tells the page which button was pressed', async () => {
    const w = mountCard({ view: view() })
    await byTestId(w, 'btn-guest-confirm').trigger('click')
    await byTestId(w, 'btn-guest-not-me').trigger('click')
    expect(w.emitted('confirm')).toHaveLength(1)
    expect(w.emitted('notMe')).toHaveLength(1)
  })

  it('starts nothing while an action runs, and keeps both buttons focusable', async () => {
    const w = mountCard({ view: view(), busy: true, confirming: true })
    const yes = byTestId(w, 'btn-guest-confirm')
    expect(yes.attributes('aria-disabled')).toBe('true')
    expect(yes.attributes('disabled')).toBeUndefined()
    expect(yes.find('.animate-spin').exists()).toBe(true)
    await yes.trigger('click')
    await byTestId(w, 'btn-guest-not-me').trigger('click')
    expect(w.emitted('confirm')).toBeUndefined()
    expect(w.emitted('notMe')).toBeUndefined()
  })

  it('offers no "Das war ich nicht" where it may not be said', () => {
    const w = mountCard({ view: view({ can_reject: false }) })
    expect(byTestId(w, 'btn-guest-not-me').exists()).toBe(false)
  })

  it('only says where confirming happens on the link the sign-up page showed', () => {
    const w = mountCard({ view: view({ can_confirm: false, can_reject: false }) })
    expect(byTestId(w, 'guest-confirm').exists()).toBe(false)
    expect(byTestId(w, 'guest-confirm-from-mail').text()).toBe(
      'If we sent you an email, you can confirm your address through the link in it.',
    )
  })

  it('shows nothing on a confirmed address, nor without an address', () => {
    const confirmed = mountCard({
      view: view({ can_confirm: false, can_reject: false, confirmed: true }),
    })
    expect(confirmed.html()).not.toContain('data-testid')

    const noAddress = mountCard({ view: view({ can_confirm: false, email: null }) })
    expect(noAddress.html()).not.toContain('data-testid')
  })

  it('reads in German, with du', () => {
    i18n.global.locale.value = 'de'
    const w = mountCard({ view: view() })
    expect(w.find('h2').text()).toBe('Ist das deine Adresse?')
    expect(byTestId(w, 'btn-guest-confirm').text()).toBe('Ja, das bin ich')
    expect(byTestId(w, 'guest-confirm-text').text()).toContain(
      'Jede Eintragung behält ihren Namen.',
    )
  })
})
