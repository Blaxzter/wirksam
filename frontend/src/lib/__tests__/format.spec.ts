// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { formatDate, formatHours, initials } from '@/lib/format'
import i18n from '@/locales/i18n'

/**
 * `formatDate` is a one-liner, but the thing it delegates to —
 * `Date#toLocaleDateString(locale)` — changes its output shape with the active
 * i18n locale. These tests drive the real i18n instance (rather than mocking
 * it) so a regression in how the locale reaches `toLocaleDateString` is caught.
 *
 * Dates are written without a timezone designator on purpose: per spec a
 * date-time form with no offset is parsed as *local* time, so the calendar day
 * is the same no matter which timezone the test runner sits in.
 */
const LOCAL_NOON = '2024-03-05T12:00:00'

describe('formatDate', () => {
  const originalLocale = i18n.global.locale.value

  beforeEach(() => {
    i18n.global.locale.value = 'en'
  })

  afterEach(() => {
    i18n.global.locale.value = originalLocale
  })

  it('formats using the en locale (month first, slash separated)', () => {
    i18n.global.locale.value = 'en'

    expect(formatDate(LOCAL_NOON)).toBe('3/5/2024')
  })

  it('formats using the de locale (day first, dot separated)', () => {
    i18n.global.locale.value = 'de'

    expect(formatDate(LOCAL_NOON)).toBe('5.3.2024')
  })

  it('picks up the locale at call time, not at import time', () => {
    i18n.global.locale.value = 'en'
    const asEnglish = formatDate(LOCAL_NOON)

    i18n.global.locale.value = 'de'
    const asGerman = formatDate(LOCAL_NOON)

    expect(asEnglish).toBe('3/5/2024')
    expect(asGerman).toBe('5.3.2024')
    expect(asEnglish).not.toBe(asGerman)
  })

  it('accepts a full ISO timestamp with an offset', () => {
    i18n.global.locale.value = 'en'

    // Midday UTC stays on the same calendar day for every realistic runner TZ.
    expect(formatDate('2024-12-24T12:00:00Z')).toBe('12/24/2024')
  })

  it('accepts a date-only string', () => {
    i18n.global.locale.value = 'de'

    // Date-only strings are parsed as UTC midnight, so only the shape (and the
    // year) can be pinned without assuming the runner's timezone.
    expect(formatDate('2024-03-05')).toMatch(/^\d{1,2}\.\d{1,2}\.\d{4}$/)
    expect(formatDate('2024-03-05')).toContain('2024')
  })

  it('returns "Invalid Date" instead of throwing for an unparseable string', () => {
    i18n.global.locale.value = 'en'
    expect(() => formatDate('nonsense')).not.toThrow()
    expect(formatDate('nonsense')).toBe('Invalid Date')

    i18n.global.locale.value = 'de'
    expect(formatDate('nonsense')).toBe('Invalid Date')
  })

  it('returns "Invalid Date" for an empty string', () => {
    expect(formatDate('')).toBe('Invalid Date')
  })
})

describe('formatHours', () => {
  const originalLocale = i18n.global.locale.value

  afterEach(() => {
    i18n.global.locale.value = originalLocale
  })

  it('renders whole and fractional hours with the locale separator', () => {
    i18n.global.locale.value = 'en'
    expect(formatHours(0)).toBe('0')
    expect(formatHours(240)).toBe('4')
    expect(formatHours(450)).toBe('7.5')
    expect(formatHours(45)).toBe('0.75')

    i18n.global.locale.value = 'de'
    expect(formatHours(450)).toBe('7,5')
  })

  it('rounds to two decimals', () => {
    i18n.global.locale.value = 'en'
    expect(formatHours(10)).toBe('0.17')
  })
})

describe('initials', () => {
  it('takes the first letters of the first two words', () => {
    expect(initials('Carla Meier')).toBe('CM')
    expect(initials('anna.schmidt@example.com')).toBe('AS')
  })

  it('skips a "[DEMO]" style prefix', () => {
    expect(initials('[DEMO] Carla Meier')).toBe('CM')
  })

  it('uses two letters of a single word, and "?" for nothing', () => {
    expect(initials('Marco')).toBe('MA')
    expect(initials('')).toBe('?')
    expect(initials(null)).toBe('?')
  })
})
