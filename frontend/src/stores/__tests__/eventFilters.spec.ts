// @vitest-environment jsdom
import { nextTick } from 'vue'

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useTaskFiltersStore } from '@/stores/eventFilters'

const STORAGE_KEY = 'wirksam:tasks:filters'

/** The store reads localStorage during setup, so seed it before instantiating. */
function seed(value: unknown) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
}

function readPersisted(): Record<string, unknown> {
  const raw = localStorage.getItem(STORAGE_KEY)
  return raw ? (JSON.parse(raw) as Record<string, unknown>) : {}
}

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})

describe('useTaskFiltersStore', () => {
  describe('initial state', () => {
    it('uses the documented defaults when nothing is persisted', () => {
      const store = useTaskFiltersStore()

      expect(store.searchQuery).toBe('')
      expect(store.viewMode).toBe('list')
      expect(store.focusMode).toBe('today')
      expect(store.myBookingsOnly).toBe(false)
      expect(store.hideFullShifts).toBe(false)
      expect(store.dateFrom).toBeNull()
      expect(store.dateTo).toBeNull()
      expect(store.locationId).toBeNull()
    })

    it('hydrates every persisted field', () => {
      seed({
        viewMode: 'calendar',
        focusMode: 'first-available',
        myBookingsOnly: true,
        hideFullShifts: true,
        dateFrom: '2026-08-01',
        dateTo: '2026-08-31',
      })

      const store = useTaskFiltersStore()

      expect(store.viewMode).toBe('calendar')
      expect(store.focusMode).toBe('first-available')
      expect(store.myBookingsOnly).toBe(true)
      expect(store.hideFullShifts).toBe(true)
      expect(store.dateFrom).toBe('2026-08-01')
      expect(store.dateTo).toBe('2026-08-31')
    })

    it('falls back per field when only part of the payload was stored', () => {
      seed({ viewMode: 'box', dateTo: '2026-09-30' })

      const store = useTaskFiltersStore()

      expect(store.viewMode).toBe('box')
      expect(store.focusMode).toBe('today')
      expect(store.myBookingsOnly).toBe(false)
      expect(store.dateFrom).toBeNull()
      expect(store.dateTo).toBe('2026-09-30')
    })

    it('ignores corrupted JSON in localStorage', () => {
      localStorage.setItem(STORAGE_KEY, '{ not json')

      const store = useTaskFiltersStore()

      expect(store.viewMode).toBe('list')
      expect(store.focusMode).toBe('today')
    })

    it('never persists the search query', () => {
      seed({ viewMode: 'box' })

      const store = useTaskFiltersStore()

      expect(store.searchQuery).toBe('')
      expect(readPersisted()).not.toHaveProperty('searchQuery')
    })
  })

  describe('persistence', () => {
    it('writes the filter snapshot back to localStorage on change', async () => {
      const store = useTaskFiltersStore()

      store.viewMode = 'calendar'
      store.myBookingsOnly = true
      store.dateFrom = '2026-08-04'
      await nextTick()

      expect(readPersisted()).toEqual({
        viewMode: 'calendar',
        focusMode: 'today',
        myBookingsOnly: true,
        hideFullShifts: false,
        dateFrom: '2026-08-04',
        dateTo: null,
      })
    })

    it('does not touch localStorage before anything changes', () => {
      useTaskFiltersStore()

      expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
    })

    it('round-trips through a freshly created store', async () => {
      const first = useTaskFiltersStore()
      first.focusMode = 'first-available'
      first.hideFullShifts = true
      await nextTick()

      setActivePinia(createPinia())
      const second = useTaskFiltersStore()

      expect(second.focusMode).toBe('first-available')
      expect(second.hideFullShifts).toBe(true)
    })
  })

  describe('hasCustomDateRange', () => {
    it('is false when both bounds are unset', () => {
      const store = useTaskFiltersStore()

      expect(store.hasCustomDateRange).toBe(false)
    })

    it('is true with only a lower bound', () => {
      const store = useTaskFiltersStore()

      store.dateFrom = '2026-08-01'

      expect(store.hasCustomDateRange).toBe(true)
    })

    it('is true with only an upper bound', () => {
      const store = useTaskFiltersStore()

      store.dateTo = '2026-08-31'

      expect(store.hasCustomDateRange).toBe(true)
    })
  })

  describe('activeFilterCount', () => {
    it('is zero on a pristine store', () => {
      const store = useTaskFiltersStore()

      expect(store.activeFilterCount).toBe(0)
    })

    it('counts a date range once even when both bounds are set', () => {
      const store = useTaskFiltersStore()

      store.dateFrom = '2026-08-01'
      store.dateTo = '2026-08-31'

      expect(store.activeFilterCount).toBe(1)
    })

    it('counts every active content filter', () => {
      const store = useTaskFiltersStore()

      store.myBookingsOnly = true
      store.hideFullShifts = true
      store.dateFrom = '2026-08-01'
      store.searchQuery = 'bar'
      store.locationId = 'loc-1'

      expect(store.activeFilterCount).toBe(5)
    })

    it('ignores a whitespace-only search query', () => {
      const store = useTaskFiltersStore()

      store.searchQuery = '   '

      expect(store.activeFilterCount).toBe(0)
    })

    it('ignores view and focus mode', () => {
      const store = useTaskFiltersStore()

      store.viewMode = 'calendar'
      store.focusMode = 'first-available'

      expect(store.activeFilterCount).toBe(0)
    })
  })

  describe('resetFilters', () => {
    it('clears content filters but keeps view and focus mode', () => {
      const store = useTaskFiltersStore()
      store.viewMode = 'calendar'
      store.focusMode = 'first-available'
      store.searchQuery = 'bar'
      store.myBookingsOnly = true
      store.hideFullShifts = true
      store.dateFrom = '2026-08-01'
      store.dateTo = '2026-08-31'
      store.locationId = 'loc-1'

      store.resetFilters()

      expect(store.locationId).toBeNull()
      expect(store.searchQuery).toBe('')
      expect(store.myBookingsOnly).toBe(false)
      expect(store.hideFullShifts).toBe(false)
      expect(store.dateFrom).toBeNull()
      expect(store.dateTo).toBeNull()
      expect(store.activeFilterCount).toBe(0)
      expect(store.viewMode).toBe('calendar')
      expect(store.focusMode).toBe('first-available')
    })

    it('is safe to call on a pristine store', () => {
      const store = useTaskFiltersStore()

      store.resetFilters()

      expect(store.activeFilterCount).toBe(0)
    })
  })

  describe('locationId', () => {
    it('is never persisted', async () => {
      const store = useTaskFiltersStore()

      store.locationId = 'loc-1'
      store.myBookingsOnly = true
      await nextTick()

      expect(readPersisted()).not.toHaveProperty('locationId')
      setActivePinia(createPinia())
      expect(useTaskFiltersStore().locationId).toBeNull()
    })

    it('survives the first setLocationEvent, so a URL-seeded filter sticks', () => {
      const store = useTaskFiltersStore()
      store.locationId = 'loc-1'

      store.setLocationEvent('event-a')

      expect(store.locationId).toBe('loc-1')
    })

    it('stays when the same event is reported again', () => {
      const store = useTaskFiltersStore()
      store.setLocationEvent('event-a')
      store.locationId = 'loc-1'

      store.setLocationEvent('event-a')

      expect(store.locationId).toBe('loc-1')
    })

    it('is cleared when the selected event changes', () => {
      const store = useTaskFiltersStore()
      store.setLocationEvent('event-a')
      store.locationId = 'loc-1'
      store.myBookingsOnly = true

      store.setLocationEvent('event-b')

      expect(store.locationId).toBeNull()
      expect(store.myBookingsOnly).toBe(true)
    })

    it('is cleared when the event selection goes away', () => {
      const store = useTaskFiltersStore()
      store.setLocationEvent('event-a')
      store.locationId = 'loc-1'

      store.setLocationEvent(null)

      expect(store.locationId).toBeNull()
    })
  })

  describe('clearDateRange', () => {
    it('drops both bounds and leaves other filters alone', () => {
      const store = useTaskFiltersStore()
      store.myBookingsOnly = true
      store.dateFrom = '2026-08-01'
      store.dateTo = '2026-08-31'

      store.clearDateRange()

      expect(store.dateFrom).toBeNull()
      expect(store.dateTo).toBeNull()
      expect(store.hasCustomDateRange).toBe(false)
      expect(store.myBookingsOnly).toBe(true)
      expect(store.activeFilterCount).toBe(1)
    })
  })
})
