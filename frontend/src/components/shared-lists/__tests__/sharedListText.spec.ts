// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSharedListText } from '@/components/shared-lists/sharedListText'

import i18n from '@/locales/i18n'

import { listRow } from './fixtures'

/**
 * The wording the shared-list screens share: names in quotes with "and N
 * more", a task's days as a span or a list, "today / tomorrow / in N days",
 * when a list closes, and a guest without a name.
 */

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))

function text() {
  let api!: ReturnType<typeof useSharedListText>
  mount(
    defineComponent({
      setup() {
        api = useSharedListText()
        return () => null
      },
    }),
    { global: { plugins: [i18n] } },
  )
  return api
}

/** `Intl` puts thin and narrow spaces around a range's dash. */
const plain = (value: string) => value.replace(/\s/gu, ' ')

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('useSharedListText', () => {
  it('quotes names and counts the rest', () => {
    const { quotedNames } = text()
    expect(quotedNames(['Bar'])).toBe('“Bar”')
    expect(quotedNames(['Bar', 'Kasse'])).toBe('“Bar” and “Kasse”')
    expect(quotedNames(['Bar', 'Kasse'], 3)).toBe('“Bar”, “Kasse” and one more')
    expect(quotedNames(['Bar', 'Kasse'], 6)).toBe('“Bar”, “Kasse” and 4 more')
  })

  it('quotes the German way in German', () => {
    i18n.global.locale.value = 'de'
    expect(text().quotedNames(['Bar', 'Kasse'], 5)).toBe('„Bar“, „Kasse“ und 3 weitere')
  })

  it('writes days that follow one another as a span', () => {
    const { daysText } = text()
    expect(daysText([])).toBe('')
    expect(plain(daysText(['2030-07-19', '2030-07-17', '2030-07-18']))).toBe('July 17 – 19, 2030')
  })

  it('lists a few scattered days and sums up many', () => {
    const { daysText } = text()
    expect(daysText(['2030-07-17', '2030-07-19'])).toBe('Wed, 7/17 and Fri, 7/19')
    expect(plain(daysText(['2030-07-01', '2030-07-03', '2030-07-05', '2030-07-09']))).toBe(
      'July 1 – 9, 2030, on 4 days',
    )
  })

  it('says today, tomorrow or in how many days, never in the past', () => {
    const { inDays } = text()
    expect(inDays(-2)).toBe('today')
    expect(inDays(0)).toBe('today')
    expect(inDays(1)).toBe('tomorrow')
    expect(inDays(3)).toBe('in 3 days')
  })

  it('says how a list closes', () => {
    const { endsText } = text()
    expect(endsText({ ends_mode: 'manual', ends_on: null, closes_at: null })).toBe(
      'until someone ends it',
    )
    expect(endsText({ ends_mode: 'date', ends_on: '2030-07-19', closes_at: null })).toBe(
      'through Fri, July 19',
    )
    expect(
      endsText({ ends_mode: 'last_shift', ends_on: null, closes_at: '2030-07-19T14:30:00' }),
    ).toBe('until the last shift starts (Fri, July 19, 14:30)')
  })

  it('fills the "open until" column', () => {
    const { closesText } = text()
    expect(closesText(listRow('a', { effective_status: 'ended' }))).toBe('ended')
    expect(closesText(listRow('a', { ends_mode: 'manual' }))).toBe('no end date')
    expect(closesText(listRow('a', { ends_mode: 'date', ends_on: '2030-07-19' }))).toBe(
      'Fri, Jul 19',
    )
    expect(closesText(listRow('a', { closes_at: '2030-07-19T14:30:00' }))).toBe(
      'Fri, Jul 19, 14:30',
    )
    expect(closesText(listRow('a', { closes_at: null }))).toBe('no shifts left')
  })

  it('writes a shift with or without its times', () => {
    const { shiftText } = text()
    expect(shiftText('2030-07-19', '10:00:00', '12:00:00')).toBe('Fri, Jul 19, 10:00 – 12:00')
    expect(shiftText('2030-07-19')).toBe('Fri, Jul 19')
  })

  it('says how long ago someone signed up', () => {
    const { signedUpWhen } = text()
    const now = new Date()
    const justNow = now.toISOString().slice(0, 19)
    expect(signedUpWhen(justNow)).toBe('just now')
    expect(signedUpWhen('not a date')).toBe('')
  })

  it('names a guest whose data is gone, and nobody else that way', () => {
    const { personName } = text()
    expect(personName('Mia', true)).toBe('Mia')
    expect(personName(null, true)).toBe('Guest (deleted)')
    expect(personName(null, false)).toBe('?')
    expect(personName(undefined, false, '—')).toBe('—')
  })
})
