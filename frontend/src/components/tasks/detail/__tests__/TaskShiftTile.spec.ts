// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import TaskShiftTile from '@/components/tasks/detail/TaskShiftTile.vue'

import type { ShiftRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * A shift on the task page: the badge says how full it is in words, the tile
 * is one button whose meaning the page decides, and the delete or details
 * button sits beside it, never inside it.
 */

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))

function shift(overrides: Partial<ShiftRead> = {}): ShiftRead {
  return {
    id: 's1',
    task_id: 't1',
    title: 'Cafétheke 14:00-17:00',
    date: '2026-07-18',
    start_time: '14:00:00',
    end_time: '17:00:00',
    max_bookings: 3,
    current_bookings: 1,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
    ...overrides,
  } as ShiftRead
}

function mountTile(props: Record<string, unknown> = {}) {
  return mount(TaskShiftTile, {
    props: { shift: shift(), ...props },
    global: { plugins: [i18n] },
  })
}

const main = (w: ReturnType<typeof mountTile>) => w.find('button[aria-label]')

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('TaskShiftTile', () => {
  it('shows the time, how many are on it and how many places are left', () => {
    const w = mountTile()
    expect(w.attributes('data-testid')).toBe('shift-card-s1')
    expect(w.text()).toContain('14:00 – 17:00')
    expect(w.text()).toContain('1 of 3')
    expect(w.text()).toContain('2 free')
  })

  it('says "Full" and "Nobody yet" for the two ends', () => {
    expect(mountTile({ shift: shift({ current_bookings: 3 }) }).text()).toContain('Full')
    expect(mountTile({ shift: shift({ current_bookings: 0 }) }).text()).toContain('Nobody yet')
  })

  it('puts the count in the badge on a phone', () => {
    const w = mountTile({ compact: true })
    expect(w.text()).toContain('1 of 3')
    expect(w.text()).not.toContain('2 free')
  })

  it('falls back to the title for a shift without times', () => {
    const w = mountTile({ shift: shift({ start_time: null, end_time: null, title: 'All day' }) })
    expect(w.text()).toContain('All day')
  })

  it('reports a tap on the tile', async () => {
    const w = mountTile()
    await main(w).trigger('click')
    expect(w.emitted('select')).toHaveLength(1)
  })

  it('names the tile with its time, count and whether it is yours', () => {
    expect(main(mountTile({ mine: true })).attributes('aria-label')).toBe(
      '14:00 – 17:00, 1 of 3, Booked',
    )
  })

  it("marks a full shift a volunteer isn't on as not usable, but not for whoever runs the task", () => {
    const full = shift({ current_bookings: 3 })
    expect(main(mountTile({ shift: full })).attributes('aria-disabled')).toBe('true')
    expect(
      main(mountTile({ shift: full, manage: true })).attributes('aria-disabled'),
    ).toBeUndefined()
  })

  it('says why a shift that is over cannot be booked', () => {
    const w = mountTile({ note: 'This shift is over.' })
    expect(main(w).attributes('aria-label')).toContain('This shift is over.')
  })

  it('marks a shift that clashes with one of yours, or is kept for a team', () => {
    expect(
      mountTile({ shift: shift({ collides_with_my_booking: true }) })
        .find('[data-testid="shift-clash-s1"]')
        .exists(),
    ).toBe(true)
    const locked = mountTile({ shift: shift({ locked_by_team: true, team_name: 'First aid' }) })
    expect(locked.find('[data-testid="shift-team-locked-s1"]').exists()).toBe(true)
    expect(main(locked).attributes('aria-label')).toContain('First aid')
  })

  it('offers delete to whoever may change the shifts, without tapping the tile', async () => {
    for (const compact of [false, true]) {
      const w = mountTile({ manage: true, canDelete: true, compact })
      const del = w.find('button[aria-label="Delete Duty Shift"]')
      expect(del.exists()).toBe(true)
      await del.trigger('click')
      expect(w.emitted('delete')).toHaveLength(1)
      expect(w.emitted('select')).toBeUndefined()
    }
  })

  it('offers the details to a volunteer, whose tap books, but not to whoever runs the task', async () => {
    for (const compact of [false, true]) {
      const w = mountTile({ compact })
      const details = w.find('button[aria-label="View details"]')
      expect(details.exists()).toBe(true)
      await details.trigger('click')
      expect(w.emitted('details')).toHaveLength(1)

      const managed = mountTile({ compact, manage: true })
      expect(managed.find('button[aria-label="View details"]').exists()).toBe(false)
    }
  })
})
