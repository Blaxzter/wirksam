import { describe, expect, it } from 'vitest'

import {
  shiftEndsAt,
  shiftHasEnded,
  shiftHasStarted,
  shiftStartsAt,
  wallClockIn,
} from '@/lib/shift-time'

// Local times in the first blocks: without a zone, the helpers read a shift's
// wall-clock times on the browser's clock.
const at = (d: number, h: number, m = 0) => new Date(2026, 6, d, h, m)

describe('shiftEndsAt', () => {
  it('ends a timed shift at its end time', () => {
    expect(shiftEndsAt('2026-07-04', '10:00:00', '12:00:00', null)).toEqual(at(4, 12))
    expect(shiftEndsAt('2026-07-04', '10:00', '12:30', undefined)).toEqual(at(4, 12, 30))
  })

  it('runs an overnight shift into the next day', () => {
    expect(shiftEndsAt('2026-07-04', '22:00:00', '02:00:00', null)).toEqual(at(5, 2))
  })

  it('counts an end equal to the start as a whole day', () => {
    expect(shiftEndsAt('2026-07-04', '08:00:00', '08:00:00', null)).toEqual(at(5, 8))
  })

  it('ends a shift without an end time at the end of its day', () => {
    expect(shiftEndsAt('2026-07-04', '18:00:00', null, null)).toEqual(at(5, 0))
    expect(shiftEndsAt('2026-07-04', null, null, null)).toEqual(at(5, 0))
  })

  it('takes an end time without a start time as it is', () => {
    expect(shiftEndsAt('2026-07-04', null, '09:00:00', null)).toEqual(at(4, 9))
  })

  it('rolls over a month end', () => {
    expect(shiftEndsAt('2026-07-31', '22:00', '01:00', null)).toEqual(new Date(2026, 7, 1, 1))
  })
})

describe('shiftHasEnded', () => {
  it('is over from its end on, not before', () => {
    expect(shiftHasEnded('2026-07-04', '10:00:00', '12:00:00', null, at(4, 11, 59))).toBe(false)
    expect(shiftHasEnded('2026-07-04', '10:00:00', '12:00:00', null, at(4, 12))).toBe(true)
  })

  it('keeps an overnight shift running past midnight', () => {
    expect(shiftHasEnded('2026-07-04', '22:00:00', '02:00:00', null, at(5, 1))).toBe(false)
    expect(shiftHasEnded('2026-07-04', '22:00:00', '02:00:00', null, at(5, 2))).toBe(true)
  })

  it('keeps start-only and untimed shifts open all day', () => {
    expect(shiftHasEnded('2026-07-04', '18:00:00', null, null, at(4, 23, 59))).toBe(false)
    expect(shiftHasEnded('2026-07-04', null, null, null, at(4, 23, 59))).toBe(false)
    expect(shiftHasEnded('2026-07-04', null, null, null, at(5, 0))).toBe(true)
  })

  it('compares with the current time by default', () => {
    expect(shiftHasEnded('2000-01-01', '10:00', '12:00', null)).toBe(true)
    expect(shiftHasEnded('2999-01-01', '10:00', '12:00', null)).toBe(false)
  })
})

describe('shiftStartsAt / shiftHasStarted', () => {
  it('starts at the start time, or at midnight without one', () => {
    expect(shiftStartsAt('2026-07-04', '10:00:00', null)).toEqual(at(4, 10))
    expect(shiftStartsAt('2026-07-04', null, null)).toEqual(at(4, 0))
  })

  it('has started from its start on', () => {
    expect(shiftHasStarted('2026-07-04', '10:00:00', null, at(4, 9, 59))).toBe(false)
    expect(shiftHasStarted('2026-07-04', '10:00:00', null, at(4, 10))).toBe(true)
  })

  it('counts an untimed shift as started once its day has begun', () => {
    expect(shiftHasStarted('2026-07-04', null, null, at(3, 23, 59))).toBe(false)
    expect(shiftHasStarted('2026-07-04', undefined, null, at(4, 0))).toBe(true)
  })

  it('compares with the current time by default', () => {
    expect(shiftHasStarted('2000-01-01', '10:00', null)).toBe(true)
    expect(shiftHasStarted('2999-01-01', '10:00', null)).toBe(false)
  })
})

// Instants written out in UTC from here on, so these say the same on any machine.
const utc = (iso: string) => new Date(`${iso}Z`)

