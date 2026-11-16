import { describe, expect, it } from 'vitest'

import {
  MAX_TASKS,
  type PickedTask,
  type WizardShift,
  addTask,
  autoTitle,
  byStart,
  dayState,
  includedShifts,
  lastShift,
  maxPerOptions,
  onlyDays,
  pruneExcluded,
  setShiftIncluded,
  shiftsByDay,
  step1Blockers,
  taskProblem,
  toggleDay,
} from '@/lib/shared-list-selection'
import i18n from '@/locales/i18n'

/**
 * Correction (a): a list is its tasks minus ONE set of excluded shifts, and a
 * day's checkbox is only ever read off that set. Every rule the wizard leans
 * on is pinned here, so a day and its shifts can never disagree again.
 */

function shift(
  id: string,
  taskId: string,
  date: string,
  start: string | null = '10:00:00',
  free = 1,
): WizardShift {
  return {
    id,
    task_id: taskId,
    date,
    start_time: start,
    end_time: start ? '12:00:00' : null,
    capacity: 2,
    free,
  }
}

function task(id: string, name = id, unavailable: PickedTask['unavailable'] = null): PickedTask {
  return { id, name, unavailable }
}

// Kitchen on Saturday (two shifts) and Sunday; Bar on Sunday only.
const SAT = '2026-12-05'
const SUN = '2026-12-06'
const k1 = shift('k1', 'kitchen', SAT, '10:00:00')
const k2 = shift('k2', 'kitchen', SAT, '14:00:00')
const k3 = shift('k3', 'kitchen', SUN, '10:00:00')
const b1 = shift('b1', 'bar', SUN, '18:00:00')
const ALL = [b1, k3, k2, k1]

const ids = (shifts: readonly WizardShift[]) => shifts.map((s) => s.id)

describe('byStart', () => {
  it('orders by day, then start with untimed first, then id', () => {
    const untimed = shift('u', 'kitchen', SAT, null)
    const twin = shift('a', 'bar', SAT, '10:00:00')
    expect(ids([k3, k2, k1, untimed, twin].sort(byStart))).toEqual(['u', 'a', 'k1', 'k2', 'k3'])
    expect(byStart(k1, k1)).toBe(0)
  })
})

describe('shiftsByDay', () => {
  it('groups the selected tasks’ shifts by date, days and shifts in order', () => {
    const days = shiftsByDay(ALL, ['kitchen', 'bar'])
    expect([...days.keys()]).toEqual([SAT, SUN])
    expect(ids(days.get(SAT)!)).toEqual(['k1', 'k2'])
    expect(ids(days.get(SUN)!)).toEqual(['k3', 'b1'])
  })

  it('leaves out the shifts of tasks that are not selected', () => {
    const days = shiftsByDay(ALL, ['bar'])
    expect([...days.keys()]).toEqual([SUN])
    expect(ids(days.get(SUN)!)).toEqual(['b1'])
  })
})

describe('dayState', () => {
  const day = [k1, k2]

  it('is checked with every shift in', () => {
    expect(dayState(day, new Set())).toBe('checked')
  })

  it('is indeterminate with some in', () => {
    expect(dayState(day, new Set(['k1']))).toBe('indeterminate')
  })

  it('is unchecked with none in', () => {
    expect(dayState(day, new Set(['k1', 'k2']))).toBe('unchecked')
  })

  it('is empty for a day without shifts', () => {
    expect(dayState([], new Set())).toBe('empty')
  })
})

describe('toggleDay', () => {
  const day = [k1, k2]

  it('leaves out every shift of a checked day', () => {
    const next = toggleDay(day, new Set(['b1']))
    expect([...next].sort()).toEqual(['b1', 'k1', 'k2'])
    expect(dayState(day, next)).toBe('unchecked')
  })

  it('takes every shift of an unchecked day back in', () => {
    const next = toggleDay(day, new Set(['k1', 'k2', 'b1']))
    expect([...next]).toEqual(['b1'])
    expect(dayState(day, next)).toBe('checked')
  })

  it('takes every shift of an indeterminate day in, as a mixed checkbox does', () => {
    const next = toggleDay(day, new Set(['k2']))
    expect([...next]).toEqual([])
    expect(dayState(day, next)).toBe('checked')
  })

  it('changes nothing for an empty day', () => {
    expect([...toggleDay([], new Set(['k1']))]).toEqual(['k1'])
  })

  it('returns a new set and leaves the one given alone', () => {
    const before = new Set<string>()
    const next = toggleDay(day, before)
    expect(next).not.toBe(before)
    expect(before.size).toBe(0)
  })
})

