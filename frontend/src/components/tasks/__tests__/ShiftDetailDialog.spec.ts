// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import ShiftDetailDialog from '@/components/tasks/ShiftDetailDialog.vue'

import type { LocationDetailRead, ShiftRead, TaskRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * One shift, as whoever runs the task sees it: what and when, the place and
 * what it earns as chips, who is in charge, who signed up and the place's
 * description and plan. The task page and the task list hand over the people
 * in charge; the dashboard and the map don't know them, so the dialog reads
 * the task itself there.
 */

const phone = vi.hoisted(() => ({ value: false }))
vi.mock('@vueuse/core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@vueuse/core')>()
  const { ref: vueRef } = await import('vue')
  return { ...actual, useMediaQuery: () => vueRef(phone.value) }
})

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => api,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ profile: { id: 'u-pia', time_format: 'h24' }, user: null }),
}))
vi.mock('@/composables/useDialog', () => ({
  useDialog: () => ({ confirmDestructive: vi.fn() }),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))

const thisYear = new Date().getFullYear()

function shift(overrides: Partial<ShiftRead> = {}): ShiftRead {
  return {
    id: 's1',
    task_id: 't1',
    event_id: 'e1',
    title: 'Cafétheke 14:00-17:00',
    // Far enough ahead to be bookable, in this year so the line leaves it out.
    date: `${thisYear}-12-19`,
    start_time: '14:00:00',
    end_time: '17:00:00',
    location: 'Foyer-Café',
    location_id: null,
    category: 'Verpflegung',
    max_bookings: 3,
    current_bookings: 0,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
    ...overrides,
  } as ShiftRead
}

const managers = [
  { user_id: 'u-mira', name: 'Mira Lindqvist' },
  { user_id: 'u-pia', name: 'Pia Incharge' },
]

function task(overrides: Partial<TaskRead> = {}): TaskRead {
  return {
    id: 't1',
    name: 'Cafétheke',
    status: 'published',
    event_id: 'e1',
    start_date: `${thisYear}-12-18`,
    end_date: `${thisYear}-12-20`,
    vouchers_per_shift: 2,
    can_manage: true,
    managers,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
    ...overrides,
  } as TaskRead
}

function location(overrides: Partial<LocationDetailRead> = {}): LocationDetailRead {
  return {
    id: 'l1',
    event_id: 'e1',
    name: 'Foyer-Café',
    description: 'Theke an der Rückwand des Foyers.',
    pins: [],
    ...overrides,
  } as unknown as LocationDetailRead
}

/** Answers the dialog's reads by URL. */
function routes(map: Record<string, unknown>) {
  api.get.mockImplementation(({ url }: { url: string }) => {
    if (url in map) return Promise.resolve({ data: map[url] })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

const passthrough = { template: '<div><slot /></div>' }
const dialogStub = { props: ['open'], template: '<div v-if="open"><slot /></div>' }

async function openDialog(props: Record<string, unknown> = {}) {
  const w = mount(ShiftDetailDialog, {
    props: { open: false, shift: shift(), taskName: 'Cafétheke', ...props },
    global: {
      plugins: [i18n],
      stubs: {
        ResponsiveDialog: dialogStub,
        ResponsiveDialogContent: passthrough,
        ResponsiveDialogHeader: passthrough,
        ResponsiveDialogTitle: passthrough,
        ResponsiveDialogDescription: passthrough,
        ResponsiveDialogBody: passthrough,
        ResponsiveDialogFooter: passthrough,
        ResponsiveDialogClose: passthrough,
        LocationDescription: { props: ['location'], template: '<p>{{ location.description }}</p>' },
        VenueMiniMap: { template: '<div data-stub="mini-map" />' },
        TeamJoinButton: true,
      },
    },
  })
  await w.setProps({ open: true })
  await flushPromises()
  return w
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
  phone.value = false
  vi.clearAllMocks()
  routes({ '/shifts/s1/bookings': [], '/tasks/t1': task() })
})

describe('ShiftDetailDialog', () => {
  it('says when, in full, and leaves the year out when it is this one', async () => {
    i18n.global.locale.value = 'de'
    const w = await openDialog()
    expect(w.find('[data-testid="shift-detail-title"]').text()).toBe('Cafétheke')
    const when = new Date(`${thisYear}-12-19T00:00:00`).toLocaleDateString('de', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
    })
    expect(w.text()).toContain(`${when} · 14:00 – 17:00`)
    expect(w.text()).not.toContain(String(thisYear))
  })

  it('shows the place, the category and what a shift earns as chips', async () => {
    const w = await openDialog({ managers, vouchersPerShift: 2 })
    const facts = w.find('[data-testid="shift-detail-facts"]')
    expect(facts.text()).toContain('Foyer-Café')
    expect(facts.text()).toContain('Verpflegung')
    expect(w.find('[data-testid="shift-detail-vouchers"]').text()).toBe('2 vouchers per person')
  })

  it('leaves the category out on a phone, and the vouchers when there are none', async () => {
    phone.value = true
    const w = await openDialog({ managers, vouchersPerShift: 0 })
    const facts = w.find('[data-testid="shift-detail-facts"]')
    expect(facts.text()).toContain('Foyer-Café')
    expect(facts.text()).not.toContain('Verpflegung')
    expect(w.find('[data-testid="shift-detail-vouchers"]').exists()).toBe(false)
  })

  it('names the people in charge, the viewer last as "you", without reading the task', async () => {
    const w = await openDialog({ managers })
    expect(w.find('[data-testid="shift-in-charge-names"]').text()).toBe('Mira Lindqvist and you')
    expect(api.get).not.toHaveBeenCalledWith({ url: '/tasks/t1' })
  })

  it('says "You" when the viewer is the only one in charge', async () => {
    const w = await openDialog({ managers: [managers[1]] })
    expect(w.find('[data-testid="shift-in-charge-names"]').text()).toBe('You')
  })

  it('has no in-charge line for a task nobody runs', async () => {
    const w = await openDialog({ managers: [] })
    expect(w.find('[data-testid="shift-in-charge"]').exists()).toBe(false)
  })

  it('reads the task for its people in charge and vouchers when the caller has neither', async () => {
    i18n.global.locale.value = 'de'
    routes({ '/shifts/s1': shift(), '/shifts/s1/bookings': [], '/tasks/t1': task() })
    const w = await openDialog({ shift: null, shiftId: 's1', taskName: null })
    expect(api.get).toHaveBeenCalledWith({ url: '/tasks/t1' })
    expect(w.find('[data-testid="shift-in-charge-names"]').text()).toBe('Mira Lindqvist und du')
    expect(w.find('[data-testid="shift-detail-vouchers"]').text()).toBe('2 Marken pro Person')
  })

  it('keeps going without the in-charge line when the task cannot be read', async () => {
    routes({ '/shifts/s1/bookings': [] })
    const w = await openDialog()
    expect(w.find('[data-testid="shift-in-charge"]').exists()).toBe(false)
    expect(w.find('[data-testid="shift-roster"]').exists()).toBe(true)
  })

  it('offers "Sign me up" beside Close on a desktop', async () => {
    const w = await openDialog({ managers })
    const footer = w.find('[data-testid="shift-detail-footer"]')
    expect(footer.text()).toContain('Close')
    expect(w.find('[data-testid="btn-book-shift"]').text()).toBe('Sign me up')
  })

  it('leaves Close to the sheet itself on a phone', async () => {
    phone.value = true
    const w = await openDialog({ managers })
    expect(w.find('[data-testid="shift-detail-footer"]').text()).not.toContain('Close')
    expect(w.find('[data-testid="btn-book-shift"]').exists()).toBe(true)
  })

  it('puts the place description and the plan under "Location and site plan"', async () => {
    const pin = { plan_id: 'p1', plan_name: 'Erdgeschoss', x: 1, y: 1 }
    routes({
      '/shifts/s1/bookings': [],
      '/locations/l1': location({ pins: [pin] } as Partial<LocationDetailRead>),
    })
    const w = await openDialog({ managers, shift: shift({ location_id: 'l1' }) })
    const place = w.find('[data-testid="shift-location-details"]')
    expect(place.text()).toContain('Location and site plan')
    // A short description starts open, with the plan under it.
    expect(place.text()).toContain('Theke an der Rückwand des Foyers.')
    expect(place.find('[data-testid="shift-mini-map"]').exists()).toBe(true)
  })

  it('calls it "About this place" when there is no plan to show', async () => {
    routes({ '/shifts/s1/bookings': [], '/locations/l1': location() })
    const w = await openDialog({ managers, shift: shift({ location_id: 'l1' }) })
    const place = w.find('[data-testid="shift-location-details"]')
    expect(place.text()).toContain('About this place')
    expect(w.find('[data-testid="shift-mini-map"]').exists()).toBe(false)
  })
})
