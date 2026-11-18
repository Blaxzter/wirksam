import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SETTLE_MS, usePrintSheet } from '@/composables/usePrintSheet'

import type {
  PublicSharedList,
  SharedListDetail,
  ShiftRead,
  TaskBookingEntry,
} from '@/client/types.gen'
import type { SheetShift } from '@/lib/print-sheet'

const api = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => api,
}))

function shift(id: string, patch: Partial<SheetShift> = {}): SheetShift {
  return {
    id,
    task_id: 't1',
    date: '2026-12-05',
    start_time: '10:00:00',
    end_time: '12:00:00',
    title: 'Kuchen',
    location: 'Aula',
    location_id: null,
    batch_id: null,
    capacity: 2,
    free: null,
    vouchers: 0,
    ...patch,
  }
}

function entry(id: string, shiftId: string): TaskBookingEntry {
  return { id, shift_id: shiftId, user_name: id }
}

/** Answer each task's bookings, or fail for the tasks in `failing`. */
function serveBookings(byTask: Record<string, TaskBookingEntry[]>, failing: string[] = []) {
  api.get.mockImplementation(({ url }: { url: string }) => {
    const taskId = url.split('/')[2]!
    if (failing.includes(taskId)) return Promise.reject(new Error('boom'))
    return Promise.resolve({ data: byTask[taskId] ?? [] })
  })
}

beforeEach(() => {
  vi.resetAllMocks()
})