describe('days and single shifts share one set', () => {
  it('re-including one shift of an unchecked day makes the day indeterminate', () => {
    const unchecked = toggleDay([k1, k2], new Set())
    const next = setShiftIncluded(unchecked, 'k2', true)
    expect(dayState([k1, k2], next)).toBe('indeterminate')
    expect(ids(includedShifts(ALL, ['kitchen'], next))).toEqual(['k2', 'k3'])
  })

  it('leaving out the last shift of a day unchecks it', () => {
    const next = setShiftIncluded(new Set(['k1']), 'k2', false)
    expect(dayState([k1, k2], next)).toBe('unchecked')
  })

  it('setting a shift to what it already is changes nothing', () => {
    expect([...setShiftIncluded(new Set(['k1']), 'k1', false)]).toEqual(['k1'])
    expect([...setShiftIncluded(new Set(), 'k1', true)]).toEqual([])
  })
})

describe('addTask', () => {
  it('starts a task with every shift in, clearing ids left from an earlier pick', () => {
    const stale = new Set(['k1', 'k3', 'b1'])
    expect([...addTask(stale, ['k1', 'k2', 'k3'])]).toEqual(['b1'])
  })

  it('leaves the given set alone', () => {
    const stale = new Set(['k1'])
    addTask(stale, ['k1'])
    expect([...stale]).toEqual(['k1'])
  })
})

describe('pruneExcluded', () => {
  const byId = new Map(ALL.map((s) => [s.id, s]))

  it('keeps only exclusions of selected tasks, by the shift’s task, sorted', () => {
    expect(pruneExcluded(new Set(['k3', 'b1', 'k1']), ['kitchen'], byId)).toEqual(['k1', 'k3'])
  })

  it('drops ids of shifts it does not know, such as ones that have started', () => {
    expect(pruneExcluded(new Set(['gone', 'b1']), ['kitchen', 'bar'], byId)).toEqual(['b1'])
  })
})

describe('includedShifts', () => {
  it('offers the selected tasks’ shifts that are not excluded, in order', () => {
    expect(ids(includedShifts(ALL, ['kitchen', 'bar'], new Set(['k2'])))).toEqual([
      'k1',
      'k3',
      'b1',
    ])
  })
})

describe('taskProblem', () => {
  const full = shift('f', 'kitchen', SAT, '16:00:00', 0)

  it('is none with a free shift in', () => {
    expect(taskProblem([k1, full], new Set())).toBe('none')
  })

  it('is no_included with every shift left out, or none to leave in', () => {
    expect(taskProblem([k1, full], new Set(['k1', 'f']))).toBe('no_included')
    expect(taskProblem([], new Set())).toBe('no_included')
  })

  it('is all_full when every shift left in is full', () => {
    expect(taskProblem([k1, full], new Set(['k1']))).toBe('all_full')
  })
})

