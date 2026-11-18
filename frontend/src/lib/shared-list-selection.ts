/**
 * Which shifts a shared list offers, as the wizard edits it.
 *
 * The selection is the chosen tasks minus ONE set of excluded shift ids, the
 * same shape the API stores (`task_ids` + `excluded_shift_ids`). Days are never
 * stored: a day's checkbox is read off its shifts, and ticking a day only adds
 * or removes its shift ids from that one set. So a day and its shifts cannot
 * disagree, which the approved prototype allowed (correction (a)).
 *
 * Everything here is pure and returns new sets, never mutating the one given.
 */
import type { SharedListCandidateShift } from '@/client/types.gen'
import { TITLE_MAX } from '@/lib/shared-list-draft'

export type WizardShift = SharedListCandidateShift

/** How a day's checkbox reads: all of its shifts in, some, none, or no shift at all. */
export type DayState = 'checked' | 'indeterminate' | 'unchecked' | 'empty'

/** Why a selected task cannot be offered as it stands. */
export type TaskProblem = 'none' | 'no_included' | 'all_full'

/** Why a task already on a list cannot stay there (`SharedListDetailTask.not_offered_reason`). */
export type UnavailableReason = 'team_locked' | 'not_published' | 'moved'

/** A task the wizard has picked, as far as the checks below need it. */
export interface PickedTask {
  id: string
  name: string
  /** Set when the list holds a task it can no longer offer; the server would refuse it. */
  unavailable: UnavailableReason | null
}

/** The API refuses more tasks than this on one list (`SharedListCreate.task_ids`). */
export const MAX_TASKS = 50

export type Step1Blocker =
  | { kind: 'no_task' }
  | { kind: 'too_many_tasks'; max: number }
  | { kind: 'task_unavailable'; name: string; reason: UnavailableReason }
  | { kind: 'no_included_shift' }
  | { kind: 'task_no_included'; name: string }
  | { kind: 'no_free_place' }

/** Shifts in the order the public page lists them: by day, then start (untimed first). */
export function byStart(a: WizardShift, b: WizardShift): number {
  if (a.date !== b.date) return a.date < b.date ? -1 : 1
  const sa = a.start_time ?? ''
  const sb = b.start_time ?? ''
  if (sa !== sb) return sa < sb ? -1 : 1
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
}

/** The shifts of the selected tasks, grouped by date (`YYYY-MM-DD`), days and shifts in order. */
export function shiftsByDay(
  shifts: readonly WizardShift[],
  selectedTaskIds: Iterable<string>,
): Map<string, WizardShift[]> {
  const selected = new Set(selectedTaskIds)
  const days = new Map<string, WizardShift[]>()
  for (const shift of [...shifts].sort(byStart)) {
    if (!selected.has(shift.task_id)) continue
    const day = days.get(shift.date)
    if (day) day.push(shift)
    else days.set(shift.date, [shift])
  }
  return days
}

export function dayState(
  dayShifts: readonly WizardShift[],
  excluded: ReadonlySet<string>,
): DayState {
  if (dayShifts.length === 0) return 'empty'
  const included = dayShifts.filter((s) => !excluded.has(s.id)).length
  if (included === 0) return 'unchecked'
  return included === dayShifts.length ? 'checked' : 'indeterminate'
}

/**
 * Tick or untick a day. A fully ticked day drops all of its shifts; a day that
 * is partly or not at all ticked takes all of them in, which is what clicking
 * a mixed checkbox means everywhere else.
 */
export function toggleDay(
  dayShifts: readonly WizardShift[],
  excluded: ReadonlySet<string>,
): Set<string> {
  const next = new Set(excluded)
  const exclude = dayState(dayShifts, excluded) === 'checked'
  for (const shift of dayShifts) {
    if (exclude) next.add(shift.id)
    else next.delete(shift.id)
  }
  return next
}

/** Take one shift in or leave it out. */
export function setShiftIncluded(
  excluded: ReadonlySet<string>,
  shiftId: string,
  included: boolean,
): Set<string> {
  const next = new Set(excluded)
  if (included) next.delete(shiftId)
  else next.add(shiftId)
  return next
}

/**
 * A task that joins the selection starts with every shift in. Ids left over
 * from an earlier pick of the same task are cleared, so picking it again does
 * not bring back shifts that were dropped back then.
 */
export function addTask(
  excluded: ReadonlySet<string>,
  taskShiftIds: Iterable<string>,
): Set<string> {
  const next = new Set(excluded)
  for (const id of taskShiftIds) next.delete(id)
  return next
}

/**
 * The exclusions worth sending: only shifts the wizard knows, of tasks still
 * selected, sorted. Ids of tasks that were taken out, and of shifts that have
 * started since (the API no longer offers them anyway), are dropped.
 */
