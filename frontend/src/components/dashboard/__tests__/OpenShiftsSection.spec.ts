// @vitest-environment jsdom
import { RouterLinkStub, mount } from '@vue/test-utils'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import OpenShiftsSection from '@/components/dashboard/OpenShiftsSection.vue'

import type { DashboardOpenShift } from '@/client'
import i18n from '@/locales/i18n'

/**
 * The shifts still short of people: cards with a badge, a fill line and a
 * named sign-up button; four on a phone and all six on desktop, and one
 * browse link whose "(n more)" counts from whichever applies.
 */

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))

const NOW = new Date(2026, 6, 18, 9, 0)

function open(id: string, overrides: Partial<DashboardOpenShift> = {}): DashboardOpenShift {
  return {
    shift_id: id,
    task_id: 't1',
    task_name: 'Einlass',
    event_id: 'e1',
    event_name: 'Sommerfest',
    title: 'Einlass 14:00-17:00',
    date: '2026-07-18',
    start_time: '14:00',
    end_time: '17:00',
    location: 'Haupttor',
    taken: 1,
    capacity: 3,
    places_left: 2,
    ...overrides,
  }
}

function mountSection(shifts: DashboardOpenShift[], props: Record<string, unknown> = {}) {
  return mount(OpenShiftsSection, {
    props: {
      shifts,
      totalCount: shifts.length,
      openPlaces: shifts.reduce((n, s) => n + s.places_left, 0),
      now: NOW,
      showEventName: false,
      ...props,
    },
    global: { plugins: [i18n], stubs: { RouterLink: RouterLinkStub } },
  })
}

const six = ['a', 'b', 'c', 'd', 'e', 'f'].map((id) => open(id))

beforeEach(() => {
  i18n.global.locale.value = 'en'
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('OpenShiftsSection', () => {
  it('renders every card and hides the fifth and sixth below desktop', () => {
    const cards = mountSection(six).findAll('[data-testid="open-shift-card"]')
    expect(cards).toHaveLength(6)
    expect(cards.map((c) => c.classes().includes('@max-4xl:hidden'))).toEqual([
      false,
      false,
      false,
      false,
      true,
      true,
    ])
  })

  it('has one browse link that counts from four on a phone and from six on desktop', () => {
    const w = mountSection(six, { totalCount: 10 })
    const links = w.findAll('[data-testid="btn-browse-open-shifts"]')
    expect(links).toHaveLength(1)
    expect(w.find('[data-testid="open-shifts-more-mobile"]').text()).toBe('(6 more)')
    expect(w.find('[data-testid="open-shifts-more-desktop"]').text()).toBe('(4 more)')
    const to = w
      .findAllComponents(RouterLinkStub)
      .find((c) => c.attributes('data-testid') === 'btn-browse-open-shifts')!
      .props('to')
    expect(to).toEqual({ name: 'tasks', query: { hide_full: 'true' } })
  })

  it('counts nothing more when every shift is on screen', () => {
    const w = mountSection(six.slice(0, 3))
    expect(w.find('[data-testid="open-shifts-more-mobile"]').exists()).toBe(false)
    expect(w.find('[data-testid="open-shifts-more-desktop"]').exists()).toBe(false)
  })

  it('marks a shift nobody has taken, and says how many places the others have left', () => {
    const w = mountSection([open('a', { taken: 0, places_left: 3 }), open('b')])
    const badges = w.findAll('[data-testid="open-shift-badge"]')
    expect(badges[0].text()).toBe('Nobody yet')
    expect(badges[1].text()).toBe('2 places left')
  })

  it('says how full a shift is in words, not only with the bar', () => {
    expect(
      mountSection([open('a')])
        .find('[data-testid="open-shift-card"]')
        .text(),
    ).toContain('1 of 3 filled')
  })

  it('names the shift in the sign-up button’s label', () => {
    const w = mountSection([
      open('a'),
      open('b', { start_time: null, end_time: null, date: '2026-07-22' }),
    ])
    const buttons = w.findAll('[data-testid="btn-open-shift-signup"]')
    expect(buttons[0].text()).toBe('Sign up')
    expect(buttons[0].attributes('aria-label')).toBe('Sign up for Einlass, today 14:00 – 17:00')
    expect(buttons[1].attributes('aria-label')).toBe('Sign up for Einlass, Wed, Jul 22')
  })

  it('opens the shift a card names', async () => {
    const w = mountSection([open('a'), open('b')])
    await w.findAll('[data-testid="btn-open-shift-signup"]')[1].trigger('click')
    expect(w.emitted('select')).toEqual([['b']])
  })

  it('names the event only when the cards come from several', () => {
    expect(
      mountSection([open('a')])
        .find('[data-testid="open-shift-event"]')
        .exists(),
    ).toBe(false)
    expect(
      mountSection([open('a')], { showEventName: true })
        .find('[data-testid="open-shift-event"]')
        .text(),
    ).toBe('Sommerfest')
  })

  it('says everything is covered when nothing is open', () => {
    const w = mountSection([], { openPlaces: 0 })
    expect(w.find('[data-testid="open-shift-card"]').exists()).toBe(false)
    expect(w.find('[data-testid="open-shifts-empty"]').text()).toContain('Everything is covered')
    expect(w.find('[data-testid="open-shifts-summary"]').text()).toBe('Every shift is covered')
  })

  it('sums up the open places', () => {
    const w = mountSection(six, { totalCount: 8, openPlaces: 14 })
    expect(w.find('[data-testid="open-shifts-summary"]').text().replace(/\s+/g, ' ')).toBe(
      '14 places open across 8 shifts',
    )
  })
})
