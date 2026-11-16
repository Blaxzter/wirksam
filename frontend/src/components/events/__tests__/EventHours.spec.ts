// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import EventHours from '@/components/events/EventHours.vue'

import type { VolunteerHours } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The event's hours, one row per person. A shared list's guest account pools
 * the sign-ups of everyone who confirmed one address, so its user id comes
 * back once per name: each row is its own person, and opening it asks for
 * that person's hours by name.
 */

const api = vi.hoisted(() => ({ get: vi.fn(), delete: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: api.get, delete: api.delete }),
}))
vi.mock('@/composables/useDialog', () => ({
  useDialog: () => ({ confirmDestructive: vi.fn() }),
}))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))

const passthrough = { template: '<div><slot /></div>' }

function hours(overrides: Partial<VolunteerHours>): VolunteerHours {
  return {
    user_id: 'u',
    name: null,
    email: null,
    role: 'member',
    shift_count: 1,
    shift_minutes: 60,
    upcoming_shift_count: 0,
    upcoming_shift_minutes: 0,
    untimed_shift_count: 0,
    manual_minutes: 0,
    total_minutes: 60,
    ...overrides,
  }
}

const ROWS: VolunteerHours[] = [
  hours({ user_id: 'u-member', name: 'Mira Lindqvist' }),
  hours({ user_id: 'u-account', name: 'Maria Muster', role: null, is_guest: true }),
  hours({ user_id: 'u-account', name: 'Tom Muster', role: null, is_guest: true }),
]

function mountHours() {
  return mount(EventHours, {
    props: { eventId: 'e1', hours: ROWS, members: [] },
    global: {
      plugins: [i18n],
      stubs: {
        ResponsiveDialog: passthrough,
        ResponsiveDialogContent: passthrough,
        ResponsiveDialogHeader: passthrough,
        ResponsiveDialogTitle: passthrough,
        ResponsiveDialogDescription: passthrough,
        ResponsiveDialogBody: passthrough,
        ResponsiveDialogFooter: passthrough,
        HoursBreakdown: true,
        WorkLogFormDialog: true,
      },
    },
  })
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
  api.get.mockReset()
  api.get.mockResolvedValue({ data: { summary: ROWS[0], shifts: [], entries: [] } })
})

describe('EventHours: a guest account', () => {
  it('lists each name of a pooled account as its own row', () => {
    const rows = mountHours().findAll('[data-testid="event-hours-row"]')
    expect(rows.map((r) => r.find('span').text())).toEqual([
      'Mira Lindqvist',
      'Maria Muster',
      'Tom Muster',
    ])
    expect(rows[2]!.find('[data-testid="guest-tag"]').exists()).toBe(true)
  })

  it('asks for the hours of the name that was opened', async () => {
    const w = mountHours()
    await w.findAll('[data-testid="event-hours-row"]')[2]!.trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenLastCalledWith({
      url: '/events/e1/hours/u-account',
      query: { name: 'Tom Muster' },
    })
  })

  it('asks for a member by id alone', async () => {
    const w = mountHours()
    await w.findAll('[data-testid="event-hours-row"]')[0]!.trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenLastCalledWith({ url: '/events/e1/hours/u-member' })
  })
})
