/**
 * The text the wizard offers for a group chat once a list is open, and the
 * short "which days" phrase its task lines and the task picker share.
 *
 * Built from what the list offers right now. With a handful of open shifts it
 * names each one under its task; with more it gives one line per task, so the
 * message stays readable on a phone. The organiser can edit it before copying.
 */
import { type WizardShift, byStart } from '@/lib/shared-list-selection'

/** Up to this many open shifts are listed one by one; above it, per task. */
export const PER_SHIFT_LINES_MAX = 8

/** Up to this many separate days are named; above it, the span and a count. */
export const LISTED_DAYS_MAX = 3

/** `t` as the message needs it: a key, its named values and, for plurals, the count. */
export interface Translate {
  (key: string, named: Record<string, unknown>): string
  (key: string, named: Record<string, unknown>, plural: number): string
}

export interface DaysFormat {
  /** "6.–8. Dezember": two dates (or the same one twice) as a span. */
  span: (start: string, end: string) => string
  /** "Sa., 6.12.": one date. */
  day: (date: string) => string
  /** "A, B und C": several phrases joined. */
  list: (items: string[]) => string
  /** "6.–20. Dezember, an 5 Tagen": a span with gaps, and how many days are in it. */
  spread: (span: string, count: number) => string
}

const DAY_MS = 86_400_000

function dayNumber(date: string): number {
  return Math.round(new Date(`${date}T00:00:00Z`).getTime() / DAY_MS)
}

/** Whether sorted `YYYY-MM-DD` dates follow each other without a gap. */
export function isConsecutive(dates: readonly string[]): boolean {
  return dates.every((date, i) => i === 0 || dayNumber(date) - dayNumber(dates[i - 1]) === 1)
}

/**
 * The days something runs on, as briefly as is still exact: a span when they
 * follow each other, the days themselves when there are few, otherwise the
 * span and how many days fall in it.
 */
export function describeDays(dates: readonly string[], format: DaysFormat): string {
  const days = [...new Set(dates)].sort()
  if (days.length === 0) return ''
  const span = format.span(days[0], days[days.length - 1])
  if (isConsecutive(days)) return span
  if (days.length <= LISTED_DAYS_MAX) return format.list(days.map(format.day))
  return format.spread(span, days.length)
}

export interface ShareMessageInput {
  eventName: string
  /** The event's dates, already written out. */
  eventDays: string
  /** In list order. */
  tasks: readonly { id: string; name: string }[]
  /** The shifts the list offers; the full ones are left out of the message. */
  shifts: readonly WizardShift[]
  url: string
}

export interface ShareMessageFormat {
  /** One shift's day. */
  day: (date: string) => string
  /** One shift's times, or '' for a shift without a start. */
  time: (start: string | null, end: string | null) => string
  /** Several days, as `describeDays` writes them. */
  days: (dates: string[]) => string
}

const KEY = 'sharedListWizard.shareMessage'

export function shareMessage(
  input: ShareMessageInput,
  format: ShareMessageFormat,
  t: Translate,
): string {
  const open = input.shifts.filter((s) => s.free > 0).sort(byStart)
  const lines = [t(`${KEY}.greeting`, { event: input.eventName, days: input.eventDays }), '']
  const perTask = input.tasks
    .map((task) => ({ task, shifts: open.filter((s) => s.task_id === task.id) }))
    .filter((group) => group.shifts.length > 0)

  if (open.length > PER_SHIFT_LINES_MAX) {
    for (const { task, shifts } of perTask) {
      const free = shifts.reduce((sum, s) => sum + s.free, 0)
      const days = format.days(shifts.map((s) => s.date))
      lines.push(t(`${KEY}.task`, { task: task.name, free, days }, free))
    }
    lines.push('')
  } else if (open.length > 0) {
    for (const { task, shifts } of perTask) {
      lines.push(task.name)
      for (const shift of shifts) {
        const day = format.day(shift.date)
        const time = format.time(shift.start_time, shift.end_time)
        lines.push(
          time
            ? t(`${KEY}.shift`, { day, time, free: shift.free })
            : t(`${KEY}.shiftAllDay`, { day, free: shift.free }),
        )
      }
      lines.push('')
    }
  }

  lines.push(t(`${KEY}.signUp`, {}), input.url)
  return lines.join('\n')
}
