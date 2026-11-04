import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useFormatters } from '../useFormatters'

/**
 * `useFormatters` pulls the active locale out of `vue-i18n` (which requires a
 * live component instance) and the `time_format` preference out of the Pinia
 * auth store (which drags in the session module, the router and vue-sonner).
 * Both are
 * replaced with the smallest possible stand-ins so the suite stays a pure Node
 * unit test: a mutable `state` object read through getters, so a test can flip
 * the locale / preference and then build a fresh formatter set.
 */
type TimeFormat = 'locale' | 'h12' | 'h24'
type Locale = 'en' | 'de'

const state = vi.hoisted(() => ({
  locale: 'en' as Locale,
  profile: null as { time_format?: TimeFormat } | null,
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    locale: {
      get value() {
        return state.locale
      },
    },
  }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    get profile() {
      return state.profile
    },
  }),
}))

function setup(opts: { locale?: Locale; profile?: { time_format?: TimeFormat } | null } = {}) {
  state.locale = opts.locale ?? 'en'
  state.profile = opts.profile ?? null
  return useFormatters()
}

/** U+2013, the separator the composable itself uses between start and end. */
const DASH = '–'

/**
 * ICU emits either a plain space or U+202F (narrow no-break space) in front of
 * AM/PM depending on the CLDR version bundled with the running Node build.
 * Normalising keeps the assertions exact without pinning an ICU release.
 */
const norm = (s: string) => s.replace(/[\u202f\u00a0]/g, ' ')

/**
 * `formatDate` feeds the raw string to `new Date(...)`, so a bare `YYYY-MM-DD`
 * is parsed as UTC midnight and then rendered in the runner's local zone — the
 * calendar day can therefore differ from the input west of Greenwich. Building
 * the expectation from the same instant's *local* fields keeps the assertion
 * timezone-agnostic while still pinning the locale's field order and
 * separators exactly.
 */
function expectedDate(locale: Locale, input: string): string {
  const d = new Date(input)
  return locale === 'en'
    ? `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear()}`
    : `${d.getDate()}.${d.getMonth() + 1}.${d.getFullYear()}`
}

beforeEach(() => {
  state.locale = 'en'
  state.profile = null
})

