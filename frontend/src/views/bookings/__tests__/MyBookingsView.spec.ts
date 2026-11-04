// @vitest-environment jsdom
import { RouterLinkStub, flushPromises, mount } from '@vue/test-utils'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { BookingReadWithShift, VoucherAccount } from '@/client/types.gen'
import i18n from '@/locales/i18n'
import MyBookingsView from '@/views/bookings/MyBookingsView.vue'

/**
 * "My bookings": each booking a card that opens it, with its day and time
 * ("· over" once it has ended), what it earns from the voucher account, and
 * where; the list by date, or grouped by task or place.
 */

const api = vi.hoisted(() => ({ get: vi.fn(), delete: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: api.get, delete: api.delete }),
}))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    selectedEventId: 'e1',
    selectedEvent: { id: 'e1', name: 'Summer fair by the river', voucher_task_count: 1 },
    profile: { id: 'u1', time_format: 'h24' },
  }),
}))
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ query: {} }),
}))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))

const booking = (over: Partial<BookingReadWithShift> = {}): BookingReadWithShift => ({
  id: 'b1',
  user_id: 'u1',
  shift_id: 's1',
  status: 'confirmed',
  created_at: '2026-07-01T10:00:00',
  updated_at: '2026-07-01T10:00:00',
  shift: {
    id: 's1',
    task_id: 't1',
    title: 'Grill 17:00',
    date: '2099-07-18',
    start_time: '17:00:00',
    end_time: '20:00:00',
    location: 'Meadow',
    task_name: 'Grill stand',
  },
  ...over,
})

const BOOKINGS: BookingReadWithShift[] = [
  booking(),
  booking({
    id: 'b2',
    shift_id: 's2',
    shift: {
      id: 's2',
      task_id: 't2',
      title: 'Wristbands 16:00',
      date: '2020-07-17',
      start_time: '16:00:00',
      end_time: '19:00:00',
      location: null,
      task_name: 'Wristband check',
    },
  }),
]

const ACCOUNT: VoucherAccount = {
  summary: { user_id: 'u1', earned: 2, upcoming: 2, redeemed: 0, adjusted: 0, available: 2 },
  shifts: [
    {
      booking_id: 'b1',
      task_name: 'Grill stand',
      title: 'Grill 17:00',
      date: '2099-07-18',
      ends_at: '2099-07-18T18:00:00',
      vouchers: 2,
      completed: false,
    },
  ],
  entries: [],
}

function routeApi() {
  api.get.mockImplementation(({ url }: { url: string }) => {
    if (url === '/bookings/me') {
      return Promise.resolve({ data: { items: BOOKINGS, total: 2, skip: 0, limit: 200 } })
    }
    if (url === '/events/e1/vouchers/me') return Promise.resolve({ data: ACCOUNT })
    return Promise.reject(new Error(`unexpected ${url}`))
  })
}

async function mountView() {
  const w = mount(MyBookingsView, {
    global: {
      plugins: [i18n],
      stubs: {
        RouterLink: RouterLinkStub,
        MyHoursCard: true,
        VoucherCodeDialog: true,
        DateRangePicker: true,
        HintTooltip: { template: '<div><slot /></div>' },
      },
    },
  })
  await flushPromises()
  return w
}

const cards = (w: Awaited<ReturnType<typeof mountView>>) =>
  w.findAll('[data-testid="booking-card"]')

beforeEach(() => {
  i18n.global.locale.value = 'en'
  vi.clearAllMocks()
  localStorage.clear()
  routeApi()
})

afterEach(() => {
  localStorage.clear()
})

describe('MyBookingsView', () => {
  it('names the selected event under the heading', async () => {
    const w = await mountView()
    expect(w.text()).toContain('Summer fair by the river')
  })

  it('lists the bookings by date, each with its day, time and place', async () => {
    const w = await mountView()
    const [first, second] = cards(w)
    expect(first.find('h3').text()).toBe('Wristband check')
    expect(first.text()).toContain('16:00 – 19:00 · over')
    expect(second.find('h3').text()).toBe('Grill stand')
    expect(second.text()).toContain('17:00 – 20:00')
    expect(second.text()).not.toContain('over')
    expect(second.text()).toContain('Meadow')
    expect(second.text()).toContain('Confirmed')
  })

  it('says what a booking earns, from the voucher account', async () => {
    const w = await mountView()
    const [wristbands, grill] = cards(w)
    expect(grill.find('[data-testid="booking-card-vouchers"]').text()).toBe('+2 vouchers')
    expect(wristbands.find('[data-testid="booking-card-vouchers"]').exists()).toBe(false)
  })

  it("opens a booking from its task's name", async () => {
    const w = await mountView()
    const link = cards(w)[1].findComponent(RouterLinkStub)
    expect(link.props('to')).toEqual({ name: 'booking-detail', params: { bookingId: 'b1' } })
    expect(link.text()).toBe('Grill stand')
  })

  it('groups by task on request and remembers the choice', async () => {
    const w = await mountView()
    const byDate = w.find('[data-testid="btn-event-date"]')
    const byTask = w.find('[data-testid="btn-event-task"]')
    expect(byDate.attributes('aria-pressed')).toBe('true')
    expect(w.findAll('h2').map((h) => h.text())).not.toContain('Grill stand')

    await byTask.trigger('click')
    expect(byTask.attributes('aria-pressed')).toBe('true')
    expect(byDate.attributes('aria-pressed')).toBe('false')
    const headings = w.findAll('h2').map((h) => h.text())
    expect(headings).toContain('Grill stand')
    expect(headings).toContain('Wristband check')
    expect(localStorage.getItem('wirksam:bookings:groupBy')).toBe('task')
  })

  it('reads an earlier "no grouping" as the list by date', async () => {
    localStorage.setItem('wirksam:bookings:groupBy', 'none')
    const w = await mountView()
    expect(w.find('[data-testid="btn-event-date"]').attributes('aria-pressed')).toBe('true')
  })

  it('shows the vouchers beside the hours once the account is in', async () => {
    const w = await mountView()
    expect(w.find('[data-testid="my-vouchers-card"]').exists()).toBe(true)
    expect(api.get).toHaveBeenCalledWith({ url: '/events/e1/vouchers/me' })
  })
})
