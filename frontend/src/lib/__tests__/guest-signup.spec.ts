import { describe, expect, it } from 'vitest'

import type { PublicDay, PublicShift } from '@/client/types.gen'
import {
  ALL_SHIFTS,
  type GuestFields,
  NO_SHIFT_FILTER,
  checkGuestFields,
  dayAndTime,
  filterDays,
  guestManageUrl,
  listTasks,
  rejectedField,
  retentionVariant,
} from '@/lib/guest-signup'

/**
 * What the public sign-up form refuses before sending, mirroring the server's
 * normalisers, and how it reads the server's own refusal of a field.
 */

const fields = (overrides: Partial<GuestFields> = {}): GuestFields => ({
  name: 'Anna Berg',
  email: 'anna@example.org',
  phone: '+49 170 1234567',
  remind: true,
  ...overrides,
})

describe('checkGuestFields', () => {
  it('accepts a complete form', () => {
    expect(checkGuestFields(fields(), 'required', 'required')).toEqual({})
  })

  it('wants a name of two characters once the spaces are collapsed', () => {
    expect(checkGuestFields(fields({ name: '  A  ' }), 'off', 'off')).toEqual({
      name: 'guestSignup.validation.name',
    })
    expect(checkGuestFields(fields({ name: 'Al' }), 'off', 'off')).toEqual({})
  })

  it('asks for an address only where the list requires one', () => {
    expect(checkGuestFields(fields({ email: ' ' }), 'required', 'off')).toEqual({
      email: 'guestSignup.validation.emailRequired',
    })
    expect(checkGuestFields(fields({ email: '' }), 'optional', 'off')).toEqual({})
  })

  it('refuses an address that does not look complete, even an optional one', () => {
    expect(checkGuestFields(fields({ email: 'anna@example' }), 'optional', 'off')).toEqual({
      email: 'guestSignup.validation.emailInvalid',
    })
  })

  it('ignores whatever is in a field the list does not ask for', () => {
    expect(checkGuestFields(fields({ email: 'nope', phone: 'x' }), 'off', 'off')).toEqual({})
  })

  it('asks for a phone number only where required, and checks its characters and length', () => {
    expect(checkGuestFields(fields({ phone: '' }), 'off', 'required')).toEqual({
      phone: 'guestSignup.validation.phoneRequired',
    })
    expect(checkGuestFields(fields({ phone: '' }), 'off', 'optional')).toEqual({})
    expect(checkGuestFields(fields({ phone: '0170-12 (34) / 5.6' }), 'off', 'optional')).toEqual({})
    for (const phone of ['1234', '0170 call me', '1'.repeat(31)]) {
      expect(checkGuestFields(fields({ phone }), 'off', 'optional')).toEqual({
        phone: 'guestSignup.validation.phoneInvalid',
      })
    }
  })

  it('reports every refused field at once', () => {
    expect(
      Object.keys(
        checkGuestFields({ name: '', email: '', phone: '', remind: false }, 'required', 'required'),
      ),
    ).toEqual(['name', 'email', 'phone'])
  })
})

describe('rejectedField', () => {
  it('names the first body field the server refused, with what to say about it', () => {
    expect(
      rejectedField([
        { loc: ['body', 'shift_id'], msg: 'bad', type: 'uuid_parsing' },
        { loc: ['body', 'phone'], msg: 'bad', type: 'value_error' },
        { loc: ['body', 'email'], msg: 'bad', type: 'value_error' },
      ]),
    ).toEqual({ field: 'phone', key: 'guestSignup.validation.phoneInvalid' })
  })

  it('answers null when no form field is named, or there are no errors', () => {
    expect(rejectedField([{ loc: ['query', 'name'], msg: 'bad', type: 'x' }])).toBeNull()
    expect(rejectedField(undefined)).toBeNull()
  })
})

describe('dayAndTime', () => {
  it('joins the day and the times, leaving out whichever is empty', () => {
    expect(dayAndTime('Friday, 20 November', '10:00 – 12:00')).toBe(
      'Friday, 20 November, 10:00 – 12:00',
    )
    expect(dayAndTime('Friday, 20 November', '')).toBe('Friday, 20 November')
  })
})

describe('guestManageUrl', () => {
  it('puts the token in the fragment of the manage page', () => {
    expect(guestManageUrl('abc.def', 'https://wirksam.app/')).toBe(
      'https://wirksam.app/guest-signup#abc.def',
    )
  })

  it('defaults to this deployment', () => {
    const previous = globalThis.window
    globalThis.window = { location: { origin: 'https://example.org' } } as Window &
      typeof globalThis
    try {
      expect(guestManageUrl('t')).toBe('https://example.org/guest-signup#t')
    } finally {
      globalThis.window = previous
    }
  })
})

describe('retentionVariant', () => {
  it('names the address and the phone number only where there are any', () => {
    expect(retentionVariant(false, false)).toBe('name')
    expect(retentionVariant(true, false)).toBe('nameEmail')
    expect(retentionVariant(false, true)).toBe('namePhone')
    expect(retentionVariant(true, true)).toBe('all')
  })
})

describe('filterDays', () => {
  const shift = (id: string, task: string, full = false): PublicShift => ({
    id,
    task_id: task,
    task_name: task === 'bar' ? 'Bar' : 'Grill',
    capacity: 2,
    free: full ? 0 : 1,
    full,
    names: [],
    others_count: 0,
    vouchers: 0,
  })
  const days: PublicDay[] = [
    { date: '2026-11-20', shifts: [shift('a', 'bar', true), shift('b', 'grill')] },
    { date: '2026-11-21', shifts: [shift('c', 'bar')] },
  ]
  const ids = (picked: PublicDay[]) => picked.map((day) => day.shifts.map((s) => s.id))

  it('keeps everything without a filter', () => {
    expect(filterDays(days, NO_SHIFT_FILTER)).toEqual(days)
  })

  it('narrows to one task, dropping a day left empty', () => {
    expect(ids(filterDays(days, { ...NO_SHIFT_FILTER, task: 'grill' }))).toEqual([['b']])
  })

  it('narrows to one day and to shifts with a place left', () => {
    expect(ids(filterDays(days, { ...NO_SHIFT_FILTER, day: '2026-11-20' }))).toEqual([['a', 'b']])
    expect(ids(filterDays(days, { ...NO_SHIFT_FILTER, onlyFree: true }))).toEqual([['b'], ['c']])
    expect(filterDays(days, { task: 'bar', day: '2026-11-20', onlyFree: true })).toEqual([])
  })

  it('names each task once, in the order its first shift comes', () => {
    expect(listTasks(days)).toEqual([
      { id: 'bar', name: 'Bar' },
      { id: 'grill', name: 'Grill' },
    ])
    expect(ALL_SHIFTS).toBe('all')
  })
})