describe('useFormatters', () => {
  describe('hour12', () => {
    it('is undefined when there is no profile at all', () => {
      expect(setup().hour12.value).toBeUndefined()
    })

    it('is undefined when the profile carries no time_format', () => {
      expect(setup({ profile: {} }).hour12.value).toBeUndefined()
    })

    it("is undefined for the 'locale' preference, deferring to the locale", () => {
      expect(setup({ profile: { time_format: 'locale' } }).hour12.value).toBeUndefined()
    })

    it("is true for the 'h12' preference", () => {
      expect(setup({ profile: { time_format: 'h12' } }).hour12.value).toBe(true)
    })

    it("is false for the 'h24' preference", () => {
      expect(setup({ profile: { time_format: 'h24' } }).hour12.value).toBe(false)
    })
  })

  describe('formatTime', () => {
    it('renders en as a 12-hour clock by default', () => {
      const { formatTime } = setup({ locale: 'en' })
      expect(norm(formatTime('14:30'))).toBe('02:30 PM')
      expect(norm(formatTime('09:05'))).toBe('09:05 AM')
      expect(norm(formatTime('00:00'))).toBe('12:00 AM')
      expect(norm(formatTime('23:59'))).toBe('11:59 PM')
    })

    it('renders de as a 24-hour clock by default', () => {
      const { formatTime } = setup({ locale: 'de' })
      expect(formatTime('14:30')).toBe('14:30')
      expect(formatTime('09:05')).toBe('09:05')
      expect(formatTime('00:00')).toBe('00:00')
      expect(formatTime('23:59')).toBe('23:59')
    })

    it("forces a 24-hour clock on en when the preference is 'h24'", () => {
      const { formatTime } = setup({ locale: 'en', profile: { time_format: 'h24' } })
      expect(formatTime('14:30')).toBe('14:30')
      expect(formatTime('09:05')).toBe('09:05')
      expect(formatTime('00:00')).toBe('00:00')
    })

    it("forces a 12-hour clock on de when the preference is 'h12'", () => {
      const { formatTime } = setup({ locale: 'de', profile: { time_format: 'h12' } })
      expect(norm(formatTime('14:30'))).toBe('02:30 PM')
      expect(norm(formatTime('00:00'))).toBe('12:00 AM')
    })

    it("leaves the locale in charge for the 'locale' preference", () => {
      expect(
        norm(setup({ locale: 'en', profile: { time_format: 'locale' } }).formatTime('14:30')),
      ).toBe('02:30 PM')
      expect(setup({ locale: 'de', profile: { time_format: 'locale' } }).formatTime('14:30')).toBe(
        '14:30',
      )
    })

    it('drops the seconds component of an HH:mm:ss input', () => {
      expect(setup({ locale: 'de' }).formatTime('14:30:45')).toBe('14:30')
      expect(norm(setup({ locale: 'en' }).formatTime('14:30:45'))).toBe('02:30 PM')
    })

    it('returns an empty string for null, undefined and empty input', () => {
      const { formatTime } = setup({ locale: 'de' })
      expect(formatTime(null)).toBe('')
      expect(formatTime(undefined)).toBe('')
      expect(formatTime('')).toBe('')
    })

    it('returns an empty string when the hour is not a number', () => {
      const { formatTime } = setup({ locale: 'de' })
      expect(formatTime('abc')).toBe('')
      expect(formatTime('not-a-time')).toBe('')
    })

    it('does not range-check the hour — 25:00 rolls over into the next day', () => {
      expect(setup({ locale: 'de' }).formatTime('25:00')).toBe('01:00')
    })
  })

  describe('formatTimeRange', () => {
    it('joins both ends with an en dash (en)', () => {
      const { formatTimeRange } = setup({ locale: 'en' })
      expect(norm(formatTimeRange('14:30', '16:00'))).toBe(`02:30 PM ${DASH} 04:00 PM`)
    })

    it('joins both ends with an en dash (de)', () => {
      const { formatTimeRange } = setup({ locale: 'de' })
      expect(formatTimeRange('14:30', '16:00')).toBe(`14:30 ${DASH} 16:00`)
    })

    it('renders a start-only range as the bare start time', () => {
      const { formatTimeRange } = setup({ locale: 'de' })
      expect(formatTimeRange('14:30', null)).toBe('14:30')
      expect(formatTimeRange('14:30', undefined)).toBe('14:30')
      expect(formatTimeRange('14:30', '')).toBe('14:30')
    })

    it('prefixes an end-only range with a leading dash', () => {
      const { formatTimeRange } = setup({ locale: 'de' })
      expect(formatTimeRange(null, '16:00')).toBe(`${DASH} 16:00`)
      expect(formatTimeRange('', '16:00')).toBe(`${DASH} 16:00`)
    })

    it('returns an empty string when neither end is given', () => {
      const { formatTimeRange } = setup({ locale: 'de' })
      expect(formatTimeRange(null, null)).toBe('')
      expect(formatTimeRange(undefined, undefined)).toBe('')
      expect(formatTimeRange('', '')).toBe('')
    })

    it('collapses to an empty string when both ends are unparseable', () => {
      expect(setup({ locale: 'de' }).formatTimeRange('abc', 'def')).toBe('')
    })
  })

  describe('formatDateLabel', () => {
    it('renders the default weekday/month/day label in en', () => {
      expect(setup({ locale: 'en' }).formatDateLabel('2026-03-15')).toBe('Sun, Mar 15')
    })

    it('renders the default weekday/month/day label in de', () => {
      expect(setup({ locale: 'de' }).formatDateLabel('2026-03-15')).toBe('So., 15. März')
    })

    it('honours custom Intl options in en', () => {
      const { formatDateLabel } = setup({ locale: 'en' })
      expect(
        formatDateLabel('2026-03-15', {
          weekday: 'long',
          year: 'numeric',
          month: 'long',
          day: 'numeric',
        }),
      ).toBe('Sunday, March 15, 2026')
    })

    it('honours custom Intl options in de', () => {
      const { formatDateLabel } = setup({ locale: 'de' })
      expect(
        formatDateLabel('2026-03-15', {
          weekday: 'long',
          year: 'numeric',
          month: 'long',
          day: 'numeric',
        }),
      ).toBe('Sonntag, 15. März 2026')
    })

    it('anchors the date at local midnight so the day never shifts', () => {
      expect(setup({ locale: 'en' }).formatDateLabel('2026-01-01')).toBe('Thu, Jan 1')
      expect(setup({ locale: 'de' }).formatDateLabel('2026-01-01')).toBe('Do., 1. Jan.')
    })
  })

  describe('formatDate', () => {
    it('uses slash-separated M/D/Y in en and dot-separated D.M.Y in de', () => {
      expect(setup({ locale: 'en' }).formatDate('2026-03-15T12:00:00')).toBe('3/15/2026')
      expect(setup({ locale: 'de' }).formatDate('2026-03-15T12:00:00')).toBe('15.3.2026')
    })

    it('diverges on the separator between the two locales', () => {
      const en = setup({ locale: 'en' }).formatDate('2026-03-15T12:00:00')
      const de = setup({ locale: 'de' }).formatDate('2026-03-15T12:00:00')
      expect(en).toContain('/')
      expect(en).not.toContain('.')
      expect(de).toContain('.')
      expect(de).not.toContain('/')
      expect(en).not.toBe(de)
    })

    it('does not zero-pad single-digit months or days', () => {
      expect(setup({ locale: 'en' }).formatDate('2026-12-01T12:00:00')).toBe('12/1/2026')
      expect(setup({ locale: 'de' }).formatDate('2026-12-01T12:00:00')).toBe('1.12.2026')
    })

    it('accepts a date-only string', () => {
      expect(setup({ locale: 'en' }).formatDate('2026-03-15')).toBe(
        expectedDate('en', '2026-03-15'),
      )
      expect(setup({ locale: 'de' }).formatDate('2026-03-15')).toBe(
        expectedDate('de', '2026-03-15'),
      )
    })

    it("renders 'Invalid Date' for unparseable input", () => {
      expect(setup({ locale: 'en' }).formatDate('not-a-date')).toBe('Invalid Date')
    })
  })

  describe('formatDaySpan', () => {
    // The year shows only outside the current one, so "now" is pinned.
    beforeEach(() => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date(2026, 2, 15, 12, 0, 0))
      return () => vi.useRealTimers()
    })

    const dashless = (s: string) => s.replace(/[   ]/g, ' ')

    it('gives the days of one month once, with the month at the end (de)', () => {
      expect(setup({ locale: 'de' }).formatDaySpan('2026-07-17', '2026-07-19')).toBe('17.–19. Juli')
    })

    it('names both months when the span crosses one (en)', () => {
      expect(dashless(setup({ locale: 'en' }).formatDaySpan('2026-07-17', '2026-08-02'))).toBe(
        'July 17 – August 2',
      )
    })

    it('adds the year when either end is not in this year', () => {
      expect(dashless(setup({ locale: 'de' }).formatDaySpan('2026-12-30', '2027-01-02'))).toBe(
        '30. Dezember 2026 – 2. Januar 2027',
      )
    })

    it('gives one day for a one-day span, a missing end or an end before the start', () => {
      const { formatDaySpan } = setup({ locale: 'de' })
      expect(formatDaySpan('2026-07-17', '2026-07-17')).toBe('17. Juli')
      expect(formatDaySpan('2026-07-17')).toBe('17. Juli')
      expect(formatDaySpan('2026-07-17', null)).toBe('17. Juli')
      expect(formatDaySpan('2026-07-17', '2026-07-10')).toBe('17. Juli')
    })

    it('renders nothing without a start or for unparseable input', () => {
      const { formatDaySpan } = setup({ locale: 'en' })
      expect(formatDaySpan(null)).toBe('')
      expect(formatDaySpan(undefined, '2026-07-19')).toBe('')
      expect(formatDaySpan('not-a-date', '2026-07-19')).toBe('')
    })
  })

  describe('formatRelativeDay', () => {
    /**
     * Every assertion here is relative to "now", so the clock is pinned. Local
     * noon rather than a UTC instant: the function compares local midnights,
     * and a UTC-midnight fake would land on the previous day west of
     * Greenwich and shift every expectation by one.
     */
    beforeEach(() => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date(2026, 2, 15, 12, 0, 0))
      return () => vi.useRealTimers()
    })

    it('names the days either side of today in words', () => {
      const { formatRelativeDay } = setup({ locale: 'en' })
      expect(formatRelativeDay('2026-03-15')).toBe('today')
      expect(formatRelativeDay('2026-03-16')).toBe('tomorrow')
      expect(formatRelativeDay('2026-03-14')).toBe('yesterday')
    })

    it('translates those words with the locale', () => {
      const { formatRelativeDay } = setup({ locale: 'de' })
      expect(formatRelativeDay('2026-03-15')).toBe('heute')
      expect(formatRelativeDay('2026-03-16')).toBe('morgen')
    })

    it('counts the days out to the end of the week', () => {
      const { formatRelativeDay } = setup({ locale: 'en' })
      expect(formatRelativeDay('2026-03-18')).toBe('in 3 days')
      expect(formatRelativeDay('2026-03-21')).toBe('in 6 days')
    })

    it('hands over to a plain date once counting stops helping', () => {
      const { formatRelativeDay, formatDateLabel } = setup({ locale: 'en' })
      expect(formatRelativeDay('2026-03-24')).toBe(formatDateLabel('2026-03-24'))
      expect(formatRelativeDay('2026-03-01')).toBe(formatDateLabel('2026-03-01'))
    })

    it('passes custom date options through to the fallback', () => {
      const { formatRelativeDay, formatDateLabel } = setup({ locale: 'en' })
      const options: Intl.DateTimeFormatOptions = { month: 'long', day: 'numeric' }
      expect(formatRelativeDay('2026-03-24', options)).toBe(formatDateLabel('2026-03-24', options))
    })

    it('renders nothing for unparseable input', () => {
      expect(setup({ locale: 'en' }).formatRelativeDay('not-a-date')).toBe('')
    })
  })

  describe('formatDateWithTime', () => {
    it('returns the bare date when no times are attached', () => {
      const { formatDateWithTime } = setup({ locale: 'en' })
      expect(formatDateWithTime({ slot_date: '2026-03-15' })).toBe(expectedDate('en', '2026-03-15'))
      expect(
        formatDateWithTime({ slot_date: '2026-03-15', start_time: null, end_time: null }),
      ).toBe(expectedDate('en', '2026-03-15'))
      expect(formatDateWithTime({ slot_date: '2026-03-15', start_time: '', end_time: '' })).toBe(
        expectedDate('en', '2026-03-15'),
      )
    })

    it('appends both times in parentheses (en, 12-hour)', () => {
      const { formatDateWithTime } = setup({ locale: 'en' })
      expect(
        norm(
          formatDateWithTime({ slot_date: '2026-03-15', start_time: '14:30', end_time: '16:00' }),
        ),
      ).toBe(`${expectedDate('en', '2026-03-15')} (02:30 PM ${DASH} 04:00 PM)`)
    })

    it('appends both times in parentheses (de, 24-hour)', () => {
      const { formatDateWithTime } = setup({ locale: 'de' })
      expect(
        formatDateWithTime({ slot_date: '2026-03-15', start_time: '14:30', end_time: '16:00' }),
      ).toBe(`${expectedDate('de', '2026-03-15')} (14:30 ${DASH} 16:00)`)
    })

    it('appends a lone start time without a trailing dash', () => {
      const { formatDateWithTime } = setup({ locale: 'de' })
      expect(formatDateWithTime({ slot_date: '2026-03-15', start_time: '14:30' })).toBe(
        `${expectedDate('de', '2026-03-15')} (14:30)`,
      )
    })

    it('appends a lone end time without the leading dash formatTimeRange would add', () => {
      const { formatDateWithTime } = setup({ locale: 'de' })
      expect(formatDateWithTime({ slot_date: '2026-03-15', end_time: '16:00' })).toBe(
        `${expectedDate('de', '2026-03-15')} (16:00)`,
      )
    })

    it("respects the 'h24' preference on en", () => {
      const { formatDateWithTime } = setup({ locale: 'en', profile: { time_format: 'h24' } })
      expect(
        formatDateWithTime({ slot_date: '2026-03-15', start_time: '14:30', end_time: '16:00' }),
      ).toBe(`${expectedDate('en', '2026-03-15')} (14:30 ${DASH} 16:00)`)
    })
  })

  describe('formatDateTime', () => {
    it('renders the default month/day plus a 12-hour time in en', () => {
      expect(norm(setup({ locale: 'en' }).formatDateTime('2026-03-15T14:30:00'))).toBe(
        'Mar 15, 02:30 PM',
      )
    })

    it('renders the default month/day plus a 24-hour time in de', () => {
      expect(setup({ locale: 'de' }).formatDateTime('2026-03-15T14:30:00')).toBe('15. März, 14:30')
    })

    it("forces a 24-hour time on en for the 'h24' preference", () => {
      expect(
        setup({ locale: 'en', profile: { time_format: 'h24' } }).formatDateTime(
          '2026-03-15T14:30:00',
        ),
      ).toBe('Mar 15, 14:30')
    })

    it("forces a 12-hour time on de for the 'h12' preference", () => {
      expect(
        norm(
          setup({ locale: 'de', profile: { time_format: 'h12' } }).formatDateTime(
            '2026-03-15T14:30:00',
          ),
        ),
      ).toBe('15. März, 02:30 PM')
    })

    it('merges custom Intl options with the always-on time fields (en)', () => {
      const { formatDateTime } = setup({ locale: 'en' })
      expect(
        norm(
          formatDateTime('2026-03-15T14:30:00', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
          }),
        ),
      ).toBe('March 15, 2026 at 02:30 PM')
    })

    it('merges custom Intl options with the always-on time fields (de)', () => {
      const { formatDateTime } = setup({ locale: 'de' })
      expect(
        formatDateTime('2026-03-15T14:30:00', {
          year: 'numeric',
          month: 'long',
          day: 'numeric',
        }),
      ).toBe('15. März 2026 um 14:30')
    })

    it("renders 'Invalid Date' for unparseable input", () => {
      expect(setup({ locale: 'en' }).formatDateTime('nonsense')).toBe('Invalid Date')
    })
  })
})
