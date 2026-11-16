import { describe, expect, it } from 'vitest'

import type {
  PublicSharedList,
  ShiftBatchRead,
  ShiftRead,
  TaskBookingEntry,
} from '@/client/types.gen'
import {
  type SheetShift,
  byBatch,
  byDay,
  byTask,
  fromShift,
  offeredShifts,
  sheetLines,
  shiftDates,
  varies,
} from '@/lib/print-sheet'

function shiftRead(id: string, patch: Partial<ShiftRead> = {}): ShiftRead {
  return {
    id,
    task_id: 't1',
    title: 'Kuchen',
    date: '2026-12-05',
    start_time: '10:00:00',
    end_time: '12:00:00',
    location: 'Aula',
    location_id: 'l1',
    max_bookings: 3,
    batch_id: 'b1',
    created_at: '2026-11-01T09:00:00',
    updated_at: '2026-11-01T09:00:00',
    ...patch,
  }
}

function sheetShift(id: string, patch: Partial<SheetShift> = {}): SheetShift {
  return { ...fromShift(shiftRead(id)), ...patch }
}

function booked(shiftId: string, name: string, phone: string | null = null): TaskBookingEntry {
  return { id: `${shiftId}-${name}`, shift_id: shiftId, user_name: name, user_phone_number: phone }
}

function batch(id: string, label: string): ShiftBatchRead {
  return {
    id,
    task_id: 't1',
    label,
    start_date: '2026-12-05',
    end_date: '2026-12-06',
    created_at: '2026-11-01T09:00:00',
    updated_at: '2026-11-01T09:00:00',
  }
}

describe('fromShift', () => {
  it('keeps a task sheet’s shift as it is, with its places and no free count', () => {
    expect(fromShift(shiftRead('s1'))).toEqual({
      id: 's1',
      task_id: 't1',
      date: '2026-12-05',
      start_time: '10:00:00',
      end_time: '12:00:00',
      title: 'Kuchen',
      location: 'Aula',
      location_id: 'l1',
      batch_id: 'b1',
      capacity: 3,
      free: null,
      vouchers: 0,
    })
  })

  it('reads what the API leaves out as nothing, and one place by default', () => {
    const bare = fromShift({
      id: 's2',
      task_id: 't1',
      title: 'Bar',
      date: '2026-12-05',
      created_at: '',
      updated_at: '',
    })
    expect(bare).toMatchObject({
      start_time: null,
      end_time: null,
      location: null,
      location_id: null,
      batch_id: null,
      capacity: 1,
    })
  })
})

describe('offeredShifts', () => {
  const list: Pick<PublicSharedList, 'days'> = {
    days: [
      {
        date: '2026-12-05',
        shifts: [
          {
            id: 's1',
            task_id: 't1',
            task_name: 'Kuchen',
            location: 'Aula',
            start_time: '10:00:00',
            end_time: '12:00:00',
            capacity: 3,
            free: 1,
            full: false,
            vouchers: 2,
          },
          {
            id: 's9',
            task_id: 't2',
            task_name: 'Bar',
            capacity: 2,
            free: 2,
            full: false,
          },
        ],
      },
    ],
  }

  it('takes the free places and vouchers from the list, the rest from the shift', () => {
    const [known, unknown] = offeredShifts(list, new Map([['s1', shiftRead('s1')]]))
    expect(known).toEqual({
      id: 's1',
      task_id: 't1',
      date: '2026-12-05',
      start_time: '10:00:00',
      end_time: '12:00:00',
      title: 'Kuchen',
      location: 'Aula',
      location_id: 'l1',
      batch_id: 'b1',
      capacity: 3,
      free: 1,
      vouchers: 2,
    })
    // Not among the task's shift rows: it still prints, without them.
    expect(unknown).toMatchObject({
      id: 's9',
      task_id: 't2',
      title: null,
      location: null,
      location_id: null,
      batch_id: null,
      start_time: null,
      end_time: null,
      free: 2,
      vouchers: 0,
    })
  })

  it('offers nothing while the list has no days', () => {
    expect(offeredShifts({ days: [] }, new Map())).toEqual([])
  })
})

describe('byTask', () => {
  it('groups the shifts by task, in the order the tasks first come', () => {
    const bar = sheetShift('bar', { task_id: 't2' })
    const cake = sheetShift('cake')
    const later = sheetShift('later', { date: '2026-12-06' })
    const groups = byTask([bar, cake, later])
    expect([...groups].map(([task, shifts]) => [task, shifts.map((s) => s.id)])).toEqual([
      ['t2', ['bar']],
      ['t1', ['cake', 'later']],
    ])
  })
})

