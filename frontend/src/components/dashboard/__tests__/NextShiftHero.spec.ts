// @vitest-environment jsdom
import { RouterLinkStub, mount } from '@vue/test-utils'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import NextShiftHero from '@/components/dashboard/NextShiftHero.vue'

import type { DashboardShift } from '@/client'
import i18n from '@/locales/i18n'

/**
 * The next-shift card: the countdown chip from the page's clock, the facts
 * under the big time, the map button's conditions, the day strip, and the
 * empty state's offer.
 */

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))

/** Saturday, July 18th 2026, 11:45 local time. */
const NOW = new Date(2026, 6, 18, 11, 45)

function shift(overrides: Partial<DashboardShift> = {}): DashboardShift {
  return {
    booking_id: 'b1',
    shift_id: 's1',
    task_id: 't1',
    task_name: 'Cafétheke',
    event_id: 'e1',
    event_name: 'Sommerfest',
    title: 'Cafétheke 14:00-17:00',
    date: '2026-07-18',
    start_time: '14:00',
    end_time: '17:00',
    location: 'Foyer-Café',
    location_id: 'loc1',
    taken: 3,
    capacity: 4,
    ...overrides,
  }
}

function mountHero(props: Partial<InstanceType<typeof NextShiftHero>['$props']> = {}) {
  return mount(NextShiftHero, {
    props: {
      shift: shift(),
      now: NOW,
      openPlaces: 0,
      venueMapEventId: null,
      currentEventId: 'e1',
      ...props,
    },
    global: { plugins: [i18n], stubs: { RouterLink: RouterLinkStub } },
  })
}

const chip = (w: ReturnType<typeof mountHero>) =>
  w.find('[data-testid="next-shift-countdown"]').text()

