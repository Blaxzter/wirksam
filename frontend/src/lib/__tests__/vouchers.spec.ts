import { describe, expect, it } from 'vitest'

import type { VoucherEntryRead, VoucherShift } from '@/client/types.gen'
import {
  SAME_CODE_IGNORE_MS,
  classifyCameraError,
  codeUsedDetails,
  createDetectionGate,
  formatVoucherCode,
  historySortKey,
  newRequestId,
  normalizeVoucherCode,
  parseVoucherPayload,
  secondsLeft,
  voucherHistory,
} from '@/lib/vouchers'

describe('normalizeVoucherCode', () => {
  it('accepts a code as the server stores it', () => {
    expect(normalizeVoucherCode('K7M4QX')).toBe('K7M4QX')
  })

  it('forgives lower case, the shown dash and spaces', () => {
    expect(normalizeVoucherCode(' k7m-4qx ')).toBe('K7M4QX')
    expect(normalizeVoucherCode('k7m 4qx')).toBe('K7M4QX')
  })

  it('drops the QR prefix when the scanned text is pasted', () => {
    expect(normalizeVoucherCode('WV1:K7M4QX')).toBe('K7M4QX')
    expect(normalizeVoucherCode('wv1:k7m-4qx')).toBe('K7M4QX')
  })

  it('refuses look-alike characters the alphabet leaves out', () => {
    for (const bad of ['K7M4Q0', 'K7M4QO', 'K7M4Q1', 'K7M4QI', 'K7M4QL']) {
      expect(normalizeVoucherCode(bad)).toBeNull()
    }
  })

  it('refuses the wrong length and empty input', () => {
    expect(normalizeVoucherCode('K7M4Q')).toBeNull()
    expect(normalizeVoucherCode('K7M4QXX')).toBeNull()
    expect(normalizeVoucherCode('')).toBeNull()
    expect(normalizeVoucherCode('   ')).toBeNull()
    expect(normalizeVoucherCode(null)).toBeNull()
    expect(normalizeVoucherCode(undefined)).toBeNull()
  })
})

describe('parseVoucherPayload', () => {
  it('reads the code out of our own QR payload', () => {
    expect(parseVoucherPayload('WV1:K7M4QX')).toBe('K7M4QX')
    expect(parseVoucherPayload('  WV1:K7M4QX\n')).toBe('K7M4QX')
  })

  it('ignores any other QR code', () => {
    expect(parseVoucherPayload('https://example.com/WV1:K7M4QX')).toBeNull()
    expect(parseVoucherPayload('K7M4QX')).toBeNull()
    expect(parseVoucherPayload('WV2:K7M4QX')).toBeNull()
  })

  it('is stricter than typing: no dash, no lower case, no extra characters', () => {
    expect(parseVoucherPayload('WV1:K7M-4QX')).toBeNull()
    expect(parseVoucherPayload('WV1:k7m4qx')).toBeNull()
    expect(parseVoucherPayload('WV1:K7M4QX1')).toBeNull()
    expect(parseVoucherPayload('WV1:K7M4Q0')).toBeNull()
  })

  it('returns null for nothing at all', () => {
    expect(parseVoucherPayload('')).toBeNull()
    expect(parseVoucherPayload(null)).toBeNull()
    expect(parseVoucherPayload(undefined)).toBeNull()
  })
})

describe('formatVoucherCode', () => {
  it('splits a code in the middle', () => {
    expect(formatVoucherCode('K7M4QX')).toBe('K7M-4QX')
  })

  it('leaves anything that is not a whole code alone', () => {
    expect(formatVoucherCode('K7M4')).toBe('K7M4')
    expect(formatVoucherCode('')).toBe('')
  })
})

describe('secondsLeft', () => {
  const received = 1_000_000

  it('counts down from the moment the response arrived', () => {
    expect(secondsLeft(received, 120, received)).toBe(120)
    expect(secondsLeft(received, 120, received + 30_000)).toBe(90)
  })

  it('rounds a part second up, so 0 only shows once it is over', () => {
    expect(secondsLeft(received, 120, received + 119_500)).toBe(1)
    expect(secondsLeft(received, 120, received + 120_000)).toBe(0)
  })

  it('never goes below zero', () => {
    expect(secondsLeft(received, 120, received + 500_000)).toBe(0)
  })
})

