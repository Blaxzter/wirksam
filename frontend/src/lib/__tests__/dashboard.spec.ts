import { describe, expect, it } from 'vitest'

import {
  attentionItems,
  calendarDaysBetween,
  capitalizeFirst,
  dayOffset,
  dayStrip,
  endedShiftsKey,
  eventDay,
  fillPercent,
  foreignEventName,
  formatCount,
  greetingBucket,
  greetingName,
  groupByDay,
  hiddenCount,
  hoursValue,
  localIsoDate,
  mapLinkFor,
  nextUnfinished,
  shiftCountdown,
  shiftHeadline,
  twelveHourFormatter,
  upcomingToday,
  voucherShiftsDueKey,
} from '@/lib/dashboard'

/**
 * Dates are built from local parts (`new Date(2026, 6, 18, 11, 45)`), never
 * from ISO strings with a zone, so "today" is the same calendar day wherever
 * the runner sits. July 18th 2026 is a Saturday, the artboards' festival day.
 */
const at = (h: number, m = 0, s = 0, day = 18) => new Date(2026, 6, day, h, m, s)

describe('calendar days', () => {
  it('writes a local date with padded month and day', () => {
    expect(localIsoDate(new Date(2026, 0, 5, 23, 59))).toBe('2026-01-05')
    expect(localIsoDate(at(0))).toBe('2026-07-18')
  })

  it('counts whole days forwards and backwards', () => {
    expect(calendarDaysBetween('2026-07-17', '2026-07-19')).toBe(2)
    expect(calendarDaysBetween('2026-07-19', '2026-07-17')).toBe(-2)
    expect(calendarDaysBetween('2026-07-18', '2026-07-18')).toBe(0)
  })

  it('is not thrown off by the March clock change', () => {
    expect(calendarDaysBetween('2026-03-28', '2026-03-30')).toBe(2)
  })

  it('measures from today', () => {
    expect(dayOffset('2026-07-17', at(11))).toBe(-1)
    expect(dayOffset('2026-07-18', at(11))).toBe(0)
    expect(dayOffset('2026-07-19', at(23, 59))).toBe(1)
  })
})

describe('greetingBucket', () => {
  it.each([
    [4, 59, 'evening'],
    [5, 0, 'morning'],
    [11, 59, 'morning'],
    [12, 0, 'afternoon'],
    [17, 59, 'afternoon'],
    [18, 0, 'evening'],
    [23, 30, 'evening'],
  ] as const)('%i:%i is %s', (h, m, bucket) => {
    expect(greetingBucket(at(h, m))).toBe(bucket)
  })
})

describe('greetingName', () => {
  it('has nobody to greet without a profile', () => {
    expect(greetingName(null)).toBeNull()
    expect(greetingName(undefined)).toBeNull()
  })

  it('does not greet a sandbox guest by their placeholder name', () => {
    expect(greetingName({ name: 'Demo visitor', is_sandbox: true })).toBeNull()
  })

  it('prefers a trimmed nickname', () => {
    expect(greetingName({ name: 'Alexandra Weber', nickname: '  Alex ' })).toBe('Alex')
  })

  it('falls back to the first name when the nickname is blank', () => {
    expect(greetingName({ name: 'Alexandra Weber', nickname: '   ' })).toBe('Alexandra')
    expect(greetingName({ name: '[DEMO] Carla Meier', nickname: null })).toBe('Carla')
  })

  it('gives up on an empty name or an email address', () => {
    expect(greetingName({ name: '' })).toBeNull()
    expect(greetingName({})).toBeNull()
    expect(greetingName({ name: 'anna@example.org' })).toBeNull()
  })
})

describe('eventDay', () => {
  const festival = { start_date: '2026-07-17', end_date: '2026-07-19' }

  it('counts the days of a running event', () => {
    expect(eventDay(festival, at(9, 0, 0, 17))).toEqual({ day: 1, total: 3 })
    expect(eventDay(festival, at(9))).toEqual({ day: 2, total: 3 })
    expect(eventDay(festival, at(23, 59, 0, 19))).toEqual({ day: 3, total: 3 })
  })

  it('says nothing before or after the event', () => {
    expect(eventDay(festival, at(9, 0, 0, 16))).toBeNull()
    expect(eventDay(festival, at(0, 0, 0, 20))).toBeNull()
  })

  it('says nothing for a one-day event or without one', () => {
    expect(eventDay({ start_date: '2026-07-18', end_date: '2026-07-18' }, at(9))).toBeNull()
    expect(eventDay(null, at(9))).toBeNull()
  })
})

