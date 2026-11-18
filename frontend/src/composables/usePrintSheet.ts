import { computed, nextTick, ref, shallowRef } from 'vue'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import type {
  LocationDetailRead,
  PublicSharedList,
  SharedListDetail,
  ShiftListResponse,
  ShiftRead,
  TaskBookingEntry,
} from '@/client/types.gen'
import {
  type SheetMap,
  type SheetOptions,
  type SheetShift,
  byTask,
  offeredShifts,
  shiftDates,
  varies,
} from '@/lib/print-sheet'

/** Something on the page that draws in its own time: a sheet's QR code and map. */
export interface Readiness {
  ready: () => Promise<void>
}

/** How long the browser gets to lay out what just drew before it prints. */
export const SETTLE_MS = 300

/**
 * What every print view shares: loading the shifts, a list's offer and the
 * place for the map; the display options, the days to print, the booked
 * names (fetched only once someone asks for them); and printing once every
 * sheet has drawn its QR code and map.
 */
export function usePrintSheet() {
  const { get } = useAuthenticatedClient()

  const showTitle = ref(true)
  const showLocation = ref(true)
  const repeatHeader = ref(true)
  const showMap = ref(true)
  const includeNames = ref(false)
  const paperLines = ref(true)

  /** Every day on the sheets, in order. */
  const dates = ref<string[]>([])
  const selectedDates = ref<Set<string>>(new Set())

  const bookings = shallowRef<ReadonlyMap<string, TaskBookingEntry[]>>(new Map())
  const bookingsLoading = ref(false)
  let bookingTasks: readonly string[] = []
  /** The names of the current sheets, fetched or on their way; new sheets drop them. */
  let pendingBookings: Promise<void> | null = null
  let generation = 0

  /** The place every shift shares, for the map. */
  const location = ref<LocationDetailRead | null>(null)
  const pin = computed(() => location.value?.pins?.[0] ?? null)

  const options = computed<SheetOptions>(() => ({
    showTitle: showTitle.value,
    showLocation: showLocation.value,
    repeatHeader: repeatHeader.value,
    includeNames: includeNames.value,
    paperLines: paperLines.value,
  }))

  /**
   * Start over with these sheets' shifts, one group per task: every day
   * ticked, and the title and place columns shown where a task's shifts
   * differ in them. `taskIds` are the tasks whose names can be filled in.
   */
  function reset(groups: readonly (readonly SheetShift[])[], taskIds: readonly string[]) {
    dates.value = shiftDates(groups.flat())
    selectedDates.value = new Set(dates.value)
    showTitle.value = groups.some((shifts) => varies(shifts, (shift) => shift.title))
    showLocation.value = groups.some((shifts) => varies(shifts, (shift) => shift.location))
    replaceNames(taskIds)
  }

  /**
   * The same sheets as they are now, after a fix in the toolbar: the viewer's
   * choices stay, and only a day not shown before comes ticked. Sheets that
   * had nothing to show start over.
   */
  function refresh(groups: readonly (readonly SheetShift[])[], taskIds: readonly string[]) {
    if (!dates.value.length) return reset(groups, taskIds)
    const known = new Set(dates.value)
    dates.value = shiftDates(groups.flat())
    selectedDates.value = new Set(
      dates.value.filter((date) => !known.has(date) || selectedDates.value.has(date)),
    )
    replaceNames(taskIds)
  }

  /** The names belong to the sheets they were fetched for; while shown, the new ones come. */
  function replaceNames(taskIds: readonly string[]) {
    bookingTasks = taskIds
    generation += 1
    pendingBookings = null
    bookings.value = new Map()
    bookingsLoading.value = false
    if (includeNames.value) void loadBookings()
  }

  /** The shifts on a day still ticked. */
  function visible(shifts: readonly SheetShift[]): SheetShift[] {
    return shifts.filter((shift) => selectedDates.value.has(shift.date))
  }

  /** Who booked which shift, one request per task. A task that fails keeps blank lines. */
  async function fetchBookings(ticket: number) {
    bookingsLoading.value = true
    const byShift = new Map<string, TaskBookingEntry[]>()
    await Promise.all(
      bookingTasks.map(async (taskId) => {
        try {
          const res = await get<{ data: TaskBookingEntry[] }>({ url: `/tasks/${taskId}/bookings` })
          for (const entry of res.data) {
            const list = byShift.get(entry.shift_id)
            if (list) list.push(entry)
            else byShift.set(entry.shift_id, [entry])
          }
        } catch {
          // Non-critical: the sheet prints with blank lines.
        }
      }),
    )
    // Sheets replaced meanwhile have names of their own to fetch.
    if (ticket !== generation) return
    bookings.value = byShift
    bookingsLoading.value = false
  }

  function loadBookings(): Promise<void> {
    pendingBookings ??= fetchBookings(generation)
    return pendingBookings
  }

  async function setIncludeNames(on: boolean) {
    includeNames.value = on
    if (on) await loadBookings()
  }

  /** Each task's own shift rows. A task that fails to load has none. */
  async function fetchShifts(taskIds: readonly string[]): Promise<Map<string, ShiftRead[]>> {
    const shifts = new Map<string, ShiftRead[]>()
    await Promise.all(
      taskIds.map((taskId) =>
        get<{ data: ShiftListResponse }>({
          url: '/shifts/',
          query: { task_id: taskId, limit: 200 },
        }).then(
          (res) => shifts.set(taskId, res.data.items),
          () => shifts.set(taskId, []),
        ),
      ),
    )
    return shifts
  }

  /**
   * A shared list and the shifts its notice prints, by task. `known` are the
   * tasks' own shift rows by id, for what the public page leaves out (title,
   * place on the plan, batch); without them, the offered tasks' are fetched.
   */
  async function fetchListSheet(
    listId: string,
    known?: ReadonlyMap<string, ShiftRead>,
  ): Promise<{ list: SharedListDetail; offered: Map<string, SheetShift[]> }> {
    const [detail, preview] = await Promise.all([
      get<{ data: SharedListDetail }>({ url: `/shared-lists/${listId}` }),
      get<{ data: PublicSharedList }>({ url: `/shared-lists/${listId}/preview` }),
    ])
    let rows = known
    if (!rows) {
      const taskIds = preview.data.days.flatMap((day) => day.shifts.map((shift) => shift.task_id))
      const own = await fetchShifts([...new Set(taskIds)])
      rows = new Map([...own.values()].flat().map((shift) => [shift.id, shift]))
    }
    return { list: detail.data, offered: byTask(offeredShifts(preview.data, rows)) }
  }

  /** The place on the plan for the map; none without an id or when it fails to load. */
  async function loadLocation(locationId: string | null) {
    location.value = null
    if (!locationId) return
    try {
      const res = await get<{ data: LocationDetailRead }>({ url: `/locations/${locationId}` })
      location.value = res.data
    } catch {
      // Non-critical: the sheet prints without the map.
    }
  }

  /** The map on a sheet of `eventId`, while there is a place and it is to be shown. */
  function mapFor(eventId: string | null | undefined): SheetMap | null {
    if (!eventId || !pin.value || !showMap.value) return null
    return { eventId, pin: pin.value, locationId: location.value?.id ?? null }
  }

  /** Print once the names are in and every sheet has drawn. */
  async function print(sheets: readonly Readiness[]) {
    if (includeNames.value) await loadBookings()
    await Promise.all(sheets.map((sheet) => sheet.ready()))
    await nextTick()
    await new Promise((resolve) => setTimeout(resolve, SETTLE_MS))
    window.print()
  }

  return {
    showTitle,
    showLocation,
    repeatHeader,
    showMap,
    includeNames,
    paperLines,
    dates,
    selectedDates,
    bookings,
    bookingsLoading,
    options,
    pin,
    reset,
    refresh,
    visible,
    setIncludeNames,
    fetchShifts,
    fetchListSheet,
    loadLocation,
    mapFor,
    print,
  }
}
