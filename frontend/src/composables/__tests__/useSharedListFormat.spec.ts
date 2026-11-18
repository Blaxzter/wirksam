// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSharedListFormat } from '@/composables/useSharedListFormat'

import i18n from '@/locales/i18n'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ profile: { time_format: 'h24' } }),
}))

/** How the wizard writes days and times: read as written, in the viewer's language. */

function setup() {
  let format!: ReturnType<typeof useSharedListFormat>
  mount(
    defineComponent({
      setup() {
        format = useSharedListFormat()
        return () => null
      },
    }),
    { global: { plugins: [i18n] } },
  )
  return format
}

beforeEach(() => {
  i18n.global.locale.value = 'de'
})

describe('useSharedListFormat', () => {
  it('writes one day short and long', () => {
    const { shortDay, longDay } = setup()
    expect(shortDay('2026-12-05')).toBe('Sa., 5.12.')
    expect(longDay('2026-12-05')).toBe('Samstag, 5. Dezember')
  })

  it('writes a shift’s times on the 24-hour clock asked for, and nothing without them', () => {
    const { timeRange, formatTime } = setup()
    expect(timeRange('16:00:00', '18:30:00')).toBe('16:00 – 18:30')
    expect(timeRange(null, null)).toBe('')
    expect(formatTime('09:05')).toBe('09:05')
  })

  it('joins phrases the way the language does', () => {
    const { list } = setup()
    expect(list(['A', 'B', 'C'])).toBe('A, B und C')
  })

  it('writes days as a span, a few days, or a span with a count', () => {
    const { daysText } = setup()
    expect(daysText(['2027-12-05', '2027-12-06'])).toBe('5.–6. Dezember 2027')
    expect(daysText(['2027-12-05', '2027-12-07'])).toBe('So., 5.12. und Di., 7.12.')
    expect(daysText(['2027-12-01', '2027-12-03', '2027-12-05', '2027-12-09'])).toBe(
      '1.–9. Dezember 2027, an 4 Tagen',
    )
  })

  it('follows the language', () => {
    i18n.global.locale.value = 'en'
    const { list, daysText } = setup()
    expect(list(['A', 'B'])).toBe('A and B')
    expect(daysText(['2027-12-01', '2027-12-03', '2027-12-05', '2027-12-09'])).toMatch(
      /, on 4 days$/,
    )
  })
})