const shift = (over: Partial<VoucherShift> = {}): VoucherShift => ({
  booking_id: 'b1',
  shift_id: 's1',
  task_id: 't1',
  task_name: 'Bar',
  title: 'Bar 10:00',
  date: '2026-07-04',
  start_time: '10:00:00',
  end_time: '12:00:00',
  ends_at: '2026-07-04T10:00:00',
  vouchers: 2,
  completed: true,
  ...over,
})

const entry = (over: Partial<VoucherEntryRead> = {}): VoucherEntryRead => ({
  id: 'e1',
  kind: 'redemption',
  amount: -1,
  task_name: 'Café',
  actor_name: 'Anna',
  created_at: '2026-07-04T11:00:00',
  updated_at: '2026-07-04T11:00:00',
  ...over,
})

describe('historySortKey', () => {
  it('uses the end of a shift and the time an entry was made, both as UTC', () => {
    expect(historySortKey({ kind: 'shift', key: 'a', shift: shift() })).toBe(
      Date.UTC(2026, 6, 4, 10),
    )
    expect(historySortKey({ kind: 'entry', key: 'b', entry: entry() })).toBe(
      Date.UTC(2026, 6, 4, 11),
    )
  })

  it('puts an unreadable time last', () => {
    expect(historySortKey({ kind: 'entry', key: 'c', entry: entry({ created_at: 'nope' }) })).toBe(
      Number.NEGATIVE_INFINITY,
    )
  })
})

describe('voucherHistory', () => {
  it('merges earned shifts and entries, newest first', () => {
    const items = voucherHistory({
      shifts: [
        shift({ booking_id: 'old', ends_at: '2026-07-03T18:00:00' }),
        shift({ booking_id: 'new', ends_at: '2026-07-04T12:00:00' }),
      ],
      entries: [entry({ id: 'mid', created_at: '2026-07-04T08:00:00' })],
    })
    expect(items.map((i) => i.key)).toEqual(['shift-new', 'entry-mid', 'shift-old'])
  })

  it('leaves out shifts that have not ended', () => {
    const items = voucherHistory({
      shifts: [shift({ booking_id: 'later', completed: false })],
      entries: [],
    })
    expect(items).toEqual([])
  })

  it('lists a settled shift whose shift and task are gone like any earned one', () => {
    const gone = shift({ booking_id: 'gone', shift_id: null, task_id: null, settled: true })
    const items = voucherHistory({ shifts: [gone], entries: [] })
    expect(items).toEqual([{ kind: 'shift', key: 'shift-gone', shift: gone }])
  })
})

describe('createDetectionGate', () => {
  it('accepts a code once, then ignores it while it stays in view', () => {
    const gate = createDetectionGate()
    expect(gate.accept('AAAAAA', 0)).toBe(true)
    expect(gate.accept('AAAAAA', 500)).toBe(false)
    expect(gate.accept('AAAAAA', SAME_CODE_IGNORE_MS - 1)).toBe(false)
  })

  it('accepts the same code again once it has been out of view for the quiet time', () => {
    const gate = createDetectionGate(1000)
    gate.accept('AAAAAA', 0)
    expect(gate.accept('AAAAAA', 1000)).toBe(true)
  })

  it('counts the quiet time from the last sighting, not the first', () => {
    const gate = createDetectionGate(1000)
    gate.accept('AAAAAA', 0)
    // Still in front of the camera: every sighting starts the wait again.
    expect(gate.accept('AAAAAA', 900)).toBe(false)
    expect(gate.accept('AAAAAA', 1800)).toBe(false)
    expect(gate.accept('AAAAAA', 2700)).toBe(false)
    expect(gate.accept('AAAAAA', 3700)).toBe(true)
  })

  it('treats a remembered code as just handled', () => {
    const gate = createDetectionGate(1000)
    gate.accept('AAAAAA', 0)
    // The confirm for it closes long after it was first seen.
    gate.remember('AAAAAA', 15_000)
    expect(gate.accept('AAAAAA', 15_500)).toBe(false)
    expect(gate.accept('BBBBBB', 15_600)).toBe(true)
  })

  it('accepts a different code at once, and the first one again after it', () => {
    const gate = createDetectionGate()
    gate.accept('AAAAAA', 0)
    expect(gate.accept('BBBBBB', 10)).toBe(true)
    expect(gate.accept('AAAAAA', 20)).toBe(true)
  })

  it('forgets the last code on reset', () => {
    const gate = createDetectionGate()
    gate.accept('AAAAAA', 0)
    gate.reset()
    expect(gate.accept('AAAAAA', 1)).toBe(true)
  })
})

