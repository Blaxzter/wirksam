import { describe, expect, it } from 'vitest'

import { shiftEndsAt, shiftHasEnded, shiftHasStarted, shiftStartsAt } from '@/lib/shift-time'

// Local times throughout, because that is what the helpers compare: a shift's
// wall-clock times against the browser's clock.
const at = (d: number, h: number, m = 0) => new Date(2026, 6, d, h, m)

describe('shiftEndsAt', () => {
  it('ends a timed shift at its end time', () => {
    expect(shiftEndsAt('2026-07-04', '10:00:00', '12:00:00')).toEqual(at(4, 12))
    expect(shiftEndsAt('2026-07-04', '10:00', '12:30')).toEqual(at(4, 12, 30))
  })

  it('runs an overnight shift into the next day', () => {
    expect(shiftEndsAt('2026-07-04', '22:00:00', '02:00:00')).toEqual(at(5, 2))
  })

  it('counts an end equal to the start as a whole day', () => {
    expect(shiftEndsAt('2026-07-04', '08:00:00', '08:00:00')).toEqual(at(5, 8))
  })

  it('ends a shift without an end time at the end of its day', () => {
    expect(shiftEndsAt('2026-07-04', '18:00:00', null)).toEqual(at(5, 0))
    expect(shiftEndsAt('2026-07-04', null, null)).toEqual(at(5, 0))
  })

  it('takes an end time without a start time as it is', () => {
    expect(shiftEndsAt('2026-07-04', null, '09:00:00')).toEqual(at(4, 9))
  })

  it('rolls over a month end', () => {
    expect(shiftEndsAt('2026-07-31', '22:00', '01:00')).toEqual(new Date(2026, 7, 1, 1))
  })
})

describe('shiftHasEnded', () => {
  it('is over from its end on, not before', () => {
    expect(shiftHasEnded('2026-07-04', '10:00:00', '12:00:00', at(4, 11, 59))).toBe(false)
    expect(shiftHasEnded('2026-07-04', '10:00:00', '12:00:00', at(4, 12))).toBe(true)
  })

  it('keeps an overnight shift running past midnight', () => {
    expect(shiftHasEnded('2026-07-04', '22:00:00', '02:00:00', at(5, 1))).toBe(false)
    expect(shiftHasEnded('2026-07-04', '22:00:00', '02:00:00', at(5, 2))).toBe(true)
  })

  it('keeps start-only and untimed shifts open all day', () => {
    expect(shiftHasEnded('2026-07-04', '18:00:00', null, at(4, 23, 59))).toBe(false)
    expect(shiftHasEnded('2026-07-04', null, null, at(4, 23, 59))).toBe(false)
    expect(shiftHasEnded('2026-07-04', null, null, at(5, 0))).toBe(true)
  })

  it('compares with the current time by default', () => {
    expect(shiftHasEnded('2000-01-01', '10:00', '12:00')).toBe(true)
    expect(shiftHasEnded('2999-01-01', '10:00', '12:00')).toBe(false)
  })
})

describe('shiftStartsAt / shiftHasStarted', () => {
  it('starts at the start time, or at midnight without one', () => {
    expect(shiftStartsAt('2026-07-04', '10:00:00')).toEqual(at(4, 10))
    expect(shiftStartsAt('2026-07-04', null)).toEqual(at(4, 0))
  })

  it('has started from its start on', () => {
    expect(shiftHasStarted('2026-07-04', '10:00:00', at(4, 9, 59))).toBe(false)
    expect(shiftHasStarted('2026-07-04', '10:00:00', at(4, 10))).toBe(true)
  })

  it('counts an untimed shift as started once its day has begun', () => {
    expect(shiftHasStarted('2026-07-04', null, at(3, 23, 59))).toBe(false)
    expect(shiftHasStarted('2026-07-04', undefined, at(4, 0))).toBe(true)
  })

  it('compares with the current time by default', () => {
    expect(shiftHasStarted('2000-01-01', '10:00')).toBe(true)
    expect(shiftHasStarted('2999-01-01', '10:00')).toBe(false)
  })
})
