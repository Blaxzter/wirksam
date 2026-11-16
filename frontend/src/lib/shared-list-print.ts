/**
 * Printing a notice anyone can sign up from: whether a printed task gets a
 * shared list's QR code, and the list a print makes when there is none to
 * reuse.
 *
 * The rules mirror the server's (`require_shared_list_tasks` and
 * `manage.validate_selection`) so the dialog can say why a sheet goes without
 * a QR code; the server still has the last word when the list is looked up
 * or created.
 */
import type { EventRead, ShiftRead, TaskRead } from '@/client/types.gen'
import { type SharedListPayload, TITLE_MAX, blankDraft, toPayload } from '@/lib/shared-list-draft'
import { MAX_TASKS, type TranslateNamed } from '@/lib/shared-list-selection'
import { canUseSharedLists } from '@/lib/shared-lists'
import { shiftHasStarted } from '@/lib/shift-time'

/** Why no list can offer a task at all (the server's `offer.offerable`). */
type ShareProblem = 'not_published' | 'team_locked'
/** Why a list could not offer one task now. */
export type TaskOfferProblem = ShareProblem | 'no_free_place'
/** Why a task's sheet goes without a QR code, as `print.notice.problem.*` says it. */
export type OfferProblem = 'event_not_published' | TaskOfferProblem
/** Why no task of an event goes on a list, as `print.notice.problem.*` says it. */
export type EventProblem = 'event_not_published' | 'none_offered' | 'no_free_place' | 'too_many'

/** A task of the event printed without a QR code, and why, as `print.notice.leftOut.*` says it. */
export interface LeftOutTask {
  id: string
  name: string
  problem: ShareProblem | 'no_shift_ahead' | 'not_yours'
}

type PrintEvent = Pick<
  EventRead,
  | 'status'
  | 'timezone'
  | 'is_sandbox'
  | 'can_manage'
  | 'managed_task_count'
  | 'managers_share_lists'
>
type PrintTask = Pick<TaskRead, 'id' | 'name' | 'status' | 'team_id' | 'can_manage'>
type PrintShift = Pick<ShiftRead, 'date' | 'start_time' | 'max_bookings' | 'current_bookings'>

/**
 * The viewer may put `task` on a list: event admins any task, a person in
 * charge their own while the event lets them (`managers_share_lists`), and
 * nobody in a demo or while shared lists are switched off.
 */
export function canShareTask(event: PrintEvent, task: Pick<TaskRead, 'can_manage'>): boolean {
  if (!canUseSharedLists(event)) return false
  if (event.can_manage) return true
  return !!task.can_manage && event.managers_share_lists !== false
}

function shareProblem(task: PrintTask): ShareProblem | null {
  if (task.status !== 'published') return 'not_published'
  if (task.team_id) return 'team_locked'
  return null
}

/** The shifts that have not started on the clock of `zone`. */
function ahead(shifts: readonly PrintShift[], zone: string, now: Date): PrintShift[] {
  return shifts.filter((shift) => !shiftHasStarted(shift.date, shift.start_time, zone, now))
}

function hasFreePlace(shifts: readonly PrintShift[]): boolean {
  return shifts.some((shift) => (shift.current_bookings ?? 0) < (shift.max_bookings ?? 1))
}

/**
 * Why a list of only `task` could not be made now, or null when it can
 * (`manage.validate_selection`): the task is published, open to everyone,
 * and a shift that has not started (on the clock of `zone`) has a free place.
 */
export function taskOfferProblem(
  task: PrintTask,
  shifts: readonly PrintShift[],
  zone: string,
  now: Date = new Date(),
): TaskOfferProblem | null {
  return shareProblem(task) ?? (hasFreePlace(ahead(shifts, zone, now)) ? null : 'no_free_place')
}

/** How printing one task goes on: the sheet without QR code, an explanation first, or a list. */
export type TaskPrintPlan =
  | { kind: 'plain' }
  | { kind: 'explain'; problem: OfferProblem }
  | { kind: 'list'; taskIds: string[]; title: string }

export function planTaskPrint(
  event: PrintEvent,
  task: PrintTask,
  shifts: readonly PrintShift[],
  now: Date = new Date(),
): TaskPrintPlan {
  if (!canShareTask(event, task)) return { kind: 'plain' }
  const problem =
    event.status === 'published'
      ? taskOfferProblem(task, shifts, event.timezone, now)
      : 'event_not_published'
  if (problem) return { kind: 'explain', problem }
  return { kind: 'list', taskIds: [task.id], title: task.name.slice(0, TITLE_MAX).trim() }
}

export type EventPrintPlan =
  | { kind: 'plain' }
  | { kind: 'explain'; reason: EventProblem; offered: number; leftOut: LeftOutTask[] }
  | { kind: 'list'; taskIds: string[]; leftOut: LeftOutTask[] }

/**
 * Printing every task of an event, a sheet each. The tasks the viewer can
 * share that have a shift still to come go on one list, full or not: a free
 * place is needed only somewhere on it, as the server checks, so the set
 * stays the same while shifts fill up. The others print without a QR code
 * and are named, with why. One list holds at most `MAX_TASKS` tasks.
 */
export function planEventPrint(
  event: PrintEvent,
  tasks: readonly PrintTask[],
  shiftsOf: (taskId: string) => readonly PrintShift[],
  now: Date = new Date(),
): EventPrintPlan {
  // Whether the viewer may share any task here at all.
  if (!canShareTask(event, { can_manage: true })) return { kind: 'plain' }
  if (event.status !== 'published') {
    return { kind: 'explain', reason: 'event_not_published', offered: 0, leftOut: [] }
  }
  const taskIds: string[] = []
  const upcoming: PrintShift[] = []
  const leftOut: LeftOutTask[] = []
  for (const task of tasks) {
    const shifts = ahead(shiftsOf(task.id), event.timezone, now)
    const problem = !canShareTask(event, task)
      ? 'not_yours'
      : (shareProblem(task) ?? (shifts.length ? null : 'no_shift_ahead'))
    if (problem) {
      leftOut.push({ id: task.id, name: task.name, problem })
    } else {
      taskIds.push(task.id)
      upcoming.push(...shifts)
    }
  }
  const offered = taskIds.length
  if (offered === 0) return { kind: 'explain', reason: 'none_offered', offered, leftOut }
  if (offered > MAX_TASKS) return { kind: 'explain', reason: 'too_many', offered, leftOut }
  if (!hasFreePlace(upcoming)) return { kind: 'explain', reason: 'no_free_place', offered, leftOut }
  return { kind: 'list', taskIds, leftOut }
}

/** The title of the one list behind a whole event's notices. */
export function eventListTitle(eventName: string, t: TranslateNamed): string {
  return t('print.notice.eventTitle', { event: eventName }).slice(0, TITLE_MAX).trim()
}

/**
 * The body of the list a print creates: the wizard's defaults, every shift
 * of the tasks that has not started, and `title`.
 */
export function noticeListBody(title: string, taskIds: readonly string[]): SharedListPayload {
  const draft = blankDraft(taskIds.map((id) => ({ id, name: '', unavailable: null })))
  draft.title = title
  return toPayload(draft, [])
}
