/**
 * The arithmetic behind the dashboard, kept out of the components.
 *
 * Nothing in here touches Vue, i18n or a store, and every function that needs
 * the time takes `now` as an argument: the page ticks its own clock once a
 * minute and hands it down, so a countdown, a greeting and a "today" label all
 * move together, and a test can pin the clock without faking timers.
 *
 * Shift dates arrive as `YYYY-MM-DD` and times as `HH:MM[:SS]`, with no zone;
 * they are read in the browser's local time, like `@/lib/shift-time`, whose
 * start and end rules (no times, past midnight) this file reuses rather than
 * restates.
 */
import type { RouteLocationRaw } from 'vue-router'

import type { DashboardAttention } from '@/client/types.gen'
import { firstName } from '@/lib/format'
import { parseServerDate } from '@/lib/server-time'
import { type ShiftZone, shiftEndsAt, shiftHasEnded, shiftStartsAt, wallClockIn } from '@/lib/shift-time'

/** Open-shift cards a phone shows before handing over to the Tasks board. */
export const MOBILE_OPEN_SHIFT_LIMIT = 4
/** The day strip's window starts at 08:00 unless the shift or "now" is earlier. */
export const DAY_STRIP_DEFAULT_START = 8
/** …and always runs to midnight. */
export const DAY_STRIP_END = 24
/** The Tasks board narrowed to shifts with room, as goBrowseOpenShifts did. */
export const OPEN_SHIFTS_ROUTE = { name: 'tasks', query: { hide_full: 'true' } } as const

export interface TimedShift {
  /** YYYY-MM-DD */
  date: string
  /** HH:MM[:SS] */
  start_time?: string | null
  end_time?: string | null
  /** The zone of the shift's event, which its times are in. */
  event_timezone?: string | null
}

const MS_PER_DAY = 86_400_000