describe('step1Blockers', () => {
  const both = [task('kitchen', 'Kitchen'), task('bar', 'Bar')]

  it('asks for a task first', () => {
    expect(step1Blockers([], ALL, new Set())).toEqual([{ kind: 'no_task' }])
  })

  it('has nothing to say about a list that can open', () => {
    expect(step1Blockers(both, ALL, new Set())).toEqual([])
  })

  it('is one blocker when nothing at all is left in, however it got there', () => {
    expect(step1Blockers(both, ALL, new Set(ids(ALL)))).toEqual([{ kind: 'no_included_shift' }])
  })

  it('names a task whose shifts are all left out, whether by day or one by one', () => {
    const byDay = toggleDay([b1, k3], new Set())
    expect(step1Blockers(both, ALL, byDay)).toEqual([{ kind: 'task_no_included', name: 'Bar' }])
    const oneByOne = new Set(['b1'])
    expect(step1Blockers(both, ALL, oneByOne)).toEqual(step1Blockers(both, ALL, byDay))
  })

  it('names a task the list holds but can no longer offer, before anything else', () => {
    const moved = [task('kitchen', 'Kitchen'), task('gone', 'Tent', 'not_published')]
    expect(step1Blockers(moved, ALL, new Set())).toEqual([
      { kind: 'task_unavailable', name: 'Tent', reason: 'not_published' },
    ])
  })

  it('says when every shift left in is full', () => {
    const full = [shift('f1', 'kitchen', SAT, '10:00:00', 0)]
    expect(step1Blockers([task('kitchen')], full, new Set())).toEqual([{ kind: 'no_free_place' }])
  })

  it('refuses more tasks than a list takes', () => {
    const many = Array.from({ length: MAX_TASKS + 1 }, (_, i) => task(`t${i}`))
    expect(step1Blockers(many, [shift('s', 't0', SAT)], new Set())[0]).toEqual({
      kind: 'too_many_tasks',
      max: MAX_TASKS,
    })
  })
})

describe('onlyDays', () => {
  it('is null while every day keeps a shift in', () => {
    expect(onlyDays(ALL, ['kitchen', 'bar'], new Set(['k1']))).toBeNull()
  })

  it('names the days left once one is left out completely', () => {
    expect(onlyDays(ALL, ['kitchen', 'bar'], new Set(['k1', 'k2']))).toEqual([SUN])
  })

  it('counts only the selected tasks’ days', () => {
    expect(onlyDays(ALL, ['bar'], new Set(['k1', 'k2']))).toBeNull()
  })
})

describe('lastShift', () => {
  it('is the shift that starts last', () => {
    expect(lastShift([b1, k1, k3])?.id).toBe('b1')
  })

  it('is null without shifts', () => {
    expect(lastShift([])).toBeNull()
  })
})

describe('maxPerOptions', () => {
  it('offers "as many as are free" first, then 1 up to 3', () => {
    expect(maxPerOptions(10)).toEqual([null, 1, 2, 3])
  })

  it('offers no more than the list has shifts', () => {
    expect(maxPerOptions(2)).toEqual([null, 1, 2])
    expect(maxPerOptions(0)).toEqual([null])
  })

  it('always keeps the limit already chosen, so it never changes by itself', () => {
    expect(maxPerOptions(10, 5)).toEqual([null, 1, 2, 3, 5])
    expect(maxPerOptions(10, 2)).toEqual([null, 1, 2, 3])
    // Fewer shifts left than the limit: started ones still count towards it.
    expect(maxPerOptions(1, 2)).toEqual([null, 1, 2])
    // No shift chosen for the moment (a task swapped): the limit waits.
    expect(maxPerOptions(0, 1)).toEqual([null, 1])
  })
})

describe('autoTitle', () => {
  const t = i18n.global.t

  it('is empty without tasks', () => {
    i18n.global.locale.value = 'de'
    expect(autoTitle([], 'Weihnachtsmarkt', t)).toBe('')
  })

  it('asks for help with one task, names two, and names the event for more', () => {
    i18n.global.locale.value = 'de'
    expect(autoTitle(['Glühwein'], 'Weihnachtsmarkt', t)).toBe('Glühwein: Wer hilft mit?')
    expect(autoTitle(['Glühwein', 'Kasse'], 'Weihnachtsmarkt', t)).toBe('Glühwein und Kasse')
    expect(autoTitle(['A', 'B', 'C'], 'Weihnachtsmarkt', t)).toBe('Hilf mit: Weihnachtsmarkt')
    i18n.global.locale.value = 'en'
    expect(autoTitle(['Bar'], 'Fair', t)).toBe('Bar: who can help?')
  })

  it('stays within the length the API takes', () => {
    i18n.global.locale.value = 'en'
    expect(autoTitle(['x'.repeat(200)], 'Fair', t)).toHaveLength(120)
  })
})
