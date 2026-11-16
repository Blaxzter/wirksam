import { afterEach, describe, expect, it } from 'vitest'

import { blankDraft, toPayload } from '@/lib/shared-list-draft'
import {
  canShareTask,
  eventListTitle,
  noticeListBody,
  planEventPrint,
  planTaskPrint,
  taskOfferProblem,
} from '@/lib/shared-list-print'
import { MAX_TASKS } from '@/lib/shared-list-selection'

/** Noon on 4 December in Berlin: the shifts on the 5th lie ahead. */
const NOW = new Date('2026-12-04T11:00:00Z')

const admin = {
  status: 'published' as const,
  timezone: 'Europe/Berlin',
  is_sandbox: false,
  can_manage: true,
  managed_task_count: 0,
  managers_share_lists: true,
}
/** In charge of some of the event's tasks, not running it. */
const manager = { ...admin, can_manage: false, managed_task_count: 2 }

function task(id: string, patch: Record<string, unknown> = {}) {
  return {
    id,
    name: `Task ${id}`,
    status: 'published' as const,
    team_id: null,
    can_manage: true,
    ...patch,
  }
}

const ahead = { date: '2026-12-05', start_time: '10:00:00', max_bookings: 2, current_bookings: 1 }
const started = { ...ahead, date: '2026-12-04', start_time: '08:00:00' }
const full = { ...ahead, current_bookings: 2 }

afterEach(() => {
  delete globalThis.__APP_CONFIG__
})

describe('canShareTask', () => {
  it('lets event admins share any task', () => {
    expect(canShareTask(admin, { can_manage: false })).toBe(true)
  })

  it('lets a person in charge share their own task while the event allows it', () => {
    expect(canShareTask(manager, { can_manage: true })).toBe(true)
    expect(canShareTask(manager, { can_manage: false })).toBe(false)
    expect(canShareTask({ ...manager, managers_share_lists: false }, { can_manage: true })).toBe(
      false,
    )
  })

  it('shares nothing in a demo or while the lists are switched off', () => {
    expect(canShareTask({ ...admin, is_sandbox: true }, { can_manage: true })).toBe(false)
    globalThis.__APP_CONFIG__ = { SHARED_LISTS_ENABLED: 'false' }
    expect(canShareTask(admin, { can_manage: true })).toBe(false)
  })
})

describe('taskOfferProblem', () => {
  const zone = 'Europe/Berlin'

  it('is none for a published task with a free place ahead', () => {
    expect(taskOfferProblem(task('t1'), [started, ahead], zone, NOW)).toBeNull()
  })

  it('names an unpublished task first, then a team-only one', () => {
    expect(
      taskOfferProblem(task('t1', { status: 'draft', team_id: 'x' }), [ahead], zone, NOW),
    ).toBe('not_published')
    expect(taskOfferProblem(task('t1', { team_id: 'x' }), [ahead], zone, NOW)).toBe('team_locked')
  })

  it('needs a shift that has not started and has a place left', () => {
    expect(taskOfferProblem(task('t1'), [started, full], zone, NOW)).toBe('no_free_place')
    expect(taskOfferProblem(task('t1'), [], zone, NOW)).toBe('no_free_place')
  })

  it('counts one place for a shift without a size and none booked without a count', () => {
    const bare = { date: '2026-12-05', start_time: null }
    expect(taskOfferProblem(task('t1'), [bare], zone, NOW)).toBeNull()
  })
})

describe('planTaskPrint', () => {
  it('prints the plain sheet for whoever cannot share the task', () => {
    expect(planTaskPrint(manager, task('t1', { can_manage: false }), [ahead], NOW)).toEqual({
      kind: 'plain',
    })
  })

  it('explains why a task that cannot be offered gets no QR code', () => {
    expect(planTaskPrint({ ...admin, status: 'draft' }, task('t1'), [ahead], NOW)).toEqual({
      kind: 'explain',
      problem: 'event_not_published',
    })
    expect(planTaskPrint(admin, task('t1', { team_id: 'x' }), [ahead], NOW)).toEqual({
      kind: 'explain',
      problem: 'team_locked',
    })
  })

  it('puts the task alone on a list named after it, cut to the length a title takes', () => {
    expect(planTaskPrint(admin, task('t1'), [ahead], NOW)).toEqual({
      kind: 'list',
      taskIds: ['t1'],
      title: 'Task t1',
    })
    const long = task('t1', { name: `${'x'.repeat(119)} y` })
    const plan = planTaskPrint(manager, long, [ahead], NOW)
    expect(plan.kind === 'list' && plan.title).toBe('x'.repeat(119))
  })
})