describe('byDay', () => {
  it('orders the days, and each day by start and then end, untimed first', () => {
    const late = sheetShift('late', { date: '2026-12-06', start_time: '14:00:00' })
    const short = sheetShift('short', { end_time: '11:00:00' })
    const long = sheetShift('long')
    const untimed = sheetShift('untimed', { start_time: null, end_time: null })
    const days = byDay([late, long, short, untimed])
    expect(days.map(([date, shifts]) => [date, shifts.map((s) => s.id)])).toEqual([
      ['2026-12-05', ['untimed', 'short', 'long']],
      ['2026-12-06', ['late']],
    ])
  })
})

describe('byBatch', () => {
  const first = sheetShift('a', { batch_id: 'b1' })
  const second = sheetShift('b', { batch_id: 'b2' })
  const loose = sheetShift('c', { batch_id: null })
  const stray = sheetShift('d', { batch_id: 'gone' })

  it('is one group without a heading for one batch or none', () => {
    expect(byBatch([first, second], [batch('b1', 'Woche 1')])).toEqual([
      { batch: null, shifts: [first, second] },
    ])
    expect(byBatch([], [])).toEqual([{ batch: null, shifts: [] }])
  })

  it('groups by batch in the batches’ order, the rest last, empty ones left out', () => {
    const b1 = batch('b1', 'Woche 1')
    const b2 = batch('b2', 'Woche 2')
    const b3 = batch('b3', 'Woche 3')
    expect(byBatch([loose, second, first, stray], [b2, b1, b3])).toEqual([
      { batch: b2, shifts: [second] },
      { batch: b1, shifts: [first] },
      { batch: null, shifts: [loose, stray] },
    ])
  })
})

describe('varies', () => {
  it('is true only for two different values, blanks not counted', () => {
    const pick = (shift: SheetShift) => shift.location
    expect(varies([sheetShift('a'), sheetShift('b')], pick)).toBe(false)
    expect(varies([sheetShift('a'), sheetShift('b', { location: null })], pick)).toBe(false)
    expect(varies([sheetShift('a'), sheetShift('b', { location: 'Foyer' })], pick)).toBe(true)
  })
})

describe('shiftDates', () => {
  it('lists every day once, in order', () => {
    const shifts = [
      sheetShift('a', { date: '2026-12-06' }),
      sheetShift('b'),
      sheetShift('c', { date: '2026-12-06' }),
    ]
    expect(shiftDates(shifts)).toEqual(['2026-12-05', '2026-12-06'])
  })
})

describe('sheetLines', () => {
  const names = [booked('s1', 'Mia', '0171'), booked('s1', 'Tom')]
  const blank = { name: '', contact: '' }

  describe('on a task’s own sheet', () => {
    const shift = sheetShift('s1')

    it('has a blank line for every place while the names are hidden', () => {
      expect(sheetLines(shift, names, { includeNames: false, paperLines: true })).toEqual([
        blank,
        blank,
        blank,
      ])
    })

    it('fills in the booked names first, and never prints more lines than places', () => {
      expect(sheetLines(shift, names, { includeNames: true, paperLines: false })).toEqual([
        { name: 'Mia', contact: '0171' },
        { name: 'Tom', contact: '' },
        blank,
      ])
      const crowded = [...names, booked('s1', 'Ida'), booked('s1', 'Ben')]
      expect(
        sheetLines(shift, crowded, { includeNames: true, paperLines: true }).map((l) => l.name),
      ).toEqual(['Mia', 'Tom', 'Ida'])
    })

    it('reads a booking without a name or number as a blank', () => {
      const anonymous = { id: 'x', shift_id: 's1' }
      expect(sheetLines(shift, [anonymous], { includeNames: true, paperLines: true })[0]).toEqual(
        blank,
      )
    })
  })

  describe('on a shared list’s sheet', () => {
    const shift = sheetShift('s1', { free: 1 })

    it('has a line for each free place, with lines for paper on', () => {
      expect(sheetLines(shift, names, { includeNames: false, paperLines: true })).toEqual([blank])
    })

    it('has none without them', () => {
      expect(sheetLines(shift, names, { includeNames: false, paperLines: false })).toEqual([])
    })

    it('names who signed up above the free lines', () => {
      expect(sheetLines(shift, names, { includeNames: true, paperLines: true })).toEqual([
        { name: 'Mia', contact: '0171' },
        { name: 'Tom', contact: '' },
        blank,
      ])
    })
  })
})
