// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import TaskQuickViewCard from '@/components/tasks/quick-view/TaskQuickViewCard.vue'
import WeekDayColumns from '@/components/tasks/quick-view/WeekDayColumns.vue'
import type { DayColumn } from '@/components/tasks/quick-view/WeekDayColumns.vue'

import type { FeedShiftEntry, FeedTaskItem } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The task card on the Tasks list: what its label says about booking, counted
 * over the whole task rather than the five days on screen, and the "next
 * shift" hint that moves the strip there when those days are empty.
 */

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: api.get }),
}))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ canManageEvent: () => false, profile: { time_format: 'h24' } }),
}))
vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))

function shift(date: string, overrides: Partial<FeedShiftEntry> = {}): FeedShiftEntry {
  return {
    id: `s-${date}`,
    date,
    start_time: '09:00:00',
    end_time: '11:00:00',
    max_bookings: 2,
    current_bookings: 0,
    ...overrides,
  }
}

function task(overrides: Partial<FeedTaskItem> = {}): FeedTaskItem {
  return {
    id: 't1',
    name: 'Cafétheke',
    start_date: '2026-07-01',
    end_date: '2026-07-31',
    status: 'published',
    event_id: 'e1',
    created_at: '2026-06-01T00:00:00',
    updated_at: '2026-06-01T00:00:00',
    slot_window_start: '2026-07-18',
    shifts: [],
    open_shifts: 0,
    next_shift_date: null,
    next_open_shift_date: null,
    ...overrides,
  }
}

function mountCard(item: FeedTaskItem, props: { hideFullShifts?: boolean } = {}) {
  return mount(TaskQuickViewCard, {
    props: { task: item, ...props },
    global: {
      plugins: [i18n],
      stubs: { WeekDayColumns: true, TeamJoinButton: true, HintTooltip: true },
    },
  })
}

const label = (w: ReturnType<typeof mountCard>) =>
  w.find('[data-testid="task-row-shifts-label"]').text()
const hint = (w: ReturnType<typeof mountCard>) => w.find('[data-testid="task-row-next-shift"]')
const shownDays = (w: ReturnType<typeof mountCard>) =>
  (w.findComponent(WeekDayColumns).props('days') as DayColumn[]).map((d) => d.dateStr)

beforeEach(() => {
  i18n.global.locale.value = 'en'
  api.get.mockReset()
})

describe('TaskQuickViewCard', () => {
  describe('the label', () => {
    it('counts the open shifts of the whole task, not of the days on screen', () => {
      const w = mountCard(task({ open_shifts: 3, next_shift_date: '2026-07-28' }))
      expect(label(w)).toBe('3 open shifts')
    })

    it('says one open shift in the singular', () => {
      const w = mountCard(task({ open_shifts: 1, next_shift_date: '2026-07-28' }))
      expect(label(w)).toBe('1 open shift')
    })

    it('says every shift is taken when shifts are coming but all are full', () => {
      const w = mountCard(task({ open_shifts: 0, next_shift_date: '2026-07-19' }))
      expect(label(w)).toBe('All shifts taken')
    })

    it('says nothing is coming up when no shift is still to come', () => {
      const w = mountCard(task())
      expect(label(w)).toBe('No shifts coming up')
    })
  })

  describe('the next-shift hint', () => {
    it('appears when the days on screen are empty and the next shift lies beyond', () => {
      const w = mountCard(
        task({ open_shifts: 1, next_shift_date: '2026-07-28', next_open_shift_date: '2026-07-28' }),
      )
      expect(hint(w).exists()).toBe(true)
      expect(hint(w).text()).toContain('Next shift: Tue, Jul 28')
    })

    it('tells a screen reader which task and day its button moves to', () => {
      const w = mountCard(
        task({ open_shifts: 1, next_shift_date: '2026-07-28', next_open_shift_date: '2026-07-28' }),
      )
      const ids = w.find('[data-testid="btn-task-row-jump"]').attributes('aria-describedby')
      const described = (ids ?? '')
        .split(' ')
        .map((id) => w.find(`[id="${id}"]`).text())
        .join(' ')
      expect(described).toBe('Cafétheke Next shift: Tue, Jul 28')
    })

    it('moves the strip to that day through the shift-window endpoint', async () => {
      api.get.mockResolvedValue({
        data: { shifts: [shift('2026-07-28')], start_date: '2026-07-28', days: 5 },
      })
      const w = mountCard(
        task({ open_shifts: 1, next_shift_date: '2026-07-28', next_open_shift_date: '2026-07-28' }),
      )
      expect(shownDays(w)[0]).toBe('2026-07-18')

      await w.find('[data-testid="btn-task-row-jump"]').trigger('click')
      await flushPromises()

      expect(api.get).toHaveBeenCalledWith({
        url: '/tasks/t1/shift-window',
        query: { start_date: '2026-07-28', days: 5 },
      })
      expect(shownDays(w)).toEqual([
        '2026-07-28',
        '2026-07-29',
        '2026-07-30',
        '2026-07-31',
        '2026-08-01',
      ])
      expect(hint(w).exists()).toBe(false)
      // The days before stay in reach: swiping back loads them.
      expect(w.findComponent(WeekDayColumns).props('hasMorePrevious')).toBe(true)
    })

    it('stays put when the request fails', async () => {
      api.get.mockRejectedValue(new Error('offline'))
      const w = mountCard(task({ open_shifts: 1, next_shift_date: '2026-07-28' }))

      await w.find('[data-testid="btn-task-row-jump"]').trigger('click')
      await flushPromises()

      expect(shownDays(w)[0]).toBe('2026-07-18')
      expect(hint(w).exists()).toBe(true)
    })

    it('is not shown when the days on screen have a shift', () => {
      const w = mountCard(
        task({
          shifts: [shift('2026-07-19', { current_bookings: 2 })],
          open_shifts: 1,
          next_shift_date: '2026-07-19',
          next_open_shift_date: '2026-07-28',
        }),
      )
      expect(hint(w).exists()).toBe(false)
    })

    it('with full shifts hidden, points at the next shift that has room', () => {
      const w = mountCard(
        task({
          shifts: [shift('2026-07-19', { current_bookings: 2 })],
          open_shifts: 1,
          next_shift_date: '2026-07-19',
          next_open_shift_date: '2026-07-28',
        }),
        { hideFullShifts: true },
      )
      expect(hint(w).text()).toContain('Next shift: Tue, Jul 28')
    })

    it('is not shown when nothing is coming', () => {
      const w = mountCard(task({ next_shift_date: '2026-07-19' }), { hideFullShifts: true })
      expect(hint(w).exists()).toBe(false)
    })
  })
})