/** 'YYYY-MM-DD' of a Date in local time. */
export function localIsoDate(d: Date): string {
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${month}-${day}`
}

function utcDay(date: string): number {
  const [y, m, d] = date.split('-').map(Number)
  return Date.UTC(y, m - 1, d)
}

/**
 * Whole calendar days from `from` to `to` (both YYYY-MM-DD). Compared as UTC
 * midnights, so a daylight-saving change in between cannot make a day 23 or
 * 25 hours long and round the answer the wrong way.
 */
export function calendarDaysBetween(from: string, to: string): number {
  return Math.round((utcDay(to) - utcDay(from)) / MS_PER_DAY)
}

/**
 * Calendar days from today (per `now`) to `date`: 0 today, 1 tomorrow, -1 yesterday.
 * "Today" is the reader's, or the one in `zone` when a shift's own clock decides.
 */
export function dayOffset(date: string, now: Date, zone?: ShiftZone): number {
  return calendarDaysBetween(zone ? wallClockIn(zone, now).date : localIsoDate(now), date)
}

export type GreetingBucket = 'morning' | 'afternoon' | 'evening'

/** [05:00, 12:00) morning, [12:00, 18:00) afternoon, everything else evening. */
export function greetingBucket(now: Date): GreetingBucket {
  const hour = now.getHours()
  if (hour >= 5 && hour < 12) return 'morning'
  if (hour >= 12 && hour < 18) return 'afternoon'
  return 'evening'
}

/**
 * The name to greet with, or null for a plain greeting.
 *
 * A sandbox guest is called "Demo visitor", which reads as a label rather
 * than a name, so it gets none. A nickname is what the person asked to be
 * called; otherwise the first word of the full name. An email address used as
 * a name is not something to say hello to.
 */
export function greetingName(
  profile:
    { name?: string | null; nickname?: string | null; is_sandbox?: boolean } | null | undefined,
): string | null {
  if (!profile || profile.is_sandbox) return null
  const nickname = profile.nickname?.trim()
  const name = nickname || firstName(profile.name ?? '')
  if (!name || name.includes('@')) return null
  return name
}

/**
 * "Day 2 of 3": null when there is no event, today is outside its dates, or
 * the event lasts a single day (where "Day 1 of 1" says nothing).
 */
export function eventDay(
  event: { start_date: string; end_date: string } | null | undefined,
  now: Date,
): { day: number; total: number } | null {
  if (!event) return null
  const total = calendarDaysBetween(event.start_date, event.end_date) + 1
  if (total <= 1) return null
  const day = calendarDaysBetween(event.start_date, localIsoDate(now)) + 1
  if (day < 1 || day > total) return null
  return { day, total }
}

export type Countdown =
  | { kind: 'startsIn'; hours: number; minutes: number }
  | { kind: 'running' }
  /** Not today: the caller says which day instead (`formatRelativeDay`). */
  | { kind: 'day' }
  | { kind: 'over' }

/**
 * How far away a shift is, for the chip on the next-shift card.
 *
 * Only a timed shift can be "running" or "in 2 h 15 min"; an untimed one is
 * named by its day until its day is over. Minutes round up, so the chip never
 * says "in 0 min" while the shift has not begun.
 */
export function shiftCountdown(shift: TimedShift, now: Date): Countdown {
  const t = now.getTime()
  const zone = shift.event_timezone
  if (t >= shiftEndsAt(shift.date, shift.start_time, shift.end_time, zone).getTime()) {
    return { kind: 'over' }
  }
  if (shift.start_time) {
    const start = shiftStartsAt(shift.date, shift.start_time, zone).getTime()
    if (t >= start) return { kind: 'running' }
    if (dayOffset(shift.date, now, zone) === 0) {
      const total = Math.ceil((start - t) / 60_000)
      return { kind: 'startsIn', hours: Math.floor(total / 60), minutes: total % 60 }
    }
  }
  return { kind: 'day' }
}

/**
 * The first shift that is not over by `now`, or null.
 *
 * The feed sends your shifts until they end by the server's clock, which can
 * run behind the page's. Taking the first one still on keeps the card from
 * sitting on a shift that has finished, with no countdown, until the page is
 * reloaded.
 */
export function nextUnfinished<T extends TimedShift>(shifts: readonly T[], now: Date): T | null {
  return (
    shifts.find((s) => !shiftHasEnded(s.date, s.start_time, s.end_time, s.event_timezone, now)) ??
    null
  )
}

/**
 * The booking ids of the shifts that are over by `now`, as one string, '' for
 * none. A watcher on it fires when another shift ends, and not again when a
 * reload brings back the same finished row (the server's clock behind ours).
 */
export function endedShiftsKey(
  shifts: readonly (TimedShift & { booking_id: string })[],
  now: Date,
): string {
  return shifts
    .filter((s) => shiftHasEnded(s.date, s.start_time, s.end_time, s.event_timezone, now))
    .map((s) => s.booking_id)
    .join(',')
}

/**
 * The voucher shifts the account still counts as to come although they have
 * ended by `now`, as one key, '' for none.
 *
 * `completed`, `available` and `upcoming` are what the server worked out when
 * the account was read; they do not move on their own. `ends_at` is naive UTC,
 * so it is compared as UTC rather than in the browser's zone.
 */
export function voucherShiftsDueKey(
  shifts: readonly { booking_id: string; ends_at: string; completed: boolean }[],
  now: Date,
): string {
  return shifts
    .filter((s) => {
      if (s.completed) return false
      const ends = parseServerDate(s.ends_at)
      return ends !== null && ends.getTime() <= now.getTime()
    })
    .map((s) => s.booking_id)
    .join(',')
}

export interface DayStrip {
  /** Window start, a whole hour. */
  startHour: number
  /** Always 24. */
  endHour: number
  /** Percent of the window, two decimals. */
  block: { left: number; width: number }
  /** Percent, or null unless the shift is today. */
  nowAt: number | null
  ticks: { hour: number; at: number; edge: 'start' | 'end' | null }[]
}

function fractionalHours(time: string): number {
  const [h, m] = time.split(':').map(Number)
  return h + m / 60
}

const round2 = (n: number) => Math.round(n * 100) / 100

/**
 * The shift drawn on a bar of its day, for the desktop next-shift card.
 *
 * Needs both times; without them there is nothing to draw. A shift that ends
 * at or before it starts runs past midnight, and the bar stops at 24:00 rather
 * than wrapping. The window opens at 08:00, or earlier for an early shift or
 * an early look at the page, so the block and the "now" marker always fit.
 */
export function dayStrip(shift: TimedShift, now: Date): DayStrip | null {
  if (!shift.start_time || !shift.end_time) return null
  const startH = fractionalHours(shift.start_time)
  let endH = fractionalHours(shift.end_time)
  if (endH <= startH) endH = DAY_STRIP_END
  // The shift's times are on its own clock, so "now" has to be as well.
  const wall = wallClockIn(shift.event_timezone, now)
  const nowH = wall.date === shift.date ? wall.hours : null

  const startHour = Math.min(
    DAY_STRIP_DEFAULT_START,
    Math.floor(startH),
    nowH !== null ? Math.floor(nowH) : DAY_STRIP_DEFAULT_START,
  )
  const endHour = DAY_STRIP_END
  const span = endHour - startHour
  const at = (hour: number) => round2(((hour - startHour) / span) * 100)

  // Every fourth hour between the edges, unless it would crowd the start
  // label. The end is always 24, and the last multiple of 4 before it is 20,
  // so nothing can crowd the end label.
  const ticks: DayStrip['ticks'] = [{ hour: startHour, at: 0, edge: 'start' }]
  for (let hour = Math.floor(startHour / 4) * 4 + 4; hour < endHour; hour += 4) {
    if (hour - startHour >= 2) ticks.push({ hour, at: at(hour), edge: null })
  }
  ticks.push({ hour: endHour, at: 100, edge: 'end' })

  return {
    startHour,
    endHour,
    block: { left: at(startH), width: round2(((endH - startH) / span) * 100) },
    nowAt: nowH !== null ? at(nowH) : null,
    ticks,
  }
}

/**
 * An hour formatter when the clock in use is a 12-hour one, else null.
 *
 * `hour12` is the user's time-format choice, undefined for the locale's own
 * (English: 12-hour, German: 24-hour). The day strip uses it so its labels
 * follow the same clock as the times printed above it.
 */
export function twelveHourFormatter(
  locale: string,
  hour12: boolean | undefined,
): Intl.DateTimeFormat | null {
  const fmt = new Intl.DateTimeFormat(locale, { hour: 'numeric', hour12 })
  return fmt.resolvedOptions().hour12 === true ? fmt : null
}

/** A trailing "14:00-17:00" (hyphen or en dash) on a generated shift title. */
const TRAILING_TIME_RANGE = /\s*\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\s*$/

/**
 * Generated shift titles are "{task} HH:MM-HH:MM" (backend
 * `shift_generator.py`), and the times are printed beside them anyway. So the
 * headline drops the trailing range, and the job is named underneath only
 * when the headline is somebody's own wording that does not already carry it.
 */
export function shiftHeadline(
  title: string,
  taskName: string,
): { headline: string; taskLine: string | null } {
  const headline = title.replace(TRAILING_TIME_RANGE, '').trim() || title
  return { headline, taskLine: headline.includes(taskName) ? null : taskName }
}

/** round(taken / capacity * 100) clamped to 0..100; 0 when capacity <= 0. */
export function fillPercent(taken: number, capacity: number): number {
  if (capacity <= 0) return 0
  return Math.min(100, Math.max(0, Math.round((taken / capacity) * 100)))
}

/** Rows the feed counted but did not send (or a list did not show). */
export function hiddenCount(total: number, shown: number): number {
  return Math.max(total - shown, 0)
}

export interface PlanDay<T> {
  date: string
  offset: number
  items: T[]
}

/** Groups by date in first-seen order, keeping the items' own order. */
export function groupByDay<T extends { date: string }>(
  items: readonly T[],
  now: Date,
): PlanDay<T>[] {
  const days = new Map<string, PlanDay<T>>()
  for (const item of items) {
    let day = days.get(item.date)
    if (!day) {
      day = { date: item.date, offset: dayOffset(item.date, now), items: [] }
      days.set(item.date, day)
    }
    day.items.push(item)
  }
  return [...days.values()]
}

export type AttentionKey = 'empty' | 'short' | 'requests' | 'team-requests' | 'drafts'
export type AttentionTone = 'destructive' | 'warning' | 'neutral'
export interface AttentionItem {
  key: AttentionKey
  count: number
  tone: AttentionTone
  days: number
}

/**
 * The organiser's to-do lines, most urgent first, without the ones at zero.
 * Nobody on a shift is the loudest; a shift short of people comes next;
 * requests and drafts wait without alarm.
 */
export function attentionItems(a: DashboardAttention | null | undefined): AttentionItem[] {
  if (!a) return []
  const days = a.horizon_days ?? 7
  const lines: [AttentionKey, number | undefined, AttentionTone][] = [
    ['empty', a.empty_shifts_soon, 'destructive'],
    ['short', a.short_shifts_soon, 'warning'],
    ['requests', a.pending_join_requests, 'neutral'],
    ['team-requests', a.pending_team_requests, 'neutral'],
    ['drafts', a.draft_tasks, 'neutral'],
  ]
  return lines
    .filter(([, count]) => (count ?? 0) > 0)
    .map(([key, count, tone]) => ({ key, count: count!, tone, days }))
}

/** "99+" above 99, so a count square never has to grow past three characters. */
export function formatCount(n: number): string {
  return n > 99 ? '99+' : String(n)
}

/** First letter upper-cased in the given locale ("heute" → "Heute"); "" stays "". */
export function capitalizeFirst(text: string, locale: string): string {
  return text.charAt(0).toLocaleUpperCase(locale) + text.slice(1)
}

/** Minutes as hours with at most one decimal in the locale: 480 → "8", 450 → "7.5"/"7,5". */
export function hoursValue(minutes: number, locale: string): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(minutes / 60)
}

/**
 * The venue-map link for a shift, or null.
 *
 * Only when the shift has a place, the selected event has a plan to show it
 * on (`venueMapEventId` is that event's id, else null), and the shift belongs
 * to that event: the map page shows the selected event's plans, so a shift in
 * another event would open on the wrong map.
 */
export function mapLinkFor(
  shift: { event_id?: string | null; location_id?: string | null } | null | undefined,
  venueMapEventId: string | null,
): RouteLocationRaw | null {
  if (!shift?.location_id || !venueMapEventId || shift.event_id !== venueMapEventId) return null
  return {
    name: 'event-map',
    params: { eventId: venueMapEventId },
    query: { location: shift.location_id },
  }
}

/**
 * A shift in some other event than the one in view, labelled so. Your own
 * duties are listed across every event you belong to (a promise to turn up
 * should not vanish because the event switcher points elsewhere), and without
 * the name that list would silently mix two schedules together.
 */
export function foreignEventName(
  shift: { event_id?: string | null; event_name?: string | null },
  currentEventId: string | null | undefined,
): string | null {
  return shift.event_id && shift.event_id !== currentEventId ? (shift.event_name ?? null) : null
}