describe('planEventPrint', () => {
  const shiftsOf = (taskId: string) => {
    if (taskId === 'full') return [full]
    if (taskId === 'over') return [started]
    return [ahead]
  }

  it('prints plain sheets for whoever cannot share here', () => {
    expect(
      planEventPrint({ ...manager, managers_share_lists: false }, [task('a')], shiftsOf, NOW),
    ).toEqual({ kind: 'plain' })
  })

  it('explains an unpublished event before looking at its tasks', () => {
    expect(planEventPrint({ ...admin, status: 'draft' }, [task('a')], shiftsOf, NOW)).toEqual({
      kind: 'explain',
      reason: 'event_not_published',
      offered: 0,
      leftOut: [],
    })
  })

  it('shares the tasks it can offer and names the rest with why', () => {
    const tasks = [
      task('a'),
      task('team', { team_id: 'x' }),
      task('over'),
      task('draft', { status: 'draft' }),
      task('theirs', { can_manage: false }),
    ]
    expect(planEventPrint(manager, tasks, shiftsOf, NOW)).toEqual({
      kind: 'list',
      taskIds: ['a'],
      leftOut: [
        { id: 'team', name: 'Task team', problem: 'team_locked' },
        { id: 'over', name: 'Task over', problem: 'no_shift_ahead' },
        { id: 'draft', name: 'Task draft', problem: 'not_published' },
        { id: 'theirs', name: 'Task theirs', problem: 'not_yours' },
      ],
    })
  })

  it('keeps a full task on the list, so the list stays the same while shifts fill', () => {
    // The server asks for a free place somewhere on the list, not on each task.
    expect(planEventPrint(admin, [task('a'), task('full')], shiftsOf, NOW)).toEqual({
      kind: 'list',
      taskIds: ['a', 'full'],
      leftOut: [],
    })
  })

  it('explains when no task can be offered', () => {
    expect(planEventPrint(admin, [task('over')], shiftsOf, NOW)).toEqual({
      kind: 'explain',
      reason: 'none_offered',
      offered: 0,
      leftOut: [{ id: 'over', name: 'Task over', problem: 'no_shift_ahead' }],
    })
  })

  it('explains when no shift still to come has a free place', () => {
    expect(planEventPrint(admin, [task('full'), task('over')], shiftsOf, NOW)).toEqual({
      kind: 'explain',
      reason: 'no_free_place',
      offered: 1,
      leftOut: [{ id: 'over', name: 'Task over', problem: 'no_shift_ahead' }],
    })
  })

  it('explains when one list could not hold them all', () => {
    const many = Array.from({ length: MAX_TASKS + 1 }, (_, i) => task(`t${i}`))
    expect(planEventPrint(admin, many, shiftsOf, NOW)).toEqual({
      kind: 'explain',
      reason: 'too_many',
      offered: MAX_TASKS + 1,
      leftOut: [],
    })
  })
})

describe('eventListTitle', () => {
  const t = (key: string, named: Record<string, unknown>) => `${key}:${String(named.event)}`

  it('names the event, cut to the length a title takes', () => {
    expect(eventListTitle('Basar', t)).toBe('print.notice.eventTitle:Basar')
    expect(eventListTitle('x'.repeat(200), t)).toHaveLength(120)
  })
})

describe('noticeListBody', () => {
  it('is the wizard’s new list with this title and these tasks, every shift in', () => {
    const draft = blankDraft([
      { id: 'a', name: '', unavailable: null },
      { id: 'b', name: '', unavailable: null },
    ])
    draft.title = 'Basar – alle Aufgaben'
    expect(noticeListBody('Basar – alle Aufgaben', ['a', 'b'])).toEqual(toPayload(draft, []))
  })

  it('asks for an address, no phone, names nobody, limits nothing and closes with the last shift', () => {
    expect(noticeListBody('Kuchen', ['a'])).toEqual({
      title: 'Kuchen',
      intro: null,
      share_note: null,
      task_ids: ['a'],
      excluded_shift_ids: [],
      ask_email: 'required',
      ask_phone: 'off',
      show_names: 'none',
      max_per_person: null,
      ends_mode: 'last_shift',
      ends_on: null,
    })
  })
})
