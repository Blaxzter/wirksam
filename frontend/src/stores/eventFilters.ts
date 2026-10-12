import { computed, ref, watch } from 'vue'

import { defineStore } from 'pinia'

export type ViewMode = 'list' | 'box' | 'calendar'
export type FocusMode = 'today' | 'first-available'

const STORAGE_KEY = 'wirksam:tasks:filters'

interface PersistedFilters {
  viewMode: ViewMode
  focusMode: FocusMode
  myBookingsOnly: boolean
  hideFullShifts: boolean
  dateFrom: string | null // YYYY-MM-DD or null (= today)
  dateTo: string | null // YYYY-MM-DD or null (= no upper bound)
}

function loadFromStorage(): Partial<PersistedFilters> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export const useTaskFiltersStore = defineStore('eventFilters', () => {
  const saved = loadFromStorage()

  const searchQuery = ref('')
  const viewMode = ref<ViewMode>(saved.viewMode ?? 'list')
  const focusMode = ref<FocusMode>(saved.focusMode ?? 'today')
  const myBookingsOnly = ref(saved.myBookingsOnly ?? false)
  const hideFullShifts = ref(saved.hideFullShifts ?? false)
  /** Custom start date for task filtering. null = today (default). */
  const dateFrom = ref<string | null>(saved.dateFrom ?? null)
  /** Custom end date for task filtering. null = no upper bound. */
  const dateTo = ref<string | null>(saved.dateTo ?? null)
  /**
   * Only tasks at this location. Not persisted: a location belongs to one
   * event, so a remembered id would silently empty the feed of the next one.
   */
  const locationId = ref<string | null>(null)
  // The event `locationId` belongs to; `undefined` until first told.
  let locationEventId: string | null | undefined = undefined

  // Persist filter state to localStorage
  const persistable = computed<PersistedFilters>(() => ({
    viewMode: viewMode.value,
    focusMode: focusMode.value,
    myBookingsOnly: myBookingsOnly.value,
    hideFullShifts: hideFullShifts.value,
    dateFrom: dateFrom.value,
    dateTo: dateTo.value,
  }))

  watch(persistable, (v) => localStorage.setItem(STORAGE_KEY, JSON.stringify(v)), { deep: true })

  /** Whether a custom (non-default) date range is active. */
  const hasCustomDateRange = computed(() => dateFrom.value !== null || dateTo.value !== null)

  /** Number of active content filters (excludes view/focus mode). */
  const activeFilterCount = computed(() => {
    let count = 0
    if (myBookingsOnly.value) count++
    if (hideFullShifts.value) count++
    if (hasCustomDateRange.value) count++
    if (searchQuery.value.trim()) count++
    if (locationId.value) count++
    return count
  })

  function resetFilters() {
    searchQuery.value = ''
    myBookingsOnly.value = false
    hideFullShifts.value = false
    dateFrom.value = null
    dateTo.value = null
    locationId.value = null
  }

  /**
   * Tell the store which event the feed shows. Switching to another event
   * drops the location filter; the first call only records the event, so a
   * location seeded from the URL survives page load.
   */
  function setLocationEvent(eventId: string | null) {
    if (locationEventId !== undefined && locationEventId !== eventId) locationId.value = null
    locationEventId = eventId
  }

  function clearDateRange() {
    dateFrom.value = null
    dateTo.value = null
  }

  return {
    searchQuery,
    viewMode,
    focusMode,
    myBookingsOnly,
    hideFullShifts,
    dateFrom,
    dateTo,
    locationId,
    hasCustomDateRange,
    activeFilterCount,
    resetFilters,
    setLocationEvent,
    clearDateRange,
  }
})