describe('shiftCountdown', () => {
  const cafe = { date: '2026-07-18', start_time: '14:00', end_time: '17:00' }

  it('counts down to a shift later today', () => {
    expect(shiftCountdown(cafe, at(11, 45))).toEqual({ kind: 'startsIn', hours: 2, minutes: 15 })
    expect(shiftCountdown(cafe, at(13, 20))).toEqual({ kind: 'startsIn', hours: 0, minutes: 40 })
    expect(shiftCountdown(cafe, at(12, 0))).toEqual({ kind: 'startsIn', hours: 2, minutes: 0 })
  })

  it('rounds part of a minute up', () => {
    expect(shiftCountdown(cafe, at(11, 45, 30))).toEqual({
      kind: 'startsIn',
      hours: 2,
      minutes: 15,
    })
  })

  it('is running between start and end, and over at the end', () => {
    expect(shiftCountdown(cafe, at(14, 30))).toEqual({ kind: 'running' })
    expect(shiftCountdown(cafe, at(17, 0))).toEqual({ kind: 'over' })
  })

  it('names the day for a shift on another day', () => {
    expect(shiftCountdown({ ...cafe, date: '2026-07-19' }, at(11, 45))).toEqual({ kind: 'day' })
  })

  it('never runs an untimed shift, only ends it with its day', () => {
    expect(shiftCountdown({ date: '2026-07-18' }, at(11, 45))).toEqual({ kind: 'day' })
    expect(shiftCountdown({ date: '2026-07-17' }, at(11, 45))).toEqual({ kind: 'over' })
  })

  it('runs a shift without an end until midnight', () => {
    const open = { date: '2026-07-18', start_time: '14:00', end_time: null }
    expect(shiftCountdown(open, at(23, 30))).toEqual({ kind: 'running' })
    expect(shiftCountdown(open, at(0, 0, 0, 19))).toEqual({ kind: 'over' })
  })

  it('keeps an overnight shift running past midnight', () => {
    const night = { date: '2026-07-17', start_time: '22:00', end_time: '02:00' }
    expect(shiftCountdown(night, at(1, 0))).toEqual({ kind: 'running' })
    expect(shiftCountdown(night, at(2, 0))).toEqual({ kind: 'over' })
  })
})

describe('finished shifts', () => {
  const plan = [
    { booking_id: 'b1', date: '2026-07-18', start_time: '09:00', end_time: '11:00' },
    { booking_id: 'b2', date: '2026-07-18', start_time: '14:00', end_time: '17:00' },
    { booking_id: 'b3', date: '2026-07-19', start_time: null, end_time: null },
  ]

  it('takes the first shift that is not over, a running one included', () => {
    expect(nextUnfinished(plan, at(8))?.booking_id).toBe('b1')
    expect(nextUnfinished(plan, at(10))?.booking_id).toBe('b1')
    expect(nextUnfinished(plan, at(11))?.booking_id).toBe('b2')
    expect(nextUnfinished(plan, at(18))?.booking_id).toBe('b3')
    expect(nextUnfinished(plan, at(0, 0, 0, 20))).toBeNull()
    expect(nextUnfinished([], at(8))).toBeNull()
  })

  it('keys the shifts that are over, so a watcher fires once per shift', () => {
    expect(endedShiftsKey(plan, at(10, 59))).toBe('')
    expect(endedShiftsKey(plan, at(11))).toBe('b1')
    expect(endedShiftsKey(plan, at(17, 30))).toBe('b1,b2')
  })
})

describe('voucherShiftsDueKey', () => {
  // `ends_at` is naive UTC, so `now` is built in UTC as well.
  const utc = (h: number, m = 0) => new Date(Date.UTC(2026, 6, 18, h, m))
  const shifts = [
    { booking_id: 'b1', ends_at: '2026-07-18T10:00:00', completed: false },
    { booking_id: 'b2', ends_at: '2026-07-18T08:00:00', completed: true },
    { booking_id: 'b3', ends_at: '2026-07-18T15:00:00', completed: false },
    { booking_id: 'b4', ends_at: 'not a date', completed: false },
  ]

  it('lists what has ended by now but still counts as to come', () => {
    expect(voucherShiftsDueKey(shifts, utc(9, 59))).toBe('')
    expect(voucherShiftsDueKey(shifts, utc(10))).toBe('b1')
    expect(voucherShiftsDueKey(shifts, utc(16))).toBe('b1,b3')
  })

  it('leaves out what the account already counts as earned', () => {
    expect(voucherShiftsDueKey(shifts, utc(23))).not.toContain('b2')
  })
})