describe('classifyCameraError', () => {
  it('reads a refused permission as refused, whatever the scanner threw', () => {
    // qr-scanner turns every getUserMedia rejection into this one string.
    expect(classifyCameraError('Camera not found.', 'denied')).toBe('denied')
    expect(classifyCameraError(new Error('x'), 'denied')).toBe('denied')
  })

  it("trusts the scanner's string when the permission was not refused", () => {
    expect(classifyCameraError('Camera not found.', 'granted')).toBe('no-camera')
    expect(classifyCameraError('Camera not found.', 'prompt')).toBe('no-camera')
    expect(classifyCameraError('Camera not found.')).toBe('no-camera')
  })

  it("reads the browser's own errors by name", () => {
    expect(classifyCameraError(new DOMException('no', 'NotAllowedError'))).toBe('denied')
    expect(classifyCameraError(new DOMException('no', 'SecurityError'))).toBe('denied')
    expect(classifyCameraError({ name: 'PermissionDeniedError' })).toBe('denied')
    expect(classifyCameraError(new DOMException('none', 'NotFoundError'))).toBe('no-camera')
    expect(classifyCameraError(new DOMException('x', 'OverconstrainedError'))).toBe('no-camera')
    expect(classifyCameraError({ name: 'DevicesNotFoundError' })).toBe('no-camera')
  })

  it('calls anything else a failure', () => {
    expect(classifyCameraError(new DOMException('busy', 'NotReadableError'))).toBe('other')
    expect(classifyCameraError(new Error('boom'))).toBe('other')
    expect(classifyCameraError('something else')).toBe('other')
    expect(classifyCameraError(null)).toBe('other')
    expect(classifyCameraError({ name: 42 })).toBe('other')
  })
})

describe('newRequestId', () => {
  const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

  it('uses randomUUID where the browser has it', () => {
    const source = {
      randomUUID: () => '00000000-0000-4000-8000-000000000000',
      getRandomValues: (a: Uint8Array<ArrayBuffer>) => a,
    }
    expect(newRequestId(source)).toBe('00000000-0000-4000-8000-000000000000')
  })

  it('builds a version 4 UUID from random bytes outside a secure context', () => {
    const source = { getRandomValues: (a: Uint8Array<ArrayBuffer>) => a.fill(0xff) }
    const id = newRequestId(source)
    expect(id).toMatch(UUID_V4)
    expect(id).toBe('ffffffff-ffff-4fff-bfff-ffffffffffff')
  })

  it('gives a different key each time by default', () => {
    expect(newRequestId()).not.toBe(newRequestId())
  })
})

describe('codeUsedDetails', () => {
  const problem = (data: unknown) => ({ isAxiosError: true, response: { status: 409, data } })

  it('reads where and when a used code was redeemed', () => {
    const details = codeUsedDetails(
      problem({
        code: 'voucher.code_used',
        amount: 2,
        task_name: 'Bar',
        actor_name: 'Anna',
        used_at: '2026-07-04T12:03:00',
      }),
    )
    expect(details).toEqual({
      amount: 2,
      taskName: 'Bar',
      actorName: 'Anna',
      usedAt: new Date(Date.UTC(2026, 6, 4, 12, 3)),
    })
  })

  it('takes the code from the problem type as well', () => {
    const details = codeUsedDetails(
      problem({ type: 'urn:problem:voucher.code_used', amount: 1, task_name: 'Bar' }),
    )
    expect(details).toEqual({ amount: 1, taskName: 'Bar', actorName: null, usedAt: null })
  })

  it('returns null for other errors and for a used code without details', () => {
    expect(codeUsedDetails(problem({ code: 'voucher.code_expired' }))).toBeNull()
    expect(codeUsedDetails(problem({ type: 'https://example.com/x', amount: 1 }))).toBeNull()
    expect(codeUsedDetails(problem({ code: 'voucher.code_used', amount: null }))).toBeNull()
    expect(codeUsedDetails(problem('not json'))).toBeNull()
    expect(codeUsedDetails({ response: null })).toBeNull()
    expect(codeUsedDetails(new Error('Network Error'))).toBeNull()
    expect(codeUsedDetails(null)).toBeNull()
  })
})
