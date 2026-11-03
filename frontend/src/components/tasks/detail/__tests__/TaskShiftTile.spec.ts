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

  it('asks for people in amber only while a shift can still take them', () => {
    const badge = (w: ReturnType<typeof mountTile>) =>
      w.findAll('span').find((s) => s.text() === 'Nobody yet')!
    const empty = shift({ current_bookings: 0 })
    expect(badge(mountTile({ shift: empty })).classes()).toContain('text-warning')
    const over = badge(mountTile({ shift: empty, note: 'This shift is over.' }))
    expect(over.classes()).not.toContain('text-warning')
    expect(over.classes()).toContain('text-muted-foreground')
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

  describe('who is on it', () => {
    const booked = (...names: (string | null)[]) =>
      shift({
        current_bookings: names.length,
        max_bookings: Math.max(3, names.length),
        bookers: names.map((name, i) => ({ user_id: `u${i}`, name })),
      })
    const who = (w: ReturnType<typeof mountTile>) => w.find('[data-testid="shift-who-s1"]')

    it('adds their first names after the count, as the roster names them', () => {
      const w = mountTile({ shift: booked('Tomas Neruda', 'Adaeze Okafor') })
      expect(who(w).text()).toBe('2 of 3 · Tomas, Adaeze')
      expect(main(w).attributes('aria-label')).toBe('14:00 – 17:00, 2 of 3, Tomas, Adaeze')
    })

    it('writes out three and counts the rest, which stays in view', () => {
      const w = mountTile({ shift: booked('Vroni A', 'Yuki B', 'Ben C', 'Sina D', 'Jonas E') })
      expect(who(w).text()).toBe('5 of 5 · Vroni, Yuki, Ben +2')
      const more = who(w).findAll('span').at(-1)!
      expect(more.text()).toBe('+2')
      expect(more.classes()).toContain('shrink-0')
      expect(main(w).attributes('aria-label')).toContain('Vroni, Yuki, Ben and 2 more')
    })

    it('says a shift nobody is on yet is still free, unless it is over', () => {
      expect(who(mountTile({ shift: booked() })).text()).toBe('0 of 3 · still free')
      const over = mountTile({ shift: booked(), note: 'This shift is over.' })
      expect(who(over).text()).toBe('0 of 3')
    })

    it('counts someone without a name without writing them out', () => {
      const w = mountTile({ shift: booked(null, 'Tomas Neruda') })
      expect(who(w).text()).toBe('2 of 3 · Tomas +1')
      const nameless = mountTile({ shift: booked(null) })
      expect(who(nameless).text()).toBe('1 of 3 · +1')
      expect(main(nameless).attributes('aria-label')).toBe('14:00 – 17:00, 1 of 3')
    })

    it('puts two names on a line of their own under the badge on a phone', () => {
      const w = mountTile({ shift: booked('Vroni A', 'Yuki B', 'Ben C'), compact: true })
      expect(who(w).text()).toBe('Vroni, Yuki +1')
      expect(who(w).find('span').classes()).toContain('truncate')
      expect(who(mountTile({ shift: booked(), compact: true })).exists()).toBe(false)
    })

    it('shows the count alone when the page did not ask for names', () => {
      const w = mountTile()
      expect(who(w).text()).toBe('1 of 3')
      expect(who(mountTile({ compact: true })).exists()).toBe(false)
    })

    it('says it in German too', () => {
      i18n.global.locale.value = 'de'
      expect(who(mountTile({ shift: booked() })).text()).toBe('0 von 3 · noch frei')
      const w = mountTile({ shift: booked('Vroni A', 'Yuki B', 'Ben C', 'Sina D') })
      expect(main(w).attributes('aria-label')).toContain('Vroni, Yuki, Ben und 1 weitere Person')
    })
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