describe('twelveHourFormatter', () => {
  const at3pm = new Date(2000, 0, 1, 15)

  it('follows the locale when the user has not chosen', () => {
    expect(twelveHourFormatter('en', undefined)?.format(at3pm)).toMatch(/^3\sPM$/)
    expect(twelveHourFormatter('de', undefined)).toBeNull()
  })

  it('follows the user when they have', () => {
    expect(twelveHourFormatter('en', false)).toBeNull()
    expect(twelveHourFormatter('de', true)).not.toBeNull()
  })
})

describe('dayStrip', () => {
  const cafe = { date: '2026-07-18', start_time: '14:00', end_time: '17:00' }

  it('draws nothing without both times', () => {
    expect(dayStrip({ date: '2026-07-18', start_time: '14:00' }, at(9))).toBeNull()
    expect(dayStrip({ date: '2026-07-18', end_time: '17:00' }, at(9))).toBeNull()
  })

  it('places the shift on an 8 to 24 window', () => {
    const strip = dayStrip(cafe, at(9, 0, 0, 17))!
    expect(strip.startHour).toBe(8)
    expect(strip.endHour).toBe(24)
    expect(strip.block).toEqual({ left: 37.5, width: 18.75 })
    expect(strip.nowAt).toBeNull()
    expect(strip.ticks).toEqual([
      { hour: 8, at: 0, edge: 'start' },
      { hour: 12, at: 25, edge: null },
      { hour: 16, at: 50, edge: null },
      { hour: 20, at: 75, edge: null },
      { hour: 24, at: 100, edge: 'end' },
    ])
  })

  it('marks now on the day of the shift', () => {
    expect(dayStrip(cafe, at(11, 45))!.nowAt).toBe(23.44)
  })

  it('opens the window earlier for an early shift', () => {
    const strip = dayStrip({ date: '2026-07-19', start_time: '05:30', end_time: '08:00' }, at(9))!
    expect(strip.startHour).toBe(5)
    expect(strip.ticks.map((t) => t.hour)).toEqual([5, 8, 12, 16, 20, 24])
  })

  it('opens the window earlier for an early look at the page', () => {
    const strip = dayStrip(cafe, at(6, 30))!
    expect(strip.startHour).toBe(6)
    expect(strip.nowAt).not.toBeNull()
  })

  it('drops a tick that would crowd the start label', () => {
    const strip = dayStrip({ date: '2026-07-19', start_time: '07:00', end_time: '09:00' }, at(9))!
    expect(strip.ticks.map((t) => t.hour)).toEqual([7, 12, 16, 20, 24])
  })

  it('stops an overnight shift at midnight', () => {
    const strip = dayStrip({ date: '2026-07-19', start_time: '22:00', end_time: '02:00' }, at(9))!
    expect(strip.block.width).toBe(12.5)
    expect(strip.block.left).toBe(87.5)
  })
})

describe('shiftHeadline', () => {
  it('drops the time range from a generated title, and with it the job line', () => {
    expect(shiftHeadline('Cafétheke 14:00-17:00', 'Cafétheke')).toEqual({
      headline: 'Cafétheke',
      taskLine: null,
    })
    expect(shiftHeadline('Cafétheke 14:00 – 17:00', 'Cafétheke').headline).toBe('Cafétheke')
  })

  it('names the job under a title written by hand', () => {
    expect(shiftHeadline('Welcome desk, early', 'Empfang')).toEqual({
      headline: 'Welcome desk, early',
      taskLine: 'Empfang',
    })
  })

  it('keeps a title that is nothing but times', () => {
    expect(shiftHeadline('14:00-17:00', 'Bar').headline).toBe('14:00-17:00')
  })
})

describe('small numbers', () => {
  it('fills a bar from taken and capacity', () => {
    expect(fillPercent(1, 3)).toBe(33)
    expect(fillPercent(0, 2)).toBe(0)
    expect(fillPercent(3, 3)).toBe(100)
    expect(fillPercent(4, 3)).toBe(100)
    expect(fillPercent(-1, 3)).toBe(0)
    expect(fillPercent(1, 0)).toBe(0)
  })

  it('counts what a list held back', () => {
    expect(hiddenCount(10, 6)).toBe(4)
    expect(hiddenCount(3, 6)).toBe(0)
  })

  it('caps a count at 99+', () => {
    expect(formatCount(5)).toBe('5')
    expect(formatCount(99)).toBe('99')
    expect(formatCount(100)).toBe('99+')
  })

  it('writes hours with at most one decimal in the locale', () => {
    expect(hoursValue(480, 'en')).toBe('8')
    expect(hoursValue(450, 'en')).toBe('7.5')
    expect(hoursValue(450, 'de')).toBe('7,5')
    expect(hoursValue(500, 'en')).toBe('8.3')
  })

  it('capitalises the first letter only', () => {
    expect(capitalizeFirst('heute', 'de')).toBe('Heute')
    expect(capitalizeFirst('in 3 days', 'en')).toBe('In 3 days')
    expect(capitalizeFirst('', 'en')).toBe('')
  })
})

