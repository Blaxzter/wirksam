// @vitest-environment jsdom
import { RouterLinkStub, mount } from '@vue/test-utils'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import MyPlan from '@/components/dashboard/MyPlan.vue'

import type { DashboardShift } from '@/client'
import i18n from '@/locales/i18n'

/**
 * "Your plan": every booking day by day, the next one marked, shifts in other
 * events labelled, and a note when the feed held rows back.
 */

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))

const NOW = new Date(2026, 6, 18, 9, 0)

function shift(id: string, overrides: Partial<DashboardShift> = {}): DashboardShift {
  return {
    booking_id: `b-${id}`,
    shift_id: id,
    task_id: 't1',
    task_name: 'Cafétheke',
    event_id: 'e1',
    event_name: 'Sommerfest',
    title: 'Cafétheke 14:00-17:00',
    date: '2026-07-18',
    start_time: '14:00',
    end_time: '17:00',
    location: 'Foyer-Café',
    taken: 2,
    capacity: 3,
    ...overrides,
  }
}

function mountPlan(shifts: DashboardShift[], props: Record<string, unknown> = {}) {
  return mount(MyPlan, {
    props: {
      shifts,
      totalCount: shifts.length,
      minutes: 360,
      currentEventId: 'e1',
      now: NOW,
      ...props,
    },
    global: { plugins: [i18n], stubs: { RouterLink: RouterLinkStub } },
  })
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('MyPlan', () => {
  const plan = [
    shift('s1'),
    shift('s2', { date: '2026-07-19', title: 'Einlass 10:00-12:00', task_name: 'Einlass' }),
    shift('s3', { date: '2026-07-21', title: 'Abbau 08:00-12:00', task_name: 'Abbau' }),
  ]

  it('groups the shifts by day, with a word for today and tomorrow', () => {
    const headings = mountPlan(plan)
      .findAll('h3')
      .map((h) => h.text())
    expect(headings).toEqual(['Today · Sat, July 18', 'Tomorrow · Sun, July 19', 'Tue, July 21'])
  })

  it('marks only the first row as next', () => {
    const w = mountPlan(plan)
    const rows = w.findAll('[data-testid="plan-row"]')
    expect(rows).toHaveLength(3)
    expect(rows[0].find('[data-testid="plan-next-badge"]').text()).toBe('Up next')
    expect(rows[1].find('[data-testid="plan-next-badge"]').exists()).toBe(false)
    expect(rows[2].find('[data-testid="plan-next-badge"]').exists()).toBe(false)
  })

  it('names another event only on its own shifts', () => {
    const w = mountPlan([shift('s1'), shift('s2', { event_id: 'e2', event_name: 'Weinmarkt' })])
    const rows = w.findAll('[data-testid="plan-row"]')
    expect(rows[0].find('[data-testid="plan-row-event"]').exists()).toBe(false)
    expect(rows[1].find('[data-testid="plan-row-event"]').text()).toBe('Weinmarkt')
  })

  it('says how many more the feed held back', () => {
    expect(mountPlan(plan).find('[data-testid="plan-more"]').exists()).toBe(false)
    expect(mountPlan(plan, { totalCount: 5 }).find('[data-testid="plan-more"]').text()).toBe(
      'and 2 more',
    )
  })

  it('opens the shift a row names', async () => {
    const w = mountPlan(plan)
    await w.findAll('[data-testid="plan-row"]')[1].trigger('click')
    expect(w.emitted('select')).toEqual([['s2']])
  })

  it('says so for a shift without a set time', () => {
    const w = mountPlan([shift('s1', { start_time: null, end_time: null })])
    expect(w.find('[data-testid="plan-row"]').text()).toContain('No set time')
  })

  it('sums up shifts and hours, and links to every booking', () => {
    const w = mountPlan(plan, { totalCount: 4, minutes: 450 })
    expect(w.find('[data-testid="plan-summary"]').text().replace(/\s+/g, ' ')).toBe(
      '4 shifts · 7.5 h signed up',
    )
    const link = w
      .findAllComponents(RouterLinkStub)
      .find((c) => c.attributes('data-testid') === 'btn-all-bookings')!
    expect(link.props('to')).toEqual({ name: 'my-bookings' })
  })

  it('leaves the hours out when no shift has times', () => {
    const w = mountPlan(plan, { minutes: 0 })
    expect(w.find('[data-testid="plan-summary"]').text()).toBe('3 shifts')
  })
})
