// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import EventHours from '@/components/events/EventHours.vue'
import ShiftBookingsTable from '@/components/tasks/ShiftBookingsTable.vue'
import ShiftRoster from '@/components/tasks/ShiftRoster.vue'

import type { ShiftBookingEntry, VolunteerHours } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * People who signed up through a shared list, where the app lists who is on
 * a shift or who worked how long: a "no account" tag, the list they came
 * through for those who run the task, and "Guest (deleted)" once their data
 * is gone. Never "former member": they never were one.
 */

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ profile: { id: 'u-org', time_format: 'h24' } }),
}))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: vi.fn(), delete: vi.fn() }),
}))
vi.mock('@/composables/useDialog', () => ({ useDialog: () => ({ confirmDestructive: vi.fn() }) }))

function booking(overrides: Partial<ShiftBookingEntry> = {}): ShiftBookingEntry {
  return {
    id: 'b1',
    user_id: 'u1',
    user_name: 'Mia Berger',
    user_email: null,
    created_at: '2026-11-02T10:00:00',
    ...overrides,
  }
}

const GUEST = booking({
  id: 'b-guest',
  user_id: 'u-guest',
  is_guest: true,
  user_email: 'mia@example.org',
  via_list_title: 'Elternchat 3b',
})
const ERASED = booking({ id: 'b-erased', user_id: 'u-erased', user_name: null, is_guest: true })
const MEMBER = booking({ id: 'b-member', user_id: 'u-member', user_name: 'Jonas Weber' })

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('ShiftRoster', () => {
  it.each([false, true])(
    'tags a guest and names the list they came through (phone: %s)',
    (compact) => {
      const w = mount(ShiftRoster, {
        props: { bookings: [GUEST, MEMBER], capacity: 3, compact },
        global: { plugins: [i18n] },
      })
      const [guest, member] = w.findAll('[data-testid="shift-roster-entry"]')

      expect(guest.get('[data-testid="guest-tag"]').text()).toBe('no account')
      expect(guest.text()).toContain('via “Elternchat 3b”')
      expect(member.find('[data-testid="guest-tag"]').exists()).toBe(false)
    },
  )

  it('calls a guest whose data is gone a deleted guest', () => {
    const w = mount(ShiftRoster, {
      props: { bookings: [ERASED], capacity: 2 },
      global: { plugins: [i18n] },
    })
    expect(w.get('[data-testid="shift-roster-entry"]').text()).toContain('Guest (deleted)')
  })
})

describe('ShiftBookingsTable', () => {
  it('tags guests and names a deleted one', () => {
    const w = mount(ShiftBookingsTable, {
      props: { bookings: [GUEST, ERASED, MEMBER] },
      global: { plugins: [i18n] },
    })
    const rows = w.findAll('tbody tr')

    expect(rows[0].find('[data-testid="guest-tag"]').exists()).toBe(true)
    expect(rows[1].text()).toContain('Guest (deleted)')
    expect(rows[2].find('[data-testid="guest-tag"]').exists()).toBe(false)
    expect(rows[2].text()).toContain('Jonas Weber')
  })
})

describe('EventHours', () => {
  function hours(overrides: Partial<VolunteerHours>): VolunteerHours {
    return {
      user_id: 'u',
      name: 'Someone',
      role: 'member',
      shift_count: 1,
      shift_minutes: 120,
      upcoming_shift_count: 0,
      upcoming_shift_minutes: 0,
      untimed_shift_count: 0,
      manual_minutes: 0,
      total_minutes: 120,
      ...overrides,
    }
  }

  it('tags guests instead of calling them former members', () => {
    const w = mount(EventHours, {
      props: {
        eventId: 'e1',
        members: [],
        hours: [
          hours({ user_id: 'g', name: null, role: null, is_guest: true }),
          hours({ user_id: 'f', name: 'Former', role: null }),
        ],
      },
      global: { plugins: [i18n], stubs: { WorkLogFormDialog: true, ResponsiveDialog: true } },
    })
    const [guest, former] = w.findAll('[data-testid="event-hours-row"]')

    expect(guest.text()).toContain('Guest (deleted)')
    expect(guest.find('[data-testid="guest-tag"]').exists()).toBe(true)
    expect(guest.text()).not.toContain(i18n.global.t('duties.hours.event.formerMember'))
    expect(former.text()).toContain(i18n.global.t('duties.hours.event.formerMember'))
  })
})
