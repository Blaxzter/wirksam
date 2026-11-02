// @vitest-environment jsdom
import { RouterLinkStub, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import CommittedTile from '@/components/dashboard/CommittedTile.vue'
import DashboardHeader from '@/components/dashboard/DashboardHeader.vue'

import i18n from '@/locales/i18n'

/**
 * The page header (greeting, date, day of the event, "Find a shift") and the
 * phone's "Signed up" tile, the two small pieces around the next shift.
 */

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))

function mountHeader(props: Record<string, unknown> = {}) {
  return mount(DashboardHeader, {
    props: {
      now: new Date(2026, 6, 18, 9, 0),
      name: 'Alex',
      eventDay: { day: 2, total: 3 },
      showFindShift: true,
      ...props,
    },
    global: { plugins: [i18n], stubs: { RouterLink: RouterLinkStub } },
  })
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('DashboardHeader', () => {
  it('greets by name for the time of day, over the long date', () => {
    const w = mountHeader()
    expect(w.find('[data-testid="page-heading"]').text()).toBe('Good morning, Alex')
    expect(w.text()).toContain('Saturday, July 18')
  })

  it('greets without a name when there is none', () => {
    const w = mountHeader({ name: null, now: new Date(2026, 6, 18, 20, 0) })
    expect(w.find('[data-testid="page-heading"]').text()).toBe('Good evening')
  })

  it('greets in German', () => {
    i18n.global.locale.value = 'de'
    const w = mountHeader({ now: new Date(2026, 6, 18, 14, 0) })
    expect(w.find('[data-testid="page-heading"]').text()).toBe('Guten Tag, Alex')
    expect(w.find('[data-testid="dashboard-event-day"]').text()).toBe('Tag 2 von 3')
  })

  it('shows the day of the event only during it', () => {
    expect(mountHeader().find('[data-testid="dashboard-event-day"]').text()).toBe('Day 2 of 3')
    expect(
      mountHeader({ eventDay: null }).find('[data-testid="dashboard-event-day"]').exists(),
    ).toBe(false)
  })

  it('offers "Find a shift" unless the event is over', () => {
    const link = mountHeader()
      .findAllComponents(RouterLinkStub)
      .find((c) => c.attributes('data-testid') === 'btn-header-find-shift')!
    expect(link.props('to')).toEqual({ name: 'tasks', query: { hide_full: 'true' } })
    expect(
      mountHeader({ showFindShift: false }).find('[data-testid="btn-header-find-shift"]').exists(),
    ).toBe(false)
  })
})

describe('CommittedTile', () => {
  const mountTile = (minutes: number, shiftCount: number) =>
    mount(CommittedTile, { props: { minutes, shiftCount }, global: { plugins: [i18n] } })

  it('sums up hours and shifts', () => {
    const w = mountTile(480, 3)
    expect(w.text()).toContain('8 h')
    expect(w.text()).toContain('in 3 shifts')
  })

  it('counts shifts when none has times', () => {
    const w = mountTile(0, 2)
    expect(w.text()).toContain('2 shifts')
    expect(w.text()).not.toContain(' h')
  })

  it('asks the page to scroll to the plan', async () => {
    const w = mountTile(60, 1)
    await w.find('[data-testid="btn-to-plan"]').trigger('click')
    expect(w.emitted('toPlan')).toHaveLength(1)
  })
})
