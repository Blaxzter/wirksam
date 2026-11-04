// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it } from 'vitest'

import ShiftRoster from '@/components/tasks/ShiftRoster.vue'

import type { ShiftBookingEntry } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * "Signed up" in the shift dialog. Whoever runs the task gets e-mail, phone and
 * notes from the server, and sees them as a table on a desktop and as call and
 * e-mail buttons on a phone. A volunteer gets names and dates only, and nobody
 * is offered a way to call themselves.
 */

const thisYear = new Date().getFullYear()

function entry(overrides: Partial<ShiftBookingEntry> = {}): ShiftBookingEntry {
  return {
    id: 'b-vroni',
    user_id: 'u-vroni',
    user_name: 'Vroni Hartmann',
    user_email: 'vroni.h@example.org',
    user_phone_number: '0170 123 45 67',
    notes: 'Komme mit dem Bus, eventuell 10 Minuten später.',
    created_at: `${thisYear}-07-02T10:00:00`,
    ...overrides,
  }
}

const vroni = () => entry()
const yuki = () =>
  entry({
    id: 'b-yuki',
    user_id: 'u-yuki',
    user_name: 'Yuki Tanabe',
    user_email: 'yuki.tanabe@example.org',
    user_phone_number: null,
    notes: null,
    created_at: `${thisYear}-06-30T10:00:00`,
  })

function mountRoster(props: Record<string, unknown> = {}) {
  return mount(ShiftRoster, {
    props: { bookings: [vroni(), yuki()], capacity: 3, ...props },
    global: { plugins: [i18n] },
  })
}

const rows = (w: ReturnType<typeof mountRoster>) => w.findAll('[data-testid="shift-roster-entry"]')

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('ShiftRoster on a desktop', () => {
  it('says how full the shift is and what is left', () => {
    const w = mountRoster()
    expect(w.find('h3').text()).toBe('Signed up')
    expect(w.find('[data-testid="shift-roster-count"]').text()).toBe('2 of 3, 1 place free')
    expect(w.find('[data-testid="shift-roster-free"]').text()).toContain('1 place free')
  })

  it('lists people as a table with their contact details and when they signed up', () => {
    const w = mountRoster()
    const headers = w.findAll('[role="columnheader"]').map((h) => h.text())
    expect(headers).toEqual(['Person', 'Contact', 'Signed up'])

    const [first, second] = rows(w)
    expect(first!.text()).toContain('Vroni Hartmann')
    expect(first!.text()).toContain('July 2')
    expect(first!.find('[data-testid="shift-roster-note"]').text()).toBe(
      'Komme mit dem Bus, eventuell 10 Minuten später.',
    )
    const phone = first!.find('[data-testid="shift-roster-phone"]')
    expect(phone.attributes('href')).toBe('tel:01701234567')
    expect(phone.text()).toBe('0170 123 45 67')
    expect(first!.find('[data-testid="shift-roster-email"]').attributes('href')).toBe(
      'mailto:vroni.h@example.org',
    )

    expect(second!.find('[data-testid="shift-roster-phone"]').exists()).toBe(false)
    expect(second!.text()).toContain('June 30')
  })

  it('leaves the contact column out when nobody in it can be reached', () => {
    const w = mountRoster({
      bookings: [
        entry({ user_email: null, user_phone_number: null, notes: null }),
        entry({
          id: 'b2',
          user_id: 'u2',
          user_name: 'Yuki',
          user_email: null,
          user_phone_number: null,
          notes: null,
        }),
      ],
    })
    const headers = w.findAll('[role="columnheader"]').map((h) => h.text())
    expect(headers).toEqual(['Person', 'Signed up'])
  })

  it('shows the year only for a booking from another year', () => {
    const w = mountRoster({ bookings: [entry({ created_at: `${thisYear - 1}-12-30T10:00:00` })] })
    expect(rows(w)[0]!.text()).toContain(`December 30, ${thisYear - 1}`)
  })
})