export function pruneExcluded(
  excluded: ReadonlySet<string>,
  selectedTaskIds: Iterable<string>,
  shiftsById: ReadonlyMap<string, WizardShift>,
): string[] {
  const selected = new Set(selectedTaskIds)
  return [...excluded]
    .filter((id) => {
      const shift = shiftsById.get(id)
      return shift !== undefined && selected.has(shift.task_id)
    })
    .sort()
}

/** The shifts the list offers: of a selected task and not excluded, in order. */
export function includedShifts(
  shifts: readonly WizardShift[],
  selectedTaskIds: Iterable<string>,
  excluded: ReadonlySet<string>,
): WizardShift[] {
  const selected = new Set(selectedTaskIds)
  return shifts.filter((s) => selected.has(s.task_id) && !excluded.has(s.id)).sort(byStart)
}

/**
 * What is wrong with one selected task: nothing, every shift left out (which
 * blocks), or every shift left in already full (a warning: the list still
 * shows them, nobody can take them).
 */
export function taskProblem(
  taskShifts: readonly WizardShift[],
  excluded: ReadonlySet<string>,
): TaskProblem {
  const included = taskShifts.filter((s) => !excluded.has(s.id))
  if (included.length === 0) return 'no_included'
  return included.some((s) => s.free > 0) ? 'none' : 'all_full'
}

/**
 * Everything that keeps the first step from being done, most basic first; the
 * wizard names the first. A task with no shift left in is one blocker, however
 * it got there (its days unticked, or its shifts one by one).
 */
export function step1Blockers(
  tasks: readonly PickedTask[],
  shifts: readonly WizardShift[],
  excluded: ReadonlySet<string>,
): Step1Blocker[] {
  if (tasks.length === 0) return [{ kind: 'no_task' }]
  const blockers: Step1Blocker[] = []
  if (tasks.length > MAX_TASKS) blockers.push({ kind: 'too_many_tasks', max: MAX_TASKS })
  for (const task of tasks) {
    if (task.unavailable) {
      blockers.push({ kind: 'task_unavailable', name: task.name, reason: task.unavailable })
    }
  }
  const included = includedShifts(
    shifts,
    tasks.map((t) => t.id),
    excluded,
  )
  if (included.length === 0) {
    blockers.push({ kind: 'no_included_shift' })
    return blockers
  }
  for (const task of tasks) {
    if (task.unavailable) continue
    const own = shifts.filter((s) => s.task_id === task.id)
    if (taskProblem(own, excluded) === 'no_included') {
      blockers.push({ kind: 'task_no_included', name: task.name })
    }
  }
  if (!included.some((s) => s.free > 0)) blockers.push({ kind: 'no_free_place' })
  return blockers
}

/**
 * The days the list offers, when that is fewer than the days its tasks have
 * shifts on; `null` while every one of those days has at least one shift in.
 * The same rule as the API's `only_days`.
 */
export function onlyDays(
  shifts: readonly WizardShift[],
  selectedTaskIds: Iterable<string>,
  excluded: ReadonlySet<string>,
): string[] | null {
  const days = shiftsByDay(shifts, selectedTaskIds)
  const offered = [...days]
    .filter(([, dayShifts]) => dayState(dayShifts, excluded) !== 'unchecked')
    .map(([day]) => day)
  return offered.length < days.size ? offered : null
}

/** The shift that starts last: the one a "last shift" list closes with. */
export function lastShift(shifts: readonly WizardShift[]): WizardShift | null {
  return shifts.length ? [...shifts].sort(byStart)[shifts.length - 1] : null
}

/**
 * The choices for "Schichten pro Person": `null` (as many as are free, the
 * default) first, then 1 up to 3, but no more than the list has shifts.
 *
 * The limit already chosen (`keep`, up to the API's 50) stays among them
 * whatever the shifts do, so the wizard never lowers it on its own: a list
 * counts every booking made through it, started shifts too, so a limit above
 * the shifts left still holds for whoever has worked some of them.
 */
export function maxPerOptions(
  includedCount: number,
  keep: number | null = null,
): (number | null)[] {
  const top = Math.min(3, includedCount)
  const options: (number | null)[] = [null]
  for (let n = 1; n <= top; n += 1) options.push(n)
  if (keep !== null && keep > top) options.push(keep)
  return options
}

/** `t` as the title helper needs it: a key and its named values. */
export type TranslateNamed = (key: string, named: Record<string, unknown>) => string

/**
 * The heading the wizard suggests until someone types their own: the task's
 * name for one task, both names for two, the event for more. Cut to the
 * length the API takes, since names can be long.
 */
export function autoTitle(
  taskNames: readonly string[],
  eventName: string,
  t: TranslateNamed,
): string {
  if (taskNames.length === 0) return ''
  const title =
    taskNames.length === 1
      ? t('sharedListWizard.autoTitle.one', { name: taskNames[0] })
      : taskNames.length === 2
        ? t('sharedListWizard.autoTitle.two', { first: taskNames[0], second: taskNames[1] })
        : t('sharedListWizard.autoTitle.many', { event: eventName })
  return title.slice(0, TITLE_MAX).trim()
}