describe('usePrintSheet', () => {
  it('starts with every day ticked and a column only where a task’s shifts differ', () => {
    const sheet = usePrintSheet()
    sheet.reset(
      [
        [shift('a', { date: '2026-12-06' }), shift('b')],
        [shift('c', { title: 'Bar' }), shift('d', { title: 'Theke', location: 'Aula' })],
      ],
      ['t1', 't2'],
    )
    expect(sheet.dates.value).toEqual(['2026-12-05', '2026-12-06'])
    expect([...sheet.selectedDates.value]).toEqual(['2026-12-05', '2026-12-06'])
    expect(sheet.showTitle.value).toBe(true)
    expect(sheet.showLocation.value).toBe(false)
    expect(sheet.options.value).toEqual({
      showTitle: true,
      showLocation: false,
      repeatHeader: true,
      includeNames: false,
      paperLines: true,
    })
  })

  it('shows only the shifts on days still ticked', () => {
    const sheet = usePrintSheet()
    const later = shift('a', { date: '2026-12-06' })
    sheet.reset([[later, shift('b')]], ['t1'])
    sheet.selectedDates.value = new Set(['2026-12-06'])
    expect(sheet.visible([later, shift('b')])).toEqual([later])
  })

  it('fetches the names once, per task, when they are asked for', async () => {
    serveBookings({ t1: [entry('Mia', 's1'), entry('Tom', 's1')], t2: [entry('Ida', 's2')] })
    const sheet = usePrintSheet()
    sheet.reset([[shift('s1')], [shift('s2')]], ['t1', 't2'])

    await sheet.setIncludeNames(true)
    await sheet.setIncludeNames(false)
    await sheet.setIncludeNames(true)

    expect(api.get).toHaveBeenCalledTimes(2)
    expect(api.get).toHaveBeenCalledWith({ url: '/tasks/t1/bookings' })
    expect(sheet.bookings.value.get('s1')?.map((b) => b.id)).toEqual(['Mia', 'Tom'])
    expect(sheet.bookings.value.get('s2')?.map((b) => b.id)).toEqual(['Ida'])
    expect(sheet.bookingsLoading.value).toBe(false)
  })

  it('keeps blank lines for a task whose names fail to load', async () => {
    serveBookings({ t2: [entry('Ida', 's2')] }, ['t1'])
    const sheet = usePrintSheet()
    sheet.reset([[shift('s1')], [shift('s2')]], ['t1', 't2'])

    await sheet.setIncludeNames(true)

    expect(sheet.bookings.value.has('s1')).toBe(false)
    expect(sheet.bookings.value.get('s2')).toHaveLength(1)
  })

  it('waits for the names already on their way rather than asking again', async () => {
    serveBookings({ t1: [entry('Mia', 's1')] })
    const sheet = usePrintSheet()
    sheet.reset([[shift('s1')]], ['t1'])
    await Promise.all([sheet.setIncludeNames(true), sheet.setIncludeNames(true)])
    expect(api.get).toHaveBeenCalledOnce()
    expect(sheet.bookings.value.get('s1')).toHaveLength(1)
  })

  it('drops names that arrive for sheets replaced meanwhile', async () => {
    let answer: (value: unknown) => void = () => {}
    api.get.mockReturnValueOnce(new Promise((resolve) => (answer = resolve)))
    const sheet = usePrintSheet()
    sheet.reset([[shift('s1')]], ['t1'])
    const stale = sheet.setIncludeNames(true)
    expect(sheet.bookingsLoading.value).toBe(true)

    sheet.reset([[shift('s2')]], ['t2'])
    answer({ data: [entry('Mia', 's1')] })
    await stale

    expect(sheet.bookings.value.size).toBe(0)
    expect(sheet.bookingsLoading.value).toBe(false)
  })

  it('asks for the names of new sheets again after a reset', async () => {
    serveBookings({})
    const sheet = usePrintSheet()
    sheet.reset([[shift('s1')]], ['t1'])
    await sheet.setIncludeNames(true)
    sheet.reset([[shift('s1')]], ['t1'])
    await sheet.setIncludeNames(true)
    expect(api.get).toHaveBeenCalledTimes(2)
  })

  it('fills the names of new sheets in at once while they are shown', async () => {
    serveBookings({ t2: [entry('Ida', 's2')] })
    const sheet = usePrintSheet()
    sheet.reset([[shift('s1')]], ['t1'])
    await sheet.setIncludeNames(true)

    sheet.reset([[shift('s2')]], ['t2'])
    expect(sheet.bookingsLoading.value).toBe(true)
    await vi.waitFor(() => expect(sheet.bookings.value.get('s2')).toHaveLength(1))
    expect(sheet.includeNames.value).toBe(true)
  })

  describe('refresh', () => {
    const monday = shift('a', { date: '2026-12-07' })
    const tuesday = shift('b', { date: '2026-12-08' })
    const wednesday = shift('c', { date: '2026-12-09' })

    it('keeps the viewer’s days and columns, and ticks a day new to the sheets', () => {
      const sheet = usePrintSheet()
      sheet.reset([[monday, tuesday]], ['t1'])
      sheet.selectedDates.value = new Set(['2026-12-08'])
      sheet.showTitle.value = true

      sheet.refresh([[monday, tuesday, wednesday]], ['t1'])

      expect(sheet.dates.value).toEqual(['2026-12-07', '2026-12-08', '2026-12-09'])
      expect([...sheet.selectedDates.value]).toEqual(['2026-12-08', '2026-12-09'])
      expect(sheet.showTitle.value).toBe(true)
    })

    it('starts over when the sheets had nothing to show', () => {
      const sheet = usePrintSheet()
      sheet.reset([], [])
      sheet.refresh([[monday, shift('d', { date: '2026-12-07', title: 'Bar' })]], ['t1'])

      expect([...sheet.selectedDates.value]).toEqual(['2026-12-07'])
      expect(sheet.showTitle.value).toBe(true)
    })

    it('fetches the names again while they are shown', async () => {
      serveBookings({ t1: [entry('Mia', 'a')] })
      const sheet = usePrintSheet()
      sheet.reset([[monday]], ['t1'])
      await sheet.setIncludeNames(true)

      sheet.refresh([[monday]], ['t1'])
      await vi.waitFor(() => expect(sheet.bookingsLoading.value).toBe(false))

      expect(api.get).toHaveBeenCalledTimes(2)
      expect(sheet.bookings.value.get('a')).toHaveLength(1)
    })
  })

  describe('loading', () => {
    function row(id: string, taskId: string, patch: Partial<ShiftRead> = {}): ShiftRead {
      return {
        id,
        task_id: taskId,
        title: `Title ${id}`,
        date: '2026-12-05',
        start_time: '10:00:00',
        created_at: '',
        updated_at: '',
        ...patch,
      }
    }

    const detail = { id: 'l1' } as SharedListDetail
    const preview = {
      days: [
        {
          date: '2026-12-05',
          shifts: [
            { id: 's1', task_id: 't1', capacity: 2, free: 1, full: false, vouchers: 2 },
            { id: 's2', task_id: 't2', capacity: 1, free: 0, full: true },
          ],
        },
      ],
    } as unknown as PublicSharedList

    function serve(rows: Record<string, ShiftRead[]>, failing: string[] = []) {
      api.get.mockImplementation(({ url, query }: { url: string; query?: { task_id: string } }) => {
        if (url === '/shared-lists/l1') return Promise.resolve({ data: detail })
        if (url === '/shared-lists/l1/preview') return Promise.resolve({ data: preview })
        if (url === '/shifts/') {
          const taskId = query!.task_id
          if (failing.includes(taskId)) return Promise.reject(new Error('boom'))
          return Promise.resolve({ data: { items: rows[taskId] ?? [] } })
        }
        if (url === '/locations/loc1') {
          return Promise.resolve({ data: { id: 'loc1', pins: [{ id: 'p1' }] } })
        }
        return Promise.reject(new Error(`unexpected GET ${url}`))
      })
    }

    it('fetches each task’s shifts, none for a task that fails', async () => {
      serve({ t1: [row('s1', 't1')] }, ['t2'])
      const shifts = await usePrintSheet().fetchShifts(['t1', 't2'])

      expect(shifts.get('t1')?.map((s) => s.id)).toEqual(['s1'])
      expect(shifts.get('t2')).toEqual([])
      expect(api.get).toHaveBeenCalledWith({
        url: '/shifts/',
        query: { task_id: 't1', limit: 200 },
      })
    })

    it('reads a list’s offer by task, with what only the shift rows carry', async () => {
      serve({ t1: [row('s1', 't1', { title: 'Backen', batch_id: 'b1' })] })
      const { list, offered } = await usePrintSheet().fetchListSheet('l1')

      expect(list).toBe(detail)
      expect([...offered.keys()]).toEqual(['t1', 't2'])
      expect(offered.get('t1')).toEqual([
        expect.objectContaining({
          id: 's1',
          title: 'Backen',
          batch_id: 'b1',
          free: 1,
          vouchers: 2,
        }),
      ])
      expect(offered.get('t2')).toEqual([expect.objectContaining({ id: 's2', title: null })])
    })

    it('takes the shift rows the page has rather than fetching them', async () => {
      serve({})
      const known = new Map([['s1', row('s1', 't1', { title: 'Backen' })]])
      const { offered } = await usePrintSheet().fetchListSheet('l1', known)

      expect(offered.get('t1')?.[0]?.title).toBe('Backen')
      expect(api.get).toHaveBeenCalledTimes(2)
    })

    it('has a map while there is a place and it is shown', async () => {
      serve({})
      const sheet = usePrintSheet()
      expect(sheet.mapFor('e1')).toBeNull()

      await sheet.loadLocation('loc1')
      expect(sheet.pin.value).toEqual({ id: 'p1' })
      expect(sheet.mapFor('e1')).toEqual({ eventId: 'e1', pin: { id: 'p1' }, locationId: 'loc1' })
      expect(sheet.mapFor(null)).toBeNull()
      sheet.showMap.value = false
      expect(sheet.mapFor('e1')).toBeNull()

      await sheet.loadLocation(null)
      expect(sheet.pin.value).toBeNull()
    })

    it('prints without a map when the place fails to load', async () => {
      api.get.mockRejectedValue(new Error('boom'))
      const sheet = usePrintSheet()
      await sheet.loadLocation('loc1')
      expect(sheet.mapFor('e1')).toBeNull()
    })
  })

  describe('print', () => {
    const print = vi.fn()

    beforeEach(() => {
      vi.useFakeTimers()
      vi.stubGlobal('window', { print })
    })

    afterEach(() => {
      vi.useRealTimers()
      vi.unstubAllGlobals()
    })

    it('prints once every sheet has drawn and the page has settled', async () => {
      let drawn: () => void = () => {}
      const sheetReady = new Promise<void>((resolve) => (drawn = resolve))
      const sheet = usePrintSheet()

      const done = sheet.print([{ ready: () => sheetReady }, { ready: async () => {} }])
      await vi.advanceTimersByTimeAsync(SETTLE_MS)
      expect(print).not.toHaveBeenCalled()

      drawn()
      await vi.advanceTimersByTimeAsync(SETTLE_MS)
      await done
      expect(print).toHaveBeenCalledOnce()
    })

    it('loads the names first when they are shown', async () => {
      serveBookings({ t1: [entry('Mia', 's1')] })
      const sheet = usePrintSheet()
      sheet.reset([[shift('s1')]], ['t1'])
      sheet.includeNames.value = true

      const done = sheet.print([])
      await vi.advanceTimersByTimeAsync(SETTLE_MS)
      await done

      expect(sheet.bookings.value.get('s1')).toHaveLength(1)
      expect(print).toHaveBeenCalledOnce()
    })
  })
})