describe('groupByDay', () => {
  it('groups by date in first-seen order with offsets', () => {
    const items = [
      { id: 'a', date: '2026-07-18' },
      { id: 'b', date: '2026-07-19' },
      { id: 'c', date: '2026-07-18' },
    ]
    expect(groupByDay(items, at(9))).toEqual([
      { date: '2026-07-18', offset: 0, items: [items[0], items[2]] },
      { date: '2026-07-19', offset: 1, items: [items[1]] },
    ])
  })

  it('has no days for no items', () => {
    expect(groupByDay([], at(9))).toEqual([])
  })
})

describe('attentionItems', () => {
  it('has nothing without an attention block', () => {
    expect(attentionItems(null)).toEqual([])
    expect(attentionItems(undefined)).toEqual([])
  })

  it('lists all five in order of urgency, with their tones', () => {
    const items = attentionItems({
      empty_shifts_soon: 2,
      short_shifts_soon: 5,
      pending_join_requests: 1,
      pending_team_requests: 3,
      draft_tasks: 4,
      horizon_days: 14,
    })
    expect(items).toEqual([
      { key: 'empty', count: 2, tone: 'destructive', days: 14 },
      { key: 'short', count: 5, tone: 'warning', days: 14 },
      { key: 'requests', count: 1, tone: 'neutral', days: 14 },
      { key: 'team-requests', count: 3, tone: 'neutral', days: 14 },
      { key: 'drafts', count: 4, tone: 'neutral', days: 14 },
    ])
  })

  it('drops zeros and missing counts, and assumes a week', () => {
    expect(attentionItems({ empty_shifts_soon: 0, short_shifts_soon: 3 })).toEqual([
      { key: 'short', count: 3, tone: 'warning', days: 7 },
    ])
  })
})

describe('upcomingToday', () => {
  it('sums the vouchers of today’s shifts that are still to come', () => {
    const shifts = [
      { date: '2026-07-18', completed: false, vouchers: 2 },
      { date: '2026-07-18', completed: false, vouchers: 1 },
      { date: '2026-07-18', completed: true, vouchers: 2 },
      { date: '2026-07-18', completed: false, vouchers: 0 },
      { date: '2026-07-19', completed: false, vouchers: 2 },
    ]
    expect(upcomingToday(shifts, at(9))).toEqual({ vouchers: 3, shifts: 2 })
  })

  it('is zero with nothing today', () => {
    expect(upcomingToday([], at(9))).toEqual({ vouchers: 0, shifts: 0 })
  })
})

describe('mapLinkFor', () => {
  const shift = { event_id: 'e1', location_id: 'loc1' }

  it('links to the place on the selected event’s map', () => {
    expect(mapLinkFor(shift, 'e1')).toEqual({
      name: 'event-map',
      params: { eventId: 'e1' },
      query: { location: 'loc1' },
    })
  })

  it('has no link without a shift, a place, a map, or for another event', () => {
    expect(mapLinkFor(null, 'e1')).toBeNull()
    expect(mapLinkFor({ event_id: 'e1', location_id: null }, 'e1')).toBeNull()
    expect(mapLinkFor(shift, null)).toBeNull()
    expect(mapLinkFor({ event_id: 'e2', location_id: 'loc1' }, 'e1')).toBeNull()
  })
})

describe('foreignEventName', () => {
  it('names only another event', () => {
    expect(foreignEventName({ event_id: 'e1', event_name: 'Fest' }, 'e1')).toBeNull()
    expect(foreignEventName({ event_id: 'e2', event_name: 'Markt' }, 'e1')).toBe('Markt')
    expect(foreignEventName({ event_id: 'e2', event_name: null }, 'e1')).toBeNull()
    expect(foreignEventName({ event_id: null, event_name: 'Fest' }, 'e1')).toBeNull()
  })
})
