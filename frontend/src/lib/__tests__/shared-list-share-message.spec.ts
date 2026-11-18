import { beforeEach, describe, expect, it } from 'vitest'

import type { WizardShift } from '@/lib/shared-list-selection'
import {
  type DaysFormat,
  LISTED_DAYS_MAX,
  PER_SHIFT_LINES_MAX,
  type ShareMessageFormat,
  describeDays,
  isConsecutive,
  shareMessage,
} from '@/lib/shared-list-share-message'
import i18n from '@/locales/i18n'

/**
 * The text for the group chat: one line per open shift while there are few,
 * one line per task once there are many, full shifts left out, and no
 * "für den {event}" that only fits masculine event names.
 */

function shift(
  id: string,
  taskId: string,
  date: string,
  start: string | null,
  free: number,
): WizardShift {
  return { id, task_id: taskId, date, start_time: start, end_time: null, capacity: 4, free }
}

const format: ShareMessageFormat = {
  day: (date) => `D${date.slice(8)}`,
  time: (start) => (start ? start.slice(0, 5) : ''),
  days: (dates) => dates.map((d) => d.slice(8)).join('+'),
}

const tasks = [
  { id: 'gw', name: 'Glühwein' },
  { id: 'ks', name: 'Kasse' },
  { id: 'empty', name: 'Zelt' },
]

function message(shifts: WizardShift[]) {
  return shareMessage(
    {
      eventName: 'Weihnachtsmarkt',
      eventDays: '5.–6. Dezember',
      tasks,
      shifts,
      url: 'https://wirksam.app/l/abc',
    },
    format,
    i18n.global.t,
  )
}

beforeEach(() => {
  i18n.global.locale.value = 'de'
})

describe('shareMessage', () => {
  it('names each open shift under its task while there are few, in list order', () => {
    const text = message([
      shift('k1', 'ks', '2026-12-05', '18:00:00', 1),
      shift('g2', 'gw', '2026-12-06', null, 2),
      shift('g1', 'gw', '2026-12-05', '16:00:00', 3),
    ])
    expect(text).toBe(
      [
        'Hallo zusammen! Für „Weihnachtsmarkt“ (5.–6. Dezember) suchen wir noch Leute.',
        '',
        'Glühwein',
        '• D05, 16:00: 3 frei',
        '• D06: 2 frei',
        '',
        'Kasse',
        '• D05, 18:00: 1 frei',
        '',
        'Eintragen geht ohne Konto und dauert eine Minute:',
        'https://wirksam.app/l/abc',
      ].join('\n'),
    )
  })

  it('leaves full shifts out, and a task with nothing free', () => {
    const text = message([
      shift('g1', 'gw', '2026-12-05', '16:00:00', 0),
      shift('k1', 'ks', '2026-12-05', '18:00:00', 1),
    ])
    expect(text).not.toContain('Glühwein')
    expect(text).not.toContain('Zelt')
    expect(text).toContain('• D05, 18:00: 1 frei')
  })

  it('sums up per task once there are more open shifts than fit a phone screen', () => {
    const many = Array.from({ length: PER_SHIFT_LINES_MAX }, (_, i) =>
      shift(`g${i}`, 'gw', `2026-12-0${(i % 2) + 5}`, `${10 + i}:00:00`, 1),
    )
    const text = message([...many, shift('k1', 'ks', '2026-12-05', '18:00:00', 1)])
    expect(text.split('\n')).toEqual([
      'Hallo zusammen! Für „Weihnachtsmarkt“ (5.–6. Dezember) suchen wir noch Leute.',
      '',
      `• Glühwein: ${PER_SHIFT_LINES_MAX} Plätze frei (05+05+05+05+06+06+06+06)`,
      '• Kasse: 1 Platz frei (05)',
      '',
      'Eintragen geht ohne Konto und dauert eine Minute:',
      'https://wirksam.app/l/abc',
    ])
  })

  it('still invites people when every shift is full', () => {
    expect(message([shift('g1', 'gw', '2026-12-05', '16:00:00', 0)]).split('\n')).toEqual([
      'Hallo zusammen! Für „Weihnachtsmarkt“ (5.–6. Dezember) suchen wir noch Leute.',
      '',
      'Eintragen geht ohne Konto und dauert eine Minute:',
      'https://wirksam.app/l/abc',
    ])
  })

  it('speaks English too', () => {
    i18n.global.locale.value = 'en'
    const text = message([shift('g1', 'gw', '2026-12-05', '16:00:00', 2)])
    expect(text).toContain('Hi everyone!')
    expect(text).toContain('• D05, 16:00: 2 free')
    expect(text).toContain('Signing up needs no account and takes a minute:')
  })
})

describe('isConsecutive', () => {
  it('is true for days that follow each other, across a month', () => {
    expect(isConsecutive(['2026-11-30', '2026-12-01', '2026-12-02'])).toBe(true)
    expect(isConsecutive(['2026-12-05'])).toBe(true)
    expect(isConsecutive([])).toBe(true)
  })

  it('is false with a gap', () => {
    expect(isConsecutive(['2026-12-05', '2026-12-07'])).toBe(false)
  })
})

describe('describeDays', () => {
  const days: DaysFormat = {
    span: (start, end) => `${start.slice(8)}–${end.slice(8)}`,
    day: (date) => date.slice(8),
    list: (items) => items.join(' & '),
    spread: (span, count) => `${span} (${count})`,
  }

  it('is empty without days', () => {
    expect(describeDays([], days)).toBe('')
  })

  it('is a span for days that follow each other, once each and in order', () => {
    expect(describeDays(['2026-12-06', '2026-12-05', '2026-12-06'], days)).toBe('05–06')
  })

  it('names a few separate days', () => {
    const few = ['2026-12-01', '2026-12-05', '2026-12-09'].slice(0, LISTED_DAYS_MAX)
    expect(describeDays(few, days)).toBe('01 & 05 & 09')
  })

  it('gives the span and the count for many separate days', () => {
    expect(describeDays(['2026-12-01', '2026-12-03', '2026-12-05', '2026-12-09'], days)).toBe(
      '01–09 (4)',
    )
  })
})