beforeEach(() => {
  i18n.global.locale.value = 'en'
  // Only the clock: `formatRelativeDay` reads it, and the page hands the
  // same moment down as `now`.
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('NextShiftHero', () => {
  it('counts down to a shift later today', async () => {
    const w = mountHero()
    expect(chip(w)).toBe('in 2 h 15 min')

    await w.setProps({ now: new Date(2026, 6, 18, 12, 0) })
    expect(chip(w)).toBe('in 2 h')

    await w.setProps({ now: new Date(2026, 6, 18, 13, 20) })
    expect(chip(w)).toBe('in 40 min')
  })

  it('says the shift is happening while it runs, and drops the chip once it is over', async () => {
    const w = mountHero({ now: new Date(2026, 6, 18, 14, 30) })
    expect(chip(w)).toBe('happening now')

    await w.setProps({ now: new Date(2026, 6, 18, 17, 0) })
    expect(w.find('[data-testid="next-shift-countdown"]').exists()).toBe(false)
  })

  it('names the day for a shift on another day', () => {
    const w = mountHero({ shift: shift({ date: '2026-07-19' }) })
    expect(chip(w)).toBe('tomorrow')
    expect(w.text()).toContain('Tomorrow, Sunday, July 19')
  })

  it('leads with the times, then the date, the place and who else is on it', () => {
    const w = mountHero()
    expect(w.text()).toContain('14:00 – 17:00')
    expect(w.text()).toContain('Today, Saturday, July 18')
    expect(w.text()).toContain('Foyer-Café')
    expect(w.text()).toContain('with 2 other people')
  })

  it('leaves out a job line that would repeat a generated title', () => {
    const w = mountHero()
    expect(w.text().split('Cafétheke').length - 1).toBe(1)
    expect(w.text()).not.toContain('14:00-17:00')
  })

  it('names the job under a title written by hand', () => {
    const w = mountHero({ shift: shift({ title: 'Welcome desk, early', task_name: 'Empfang' }) })
    expect(w.text()).toContain('Welcome desk, early')
    expect(w.text()).toContain('Empfang')
  })

  it('says "on your own" when nobody else is booked', () => {
    const w = mountHero({ shift: shift({ taken: 1 }) })
    expect(w.text()).toContain('on your own')
  })

  it('offers the map only for a place on the selected event’s plan', () => {
    expect(mountHero().find('[data-testid="btn-next-shift-map"]').exists()).toBe(false)
    expect(
      mountHero({ venueMapEventId: 'e2' }).find('[data-testid="btn-next-shift-map"]').exists(),
    ).toBe(false)
    expect(
      mountHero({ venueMapEventId: 'e1', shift: shift({ location_id: null }) })
        .find('[data-testid="btn-next-shift-map"]')
        .exists(),
    ).toBe(false)

    const w = mountHero({ venueMapEventId: 'e1' })
    const link = w
      .findAllComponents(RouterLinkStub)
      .find((c) => c.attributes('data-testid') === 'btn-next-shift-map')!
    expect(link.props('to')).toEqual({
      name: 'event-map',
      params: { eventId: 'e1' },
      query: { location: 'loc1' },
    })
    expect(link.text()).toContain('On the map')
  })

  it('draws the day strip only for a shift with both times', () => {
    expect(mountHero().find('[data-testid="next-shift-day-strip"]').exists()).toBe(true)
    expect(
      mountHero({ shift: shift({ end_time: null }) })
        .find('[data-testid="next-shift-day-strip"]')
        .exists(),
    ).toBe(false)
  })

  it('marks now on the strip only on the day of the shift', () => {
    expect(mountHero().find('[data-testid="next-shift-day-strip-now"]').exists()).toBe(true)
    expect(
      mountHero({ shift: shift({ date: '2026-07-19' }) })
        .find('[data-testid="next-shift-day-strip-now"]')
        .exists(),
    ).toBe(false)
  })

  it('shows the date as the headline of a shift without times', () => {
    const w = mountHero({ shift: shift({ start_time: null, end_time: null }) })
    expect(w.text()).toContain('Saturday, July 18')
    expect(chip(w)).toBe('today')
  })

  it('names the other event for a shift elsewhere', () => {
    expect(mountHero().text()).not.toContain('Sommerfest')
    expect(mountHero({ currentEventId: 'e9' }).text()).toContain('Sommerfest')
  })

  it('opens the shift it names', async () => {
    const w = mountHero()
    await w.find('[data-testid="btn-open-next-shift"]').trigger('click')
    expect(w.emitted('open')).toEqual([[shift()]])
  })

  describe('with nothing booked', () => {
    it('offers a shift while places are open', () => {
      const w = mountHero({ shift: null, openPlaces: 10 })
      expect(w.find('[data-testid="dashboard-next-shift"]').exists()).toBe(true)
      expect(w.text()).toContain('Nothing booked yet')
      expect(w.text()).toContain('10 places are still waiting for somebody.')
      const link = w
        .findAllComponents(RouterLinkStub)
        .find((c) => c.attributes('data-testid') === 'btn-find-shift')!
      expect(link.props('to')).toEqual({ name: 'tasks', query: { hide_full: 'true' } })
    })

    it('has no offer to make when nothing is open', () => {
      const w = mountHero({ shift: null, openPlaces: 0 })
      expect(w.find('[data-testid="dashboard-next-shift"]').exists()).toBe(true)
      expect(w.find('[data-testid="btn-find-shift"]').exists()).toBe(false)
      expect(w.find('[data-testid="next-shift-countdown"]').exists()).toBe(false)
    })

    it('lays itself out in one line on desktop only with the row to itself', () => {
      const card = (alone: boolean) =>
        mountHero({ shift: null, openPlaces: 10, alone })
          .find('[data-testid="dashboard-next-shift"]')
          .classes()
      expect(card(true)).toContain('@4xl:flex-row')
      // Beside the voucher card it stays stacked.
      expect(card(false)).not.toContain('@4xl:flex-row')
    })
  })
})