describe('ShiftRoster on a phone', () => {
  it('offers a call and an e-mail button per person, named for them', () => {
    const w = mountRoster({ compact: true })
    expect(w.find('[role="table"]').exists()).toBe(false)
    const [first, second] = rows(w)

    const call = first!.find('[data-testid="shift-roster-phone"]')
    expect(call.attributes('href')).toBe('tel:01701234567')
    expect(call.attributes('aria-label')).toBe('Call Vroni Hartmann')
    expect(first!.find('[data-testid="shift-roster-email"]').attributes('aria-label')).toBe(
      'Email Vroni Hartmann',
    )
    expect(first!.text()).toContain('signed up July 2')

    // E-mail but no number: say so rather than leave a gap.
    expect(second!.find('[data-testid="shift-roster-phone"]').exists()).toBe(false)
    expect(second!.text()).toContain('signed up June 30 · no number')
  })

  it('keeps the count short and says what is free in the list', () => {
    const w = mountRoster({ compact: true })
    expect(w.find('[data-testid="shift-roster-count"]').text()).toBe('2 of 3')
    expect(w.find('[data-testid="shift-roster-free"]').text()).toBe('1 place free')
  })

  it('reads out a number the dialler cannot use', () => {
    const w = mountRoster({
      compact: true,
      bookings: [entry({ user_phone_number: 'ask at the desk', notes: null })],
    })
    expect(rows(w)[0]!.find('[data-testid="shift-roster-phone"]').exists()).toBe(false)
    expect(rows(w)[0]!.text()).toContain('signed up July 2 · ask at the desk')
  })

  it('in German', () => {
    i18n.global.locale.value = 'de'
    const w = mountRoster({ compact: true })
    expect(w.find('h3').text()).toBe('Dabei')
    expect(w.find('[data-testid="shift-roster-count"]').text()).toBe('2 von 3')
    expect(rows(w)[0]!.text()).toContain('seit 2. Juli dabei')
    expect(rows(w)[1]!.text()).toContain('keine Nummer')
    expect(rows(w)[0]!.find('[data-testid="shift-roster-phone"]').attributes('aria-label')).toBe(
      'Vroni Hartmann anrufen',
    )
    expect(w.find('[data-testid="shift-roster-free"]').text()).toBe('1 Platz frei')
  })
})

describe('ShiftRoster, either layout', () => {
  it.each([true, false])(
    'marks your own row and offers no way to reach yourself (compact %s)',
    (compact) => {
      const w = mountRoster({ compact, myId: 'u-vroni' })
      const mine = rows(w)[0]!
      expect(mine.text()).toContain('You')
      expect(mine.find('[data-testid="shift-roster-phone"]').exists()).toBe(false)
      expect(mine.find('[data-testid="shift-roster-email"]').exists()).toBe(false)
      expect(mine.text()).not.toContain('no number')
    },
  )

  it.each([true, false])(
    'says nothing of free places once the shift is over (compact %s)',
    (compact) => {
      const w = mountRoster({ compact, hideFree: true })
      expect(w.find('[data-testid="shift-roster-free"]').exists()).toBe(false)
      expect(w.find('[data-testid="shift-roster-count"]').text()).toBe('2 of 3')
    },
  )

  it('says nobody signed up for an empty shift that is over', () => {
    const w = mountRoster({ bookings: [], hideFree: true })
    expect(w.find('[data-testid="shift-roster-nobody"]').text()).toBe('Nobody signed up.')
    expect(rows(w)).toHaveLength(0)
  })

  it('shows only the free places, without column headers, before anyone signed up', () => {
    const w = mountRoster({ bookings: [], capacity: 2 })
    expect(w.findAll('[role="columnheader"]')).toHaveLength(0)
    expect(w.find('[data-testid="shift-roster-free"]').text()).toContain('2 places free')
  })

  it('says it is loading instead of listing', () => {
    const w = mountRoster({ loading: true })
    expect(w.text()).toContain('Loading')
    expect(rows(w)).toHaveLength(0)
  })

  it('keeps the shift\'s own count while the list loads, not "0 of 3"', () => {
    const w = mountRoster({ bookings: [], loading: true, booked: 3 })
    expect(w.find('[data-testid="shift-roster-count"]').text()).toBe('3 of 3')
    expect(w.find('[data-testid="shift-roster-count"] span span').classes()).toContain('bg-primary')
    // Once the list is there, it counts.
    const loaded = mountRoster({ booked: 3 })
    expect(loaded.find('[data-testid="shift-roster-count"]').text()).toBe('2 of 3, 1 place free')
  })

  it('fills the bar by how many signed up, green once full', () => {
    const half = mountRoster({ bookings: [vroni()], capacity: 2 })
    const bar = half.find('[data-testid="shift-roster-count"] span span')
    expect(bar.attributes('style')).toContain('width: 50%')
    expect(bar.classes()).toContain('bg-staff-partial')

    const full = mountRoster({ capacity: 2 })
    expect(full.find('[data-testid="shift-roster-count"] span span').classes()).toContain(
      'bg-primary',
    )
  })
})
