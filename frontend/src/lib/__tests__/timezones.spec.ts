import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  browserTimeZone,
  isSameTimeZone,
  matchesTimeZone,
  timeZoneLabel,
  timeZoneNames,
} from '../timezones'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('browserTimeZone', () => {
  it('is what the device says', () => {
    vi.spyOn(Intl.DateTimeFormat.prototype, 'resolvedOptions').mockReturnValue({
      timeZone: 'Asia/Tokyo',
    } as Intl.ResolvedDateTimeFormatOptions)
    expect(browserTimeZone()).toBe('Asia/Tokyo')
  })

  it('falls back to UTC when the device says nothing', () => {
    vi.spyOn(Intl.DateTimeFormat.prototype, 'resolvedOptions').mockReturnValue({
      timeZone: '',
    } as Intl.ResolvedDateTimeFormatOptions)
    expect(browserTimeZone()).toBe('UTC')
  })
})

describe('timeZoneNames', () => {
  it('lists the zones sorted, without duplicates, with UTC among them', () => {
    const names = timeZoneNames()
    expect(names).toContain('Asia/Tokyo')
    expect(names).toContain('UTC')
    expect(names).toEqual([...new Set(names)].sort())
  })

  it('adds a zone the browser does not list', () => {
    expect(timeZoneNames('Etc/GMT+5')).toContain('Etc/GMT+5')
  })

  it('still offers the common zones where the browser cannot list them', () => {
    vi.stubGlobal('Intl', { ...Intl, supportedValuesOf: undefined })
    const names = timeZoneNames('Europe/Vienna')
    expect(names).toContain('Europe/Lisbon')
    expect(names).toContain('Europe/Vienna')
    expect(names).toContain('UTC')
  })
})

describe('timeZoneLabel', () => {
  it('writes a name without underscores', () => {
    expect(timeZoneLabel('America/New_York')).toBe('America/New York')
    expect(timeZoneLabel('Asia/Tokyo')).toBe('Asia/Tokyo')
  })
})

describe('matchesTimeZone', () => {
  it.each([
    ['tokyo', 'Asia/Tokyo', true],
    ['  ASIA/ ', 'Asia/Tokyo', true],
    ['new york', 'America/New_York', true],
    ['new_york', 'America/New_York', true],
    ['', 'Asia/Tokyo', true],
    ['lisbon', 'Asia/Tokyo', false],
  ])('%s against %s', (query, zone, expected) => {
    expect(matchesTimeZone(zone, query)).toBe(expected)
  })
})

describe('isSameTimeZone', () => {
  it('is the same zone by name', () => {
    expect(isSameTimeZone('Asia/Tokyo', 'Asia/Tokyo')).toBe(true)
  })

  it('is the same zone under an old name', () => {
    expect(isSameTimeZone('Asia/Calcutta', 'Asia/Kolkata')).toBe(true)
  })

  it('tells two zones apart, even with the same clock', () => {
    expect(isSameTimeZone('Europe/Lisbon', 'Asia/Tokyo')).toBe(false)
  })

  it('does not fall over a name the browser does not know', () => {
    expect(isSameTimeZone('Mars/Olympus_Mons', 'Asia/Tokyo')).toBe(false)
  })
})
