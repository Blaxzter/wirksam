// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import VenueLocationSheet from '@/components/venue-map/VenueLocationSheet.vue'

import type { LocationRead, LocationShiftRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The location sheet's shift list: it must never show one place's (or day's)
 * shifts, with live Book buttons, under another place's title.
 */

const get = vi.fn()
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get, post: vi.fn() }),
}))

const passthrough = { template: '<div><slot /></div>' }
const stubs = {
  ResponsiveDialog: passthrough,
  ResponsiveDialogBody: passthrough,
  ResponsiveDialogContent: passthrough,
  ResponsiveDialogDescription: passthrough,
  ResponsiveDialogHeader: passthrough,
  ResponsiveDialogTitle: passthrough,
  ShiftDetailDialog: true,
  LocationDescription: true,
}

const place = (id: string): LocationRead => ({
  id,
  event_id: 'e1',
  name: id,
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T00:00:00Z',
})

const shift = (id: string): LocationShiftRead =>
  ({
    id,
    task_id: 't1',
    task_name: 'Bar',
    title: 'Bar',
    date: '2026-10-12',
    start_time: '10:00:00',
    end_time: '12:00:00',
    max_bookings: 2,
    current_bookings: 0,
    is_booked_by_me: false,
  }) as LocationShiftRead

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = 'en'
  get.mockReset()
})

describe('VenueLocationSheet', () => {
  it('clears the list when the location or day changes, keeps it on a reload', async () => {
    get.mockResolvedValueOnce({ data: [shift('s-a')] })
    const wrapper = mount(VenueLocationSheet, {
      props: { location: place('a'), day: '2026-10-12', open: true },
      global: { plugins: [i18n], stubs },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="sheet-book-s-a"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="sheet-book-s-a"]').attributes('aria-label')).toMatch(
      /^Book 10:00/,
    )

    // Another place: A's rows go at once, before B's answer arrives.
    let resolveB!: (v: unknown) => void
    get.mockReturnValueOnce(new Promise((r) => (resolveB = r)))
    await wrapper.setProps({ location: place('b') })
    expect(wrapper.find('[data-testid="sheet-book-s-a"]').exists()).toBe(false)
    resolveB({ data: [shift('s-b')] })
    await flushPromises()
    expect(wrapper.find('[data-testid="sheet-book-s-b"]').exists()).toBe(true)

    // Another day, same place: cleared as well.
    get.mockReturnValueOnce(new Promise(() => {}))
    await wrapper.setProps({ day: '2026-10-13' })
    expect(wrapper.find('[data-testid="sheet-book-s-b"]').exists()).toBe(false)
  })

  it('keeps the rows while the same location and day reload', async () => {
    get.mockResolvedValueOnce({ data: [shift('s-a')] })
    const wrapper = mount(VenueLocationSheet, {
      props: { location: place('a'), day: '2026-10-12', open: true },
      global: { plugins: [i18n], stubs },
    })
    await flushPromises()
    get.mockReturnValueOnce(new Promise(() => {}))
    // Closing and reopening the same place reloads the same pair.
    await wrapper.setProps({ open: false })
    await wrapper.setProps({ open: true })
    expect(wrapper.find('[data-testid="sheet-book-s-a"]').exists()).toBe(true)
  })
})
