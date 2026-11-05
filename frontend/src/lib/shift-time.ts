/**
 * When a shift starts and ends, as moments in time.
 *
 * Mirrors `backend/app/logic/work_hours.py::shift_ends_at` and the "started"
 * rule of the shift history check, so the buttons the server would refuse
 * (booking or cancelling a shift that is over, booking a voucher shift that has
 * started) are hidden instead of offered. The server stays the authority.
 *
 * It reads a shift's times in the zone of the shift's event, so someone far from
 * the event gets the answer the server gives. Where a read has no zone (a task
 * without an event, a write response) or the browser doesn't know the name, it
 * falls back to the browser's clock. Only the hour a clock change skips or repeats
 * can still come out differently, because the server compares wall clocks.
 *
 * Dates arrive as `YYYY-MM-DD`, times as `HH:MM` or `HH:MM:SS`, with no zone.
 */

/** An IANA name, or nothing for "read it on the browser's clock". */
export type ShiftZone = string | null | undefined

const formatters = new Map<string, Intl.DateTimeFormat | null>()

/** A formatter for `zone`, or null without one the browser can provide. */
function formatterFor(zone: ShiftZone): Intl.DateTimeFormat | null {
  if (!zone) return null
  let format = formatters.get(zone)
  if (format === undefined) {
    try {
      format = new Intl.DateTimeFormat('en-US', {
        timeZone: zone,
        hourCycle: 'h23',
        year: 'numeric',
        month: 'numeric',
        day: 'numeric',
        hour: 'numeric',
        minute: 'numeric',
        second: 'numeric',
      })
    } catch {
      format = null
    }
    formatters.set(zone, format)
  }
  return format
}

/** What the clock on the wall reads in that zone at `ms`, written as if it were UTC. */
function wallClockAt(ms: number, format: Intl.DateTimeFormat): number {
  const part: Record<string, number> = {}
  for (const { type, value } of format.formatToParts(ms)) part[type] = Number(value)
  return Date.UTC(part.year, part.month - 1, part.day, part.hour, part.minute, part.second)
}

function moment(date: string, time: string | null | undefined, zone: ShiftZone, addDays = 0): Date {
  const [y, m, d] = date.split('-').map(Number)
  const [hh = 0, mm = 0, ss = 0] = (time ?? '00:00').split(':').map(Number)
  const format = formatterFor(zone)
  if (!format) return new Date(y, m - 1, d + addDays, hh, mm, ss)

  const wall = Date.UTC(y, m - 1, d + addDays, hh, mm, ss)
  const offset = wallClockAt(wall, format) - wall
  const first = wall - offset
  const offsetThen = wallClockAt(first, format) - first
  if (offsetThen === offset) return new Date(first)
  // A clock change lies between the guess and the answer. A time it skips has
  // no moment of its own and counts as the same time after the change, as it
  // does for `new Date()`.
  const second = wall - offsetThen
  return new Date(wallClockAt(second, format) === wall ? second : Math.max(first, second))
}

/** When a shift begins: its start time, or the start of its day without one. */
export function shiftStartsAt(
  date: string,
  start: string | null | undefined,
  zone: ShiftZone,
): Date {
  return moment(date, start, zone)
}

/**
 * When a shift is over. Without an end time, that is the end of its day; an
 * end at or before the start runs past midnight into the next day.
 */
export function shiftEndsAt(
  date: string,
  start: string | null | undefined,
  end: string | null | undefined,
  zone: ShiftZone,
): Date {
  if (!end) return moment(date, null, zone, 1)
  const ends = moment(date, end, zone)
  if (start && ends <= moment(date, start, zone)) return moment(date, end, zone, 1)
  return ends
}

/** The shift is over, so it can no longer be booked or cancelled. */
export function shiftHasEnded(
  date: string,
  start: string | null | undefined,
  end: string | null | undefined,
  zone: ShiftZone,
  now: Date = new Date(),
): boolean {
  return shiftEndsAt(date, start, end, zone) <= now
}

/** The shift has begun (an untimed one at the start of its day). */
export function shiftHasStarted(
  date: string,
  start: string | null | undefined,
  zone: ShiftZone,
  now: Date = new Date(),
): boolean {
  return shiftStartsAt(date, start, zone) <= now
}

/** The date and hour it is right now where the shift is, for "today" and the day strip. */
export function wallClockIn(
  zone: ShiftZone,
  now: Date = new Date(),
): { date: string; hours: number } {
  const format = formatterFor(zone)
  // Written as UTC either way, so that the browser's own clock changes stay out of it.
  const wall = new Date(
    format
      ? wallClockAt(now.getTime(), format)
      : Date.UTC(
          now.getFullYear(),
          now.getMonth(),
          now.getDate(),
          now.getHours(),
          now.getMinutes(),
        ),
  )
  return {
    date: wall.toISOString().slice(0, 10),
    hours: wall.getUTCHours() + wall.getUTCMinutes() / 60,
  }
}
