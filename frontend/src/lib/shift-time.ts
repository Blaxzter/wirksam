/**
 * When a shift starts and ends, in the browser's local time.
 *
 * Mirrors `backend/app/logic/work_hours.py::shift_ends_at` and the "started"
 * rule of the shift history check, so the buttons the server would refuse
 * (booking or cancelling a shift that is over, booking a voucher shift that has
 * started) are hidden instead of offered. The server stays the authority: it
 * compares in the event's time zone, and the browser's clock is close enough
 * to decide what to show.
 *
 * Dates arrive as `YYYY-MM-DD`, times as `HH:MM` or `HH:MM:SS`, with no zone.
 */

function localDateTime(date: string, time: string | null | undefined, addDays = 0): Date {
  const [y, m, d] = date.split('-').map(Number)
  const [hh = 0, mm = 0, ss = 0] = (time ?? '00:00').split(':').map(Number)
  return new Date(y, m - 1, d + addDays, hh, mm, ss)
}

/** When a shift begins: its start time, or the start of its day without one. */
export function shiftStartsAt(date: string, start: string | null | undefined): Date {
  return localDateTime(date, start)
}

/**
 * When a shift is over. Without an end time, that is the end of its day; an
 * end at or before the start runs past midnight into the next day.
 */
export function shiftEndsAt(
  date: string,
  start: string | null | undefined,
  end: string | null | undefined,
): Date {
  if (!end) return localDateTime(date, null, 1)
  const ends = localDateTime(date, end)
  if (start && ends <= localDateTime(date, start)) return localDateTime(date, end, 1)
  return ends
}

/** The shift is over, so it can no longer be booked or cancelled. */
export function shiftHasEnded(
  date: string,
  start: string | null | undefined,
  end: string | null | undefined,
  now: Date = new Date(),
): boolean {
  return shiftEndsAt(date, start, end) <= now
}

/** The shift has begun (an untimed one at the start of its day). */
export function shiftHasStarted(
  date: string,
  start: string | null | undefined,
  now: Date = new Date(),
): boolean {
  return shiftStartsAt(date, start) <= now
}
