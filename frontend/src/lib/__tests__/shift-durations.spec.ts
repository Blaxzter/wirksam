import { describe, expect, it } from 'vitest'

import { DURATION_OPTIONS, durationOptions } from '../shift-durations'

describe('durationOptions', () => {
  it('offers the usual lengths when the one set is among them', () => {
    expect(durationOptions(30)).toEqual(DURATION_OPTIONS)
  })

  it('adds a length set elsewhere, in order, so the dropdown can show it', () => {
    expect(durationOptions(300)).toEqual([15, 30, 45, 60, 90, 120, 180, 240, 300])
    expect(durationOptions(50)).toEqual([15, 30, 45, 50, 60, 90, 120, 180, 240])
  })

  it('ignores a length that is not set or not positive', () => {
    expect(durationOptions(undefined)).toEqual(DURATION_OPTIONS)
    expect(durationOptions(null)).toEqual(DURATION_OPTIONS)
    expect(durationOptions(0)).toEqual(DURATION_OPTIONS)
    expect(durationOptions(-30)).toEqual(DURATION_OPTIONS)
  })
})