describe('reading a shift in its event\'s zone', () => {
  it('finds the moment a shift starts and ends, far from wherever the test runs', () => {
    // UTC+9 and UTC-7 in July: at least one of them is far from this machine.
    expect(shiftStartsAt('2026-07-04', '10:00', 'Asia/Tokyo')).toEqual(utc('2026-07-04T01:00:00'))
    expect(shiftEndsAt('2026-07-04', '10:00', '12:00', 'Asia/Tokyo')).toEqual(
      utc('2026-07-04T03:00:00'),
    )
    expect(shiftStartsAt('2026-07-04', '10:00', 'America/Los_Angeles')).toEqual(
      utc('2026-07-04T17:00:00'),
    )
  })

  it('tells a shift in Tokyo is over although it is still morning in Los Angeles', () => {
    const now = utc('2026-07-04T03:00:00')
    expect(shiftHasEnded('2026-07-04', '10:00', '12:00', 'Asia/Tokyo', now)).toBe(true)
    expect(shiftHasEnded('2026-07-04', '10:00', '12:00', 'America/Los_Angeles', now)).toBe(false)
    expect(
      shiftHasEnded('2026-07-04', '10:00', '12:00', 'Asia/Tokyo', utc('2026-07-04T02:59:00')),
    ).toBe(false)
  })

  it('tells a shift has started on its own clock', () => {
    const now = utc('2026-07-04T01:00:00')
    expect(shiftHasStarted('2026-07-04', '10:00', 'Asia/Tokyo', now)).toBe(true)
    expect(shiftHasStarted('2026-07-04', '10:00', 'America/Los_Angeles', now)).toBe(false)
    expect(
      shiftHasStarted('2026-07-04', '10:00', 'Asia/Tokyo', utc('2026-07-04T00:59:00')),
    ).toBe(false)
  })

  it('keeps the overnight and end-of-day rules', () => {
    expect(shiftEndsAt('2026-07-04', '22:00', '02:00', 'Asia/Tokyo')).toEqual(
      utc('2026-07-04T17:00:00'),
    )
    expect(shiftEndsAt('2026-07-04', '18:00', null, 'Asia/Tokyo')).toEqual(
      utc('2026-07-04T15:00:00'),
    )
    expect(shiftStartsAt('2026-07-04', null, 'Asia/Tokyo')).toEqual(utc('2026-07-03T15:00:00'))
  })

  it('takes the offset that holds on the day, whichever side of a clock change', () => {
    // Berlin goes from +1 to +2 on 2026-03-29 at 02:00.
    expect(shiftStartsAt('2026-03-29', '01:30', 'Europe/Berlin')).toEqual(
      utc('2026-03-29T00:30:00'),
    )
    expect(shiftStartsAt('2026-03-29', '03:30', 'Europe/Berlin')).toEqual(
      utc('2026-03-29T01:30:00'),
    )
    // New York goes from -5 to -4 on 2026-03-08 at 02:00.
    expect(shiftStartsAt('2026-03-08', '01:30', 'America/New_York')).toEqual(
      utc('2026-03-08T06:30:00'),
    )
    expect(shiftStartsAt('2026-03-08', '03:30', 'America/New_York')).toEqual(
      utc('2026-03-08T07:30:00'),
    )
  })

  it('reads a time the clock change skips as the same time after it', () => {
    expect(shiftStartsAt('2026-03-29', '02:30', 'Europe/Berlin')).toEqual(
      utc('2026-03-29T01:30:00'),
    )
    expect(shiftStartsAt('2026-03-08', '02:30', 'America/New_York')).toEqual(
      utc('2026-03-08T07:30:00'),
    )
  })

  it('falls back to the browser for a zone it does not know', () => {
    expect(shiftStartsAt('2026-07-04', '10:00', 'Mars/Olympus_Mons')).toEqual(at(4, 10))
  })
})

describe('wallClockIn', () => {
  it('says what date and hour it is where the shift is', () => {
    const now = utc('2026-07-04T20:30:00')
    expect(wallClockIn('Asia/Tokyo', now)).toEqual({ date: '2026-07-05', hours: 5.5 })
    expect(wallClockIn('America/Los_Angeles', now)).toEqual({ date: '2026-07-04', hours: 13.5 })
  })

  it('counts midnight as hour 0', () => {
    expect(wallClockIn('UTC', utc('2026-07-04T00:15:00'))).toEqual({
      date: '2026-07-04',
      hours: 0.25,
    })
  })

  it('reads the browser without a zone', () => {
    expect(wallClockIn(null, at(4, 9, 30))).toEqual({ date: '2026-07-04', hours: 9.5 })
  })

  it('compares with the current time by default', () => {
    expect(wallClockIn('UTC').date).toBe(new Date().toISOString().slice(0, 10))
  })
})
