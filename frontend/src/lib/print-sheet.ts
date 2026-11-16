/**
 * The printed sheet of shifts: which shifts it lists, in which order, and the
 * lines each gets for a name.
 *
 * A task's own sheet lists every shift with a line per place. A shared list's
 * sheet lists only the shifts the list offers, with their free places and
 * vouchers, and a line per free place: the other places are taken already,
 * online or on paper.
 */
import type {
  LocationPin,
  PublicSharedList,
  ShiftBatchRead,
  ShiftRead,
  TaskBookingEntry,
} from '@/client/types.gen'

export interface SheetShift {
  id: string
  task_id: string
  date: string
  start_time: string | null
  end_time: string | null
  title: string | null
  location: string | null
  location_id: string | null
  batch_id: string | null
  capacity: number
  /** A shared list's sheet: the places still free. `null` on a task's own sheet. */
  free: number | null
  /** The vouchers the shift earns; 0 for none. */
  vouchers: number
}

/** The shifts of one task, as one part of a sheet. */
export interface SheetSection {
  key: string
  /** Over the part; a sheet of several tasks tells them apart by name. */
  heading: string | null
  shifts: SheetShift[]
  /** The task's batches; with more than one, the shifts are grouped by them. */
  batches: ShiftBatchRead[]
  /** Organisers and the task's people in charge, who see phone numbers. */
  canSeeContacts: boolean
}

/** What the print toolbar puts on the sheet. */
export interface SheetOptions {
  showTitle: boolean
  showLocation: boolean
  repeatHeader: boolean
  includeNames: boolean
  /** A shared list's sheet: a blank line for each free place. */
  paperLines: boolean
}

export interface SheetLine {
  name: string
  contact: string
}

/** The place on the venue plan a sheet shows, when every shift shares one. */
export interface SheetMap {
  eventId: string
  pin: LocationPin
  locationId: string | null
}

/** A shift on a task's own sheet. */
export function fromShift(shift: ShiftRead): SheetShift {
  return {
    id: shift.id,
    task_id: shift.task_id,
    date: shift.date,
    start_time: shift.start_time ?? null,
    end_time: shift.end_time ?? null,
    title: shift.title,
    location: shift.location ?? null,
    location_id: shift.location_id ?? null,
    batch_id: shift.batch_id ?? null,
    capacity: shift.max_bookings ?? 1,
    free: null,
    vouchers: 0,
  }
}

/**
 * The shifts `list` offers, in its order. `known` adds what only the task's
 * own shift rows carry (the title, the place on the plan, the batch); a shift
 * missing there still prints, without them.
 */
export function offeredShifts(
  list: Pick<PublicSharedList, 'days'>,
  known: ReadonlyMap<string, ShiftRead>,
): SheetShift[] {
  return list.days.flatMap((day) =>
    day.shifts.map((offered) => {
      const shift = known.get(offered.id)
      return {
        id: offered.id,
        task_id: offered.task_id,
        date: day.date,
        start_time: offered.start_time ?? null,
        end_time: offered.end_time ?? null,
        title: shift?.title ?? null,
        location: offered.location ?? null,
        location_id: shift?.location_id ?? null,
        batch_id: shift?.batch_id ?? null,
        capacity: offered.capacity,
        free: offered.free,
        vouchers: offered.vouchers ?? 0,
      }
    }),
  )
}

/** The shifts of each task, the tasks in the order their first shift comes. */
export function byTask(shifts: readonly SheetShift[]): Map<string, SheetShift[]> {
  const tasks = new Map<string, SheetShift[]>()
  for (const shift of shifts) {
    const own = tasks.get(shift.task_id)
    if (own) own.push(shift)
    else tasks.set(shift.task_id, [shift])
  }
  return tasks
}

/** Days in order, each with its shifts by start and then end; untimed first. */
export function byDay(shifts: readonly SheetShift[]): [string, SheetShift[]][] {
  const days = new Map<string, SheetShift[]>()
  for (const shift of shifts) {
    const day = days.get(shift.date)
    if (day) day.push(shift)
    else days.set(shift.date, [shift])
  }
  for (const day of days.values()) {
    day.sort(
      (a, b) =>
        (a.start_time ?? '').localeCompare(b.start_time ?? '') ||
        (a.end_time ?? '').localeCompare(b.end_time ?? ''),
    )
  }
  return [...days].sort(([a], [b]) => a.localeCompare(b))
}

export interface BatchGroup {
  batch: ShiftBatchRead | null
  shifts: SheetShift[]
}

/**
 * The shifts by batch, in the batches' order, those of no batch last. One
 * batch or none: a single group without a heading.
 */
export function byBatch(
  shifts: readonly SheetShift[],
  batches: readonly ShiftBatchRead[],
): BatchGroup[] {
  if (batches.length <= 1) return [{ batch: null, shifts: [...shifts] }]
  const groups: BatchGroup[] = batches.map((batch) => ({
    batch,
    shifts: shifts.filter((shift) => shift.batch_id === batch.id),
  }))
  const known = new Set(batches.map((batch) => batch.id))
  groups.push({
    batch: null,
    shifts: shifts.filter((shift) => !shift.batch_id || !known.has(shift.batch_id)),
  })
  return groups.filter((group) => group.shifts.length > 0)
}

/** Whether the shifts differ in a value: then its column is worth printing. */
export function varies(
  shifts: readonly SheetShift[],
  pick: (shift: SheetShift) => string | null,
): boolean {
  return new Set(shifts.map(pick).filter(Boolean)).size > 1
}

/** Every day the shifts are on, in order. */
export function shiftDates(shifts: readonly SheetShift[]): string[] {
  return [...new Set(shifts.map((shift) => shift.date))].sort()
}

/**
 * The lines of one shift: the booked names first when they are shown, then
 * blank lines. A task's own sheet keeps a line for every place; a list's
 * sheet has blank lines only for the free places, and only with `paperLines`.
 */
export function sheetLines(
  shift: SheetShift,
  booked: readonly TaskBookingEntry[],
  options: { includeNames: boolean; paperLines: boolean },
): SheetLine[] {
  const shown = options.includeNames ? booked : []
  const named = (shift.free === null ? shown.slice(0, shift.capacity) : shown).map((entry) => ({
    name: entry.user_name ?? '',
    contact: entry.user_phone_number ?? '',
  }))
  let blank = 0
  if (shift.free === null) blank = shift.capacity - named.length
  else if (options.paperLines) blank = shift.free
  return [
    ...named,
    ...Array.from({ length: Math.max(0, blank) }, () => ({ name: '', contact: '' })),
  ]
}
