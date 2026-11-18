// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, onMounted } from 'vue'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { listDetail } from '@/components/shared-lists/__tests__/fixtures'

import type {
  EventRead,
  PublicSharedList,
  SharedListDetail,
  ShiftRead,
  TaskBookingEntry,
} from '@/client/types.gen'
import i18n from '@/locales/i18n'
import PrintListView from '@/views/print/PrintListView.vue'

/**
 * A shared list's notice: its title and intro, the QR code to its public
 * page, and only the shifts it offers, by task, with free places, vouchers
 * and lines for paper. A list that is not open says so in the toolbar and
 * offers its fix instead of a code that leads nowhere.
 */

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
const push = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn(), error: vi.fn() }))

vi.mock('@/composables/useAuthenticatedClient', () => ({ useAuthenticatedClient: () => api }))
vi.mock('vue-router', async (original) => ({
  ...(await original<typeof import('vue-router')>()),
  useRoute: () => ({ params: { listId: 'l1' } }),
  useRouter: () => ({ push }),
}))
vi.mock('vue-sonner', () => ({ toast }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))

/** The code draws at once and shows what it encodes. */
const QrCodeStub = defineComponent({
  props: { value: { type: String, required: true }, alt: String },
  emits: ['ready'],
  setup(props, { emit }) {
    onMounted(() => emit('ready'))
    return () => h('img', { alt: props.alt, 'data-value': props.value })
  },
})

const DAY = '2099-12-05'

function shiftRow(id: string, taskId: string, title: string): ShiftRead {
  return {
    id,
    task_id: taskId,
    title,
    date: DAY,
    start_time: '10:00:00',
    end_time: '12:00:00',
    location: 'Aula',
    location_id: null,
    max_bookings: 3,
    created_at: '',
    updated_at: '',
  }
}

const twoTasks = listDetail('l1', {
  title: 'Helfer für den Basar',
  intro: 'Wer backt?\nWer verkauft?',
  detail_tasks: [
    { ...listDetail('l1').detail_tasks[0]!, id: 't1', name: 'Kuchen' },
    { ...listDetail('l1').detail_tasks[0]!, id: 't2', name: 'Kasse' },
    {
      ...listDetail('l1').detail_tasks[0]!,
      id: 't3',
      name: 'Bar',
      offered: false,
      not_offered_reason: 'team_locked',
    },
  ],
})

function preview(shifts: { id: string; taskId: string; free: number; vouchers?: number }[]) {
  return {
    code: 'codel1',
    title: 'x',
    status: 'live',
    event: { name: 'Adventsbasar', start_date: DAY, end_date: DAY, timezone: 'Europe/Berlin' },
    ask_email: 'required',
    ask_phone: 'off',
    show_names: 'none',
    retention_days: 30,
    days: [
      {
        date: DAY,
        shifts: shifts.map((s) => ({
          id: s.id,
          task_id: s.taskId,
          task_name: s.taskId,
          location: 'Aula',
          start_time: '10:00:00',
          end_time: '12:00:00',
          capacity: 3,
          free: s.free,
          full: s.free === 0,
          vouchers: s.vouchers ?? 0,
        })),
      },
    ],
  } satisfies PublicSharedList
}

const event = { id: 'e1', managers_share_lists: true } as EventRead

interface Fixtures {
  detail: SharedListDetail
  preview: PublicSharedList
  event?: EventRead
  shifts?: Record<string, ShiftRead[]>
  bookings?: Record<string, TaskBookingEntry[]>
}

let fixtures: Fixtures

function serve() {
  api.get.mockImplementation(({ url, query }: { url: string; query?: { task_id?: string } }) => {
    if (url === '/shared-lists/l1') return Promise.resolve({ data: fixtures.detail })
    if (url === '/shared-lists/l1/preview') return Promise.resolve({ data: fixtures.preview })
    if (url === '/events/e1') return Promise.resolve({ data: fixtures.event ?? event })
    if (url === '/events/e1/shared-lists/overview') return Promise.resolve({ data: {} })
    if (url === '/shifts/') {
      const items = fixtures.shifts?.[query?.task_id ?? ''] ?? []
      return Promise.resolve({ data: { items, total: items.length } })
    }
    const bookings = /^\/tasks\/(\w+)\/bookings$/.exec(url)
    if (bookings) return Promise.resolve({ data: fixtures.bookings?.[bookings[1]!] ?? [] })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

async function mountView() {
  serve()
  const w = mount(PrintListView, {
    attachTo: document.body,
    global: {
      plugins: [i18n],
      stubs: { QrCode: QrCodeStub, VenueMiniMap: true },
    },
  })
  await flushPromises()
  return w
}

type Wrapper = Awaited<ReturnType<typeof mountView>>
const byTestId = (w: Wrapper, id: string) => w.find(`[data-testid="${id}"]`)
const printButton = (w: Wrapper) => w.findAll('button').find((b) => b.text() === 'Print')!
const checkbox = (w: Wrapper, id: string) => byTestId(w, id)

beforeEach(() => {
  vi.resetAllMocks()
  setActivePinia(createPinia())
  i18n.global.locale.value = 'en'
  fixtures = {
    detail: twoTasks,
    preview: preview([
      { id: 's1', taskId: 't1', free: 2, vouchers: 3 },
      { id: 's2', taskId: 't2', free: 0 },
    ]),
    shifts: { t1: [shiftRow('s1', 't1', 'Backen'), shiftRow('gone', 't1', 'Excluded')] },
  }
})

afterEach(() => {
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

describe('PrintListView', () => {
  it('prints the list’s title, intro and a QR code to its public page', async () => {
    const w = await mountView()

    const content = byTestId(w, 'print-content')
    expect(content.find('h1').text()).toBe('Helfer für den Basar')
    expect(content.text()).toContain('Adventsbasar')
    expect(content.find('.whitespace-pre-line').text()).toBe('Wer backt?\nWer verkauft?')
    const qr = byTestId(w, 'print-qr')
    expect(qr.find('img').attributes('data-value')).toBe(`${window.location.origin}/l/codel1`)
    expect(qr.text()).toContain('Scan to sign up, no account needed')
  })

  it('prints only the shifts the list offers, by task, with free places and vouchers', async () => {
    const w = await mountView()

    const sections = w.findAll('section')
    expect(sections.map((s) => s.find('h2').text())).toEqual(['Kuchen', 'Kasse'])
    const free = w.findAll('[data-testid="print-shift-free"]').map((td) => td.text())
    expect(free).toEqual(['2', '0'])
    expect(sections[0]!.text()).toContain('Vouchers')
    expect(sections[1]!.text()).not.toContain('Vouchers')
    // Two blank lines for the two free places; a full shift keeps its time.
    expect(sections[0]!.findAll('[data-testid="print-shift-line"]')).toHaveLength(2)
    expect(sections[1]!.findAll('[data-testid="print-shift-line"]')).toHaveLength(1)
    expect(w.text()).not.toContain('Excluded')
  })

  it('names no task over the shifts of a list of one', async () => {
    fixtures.preview = preview([{ id: 's1', taskId: 't1', free: 2 }])
    const w = await mountView()

    expect(w.findAll('section')).toHaveLength(1)
    expect(w.find('section h2').exists()).toBe(false)
  })

  it('leaves the lines for paper out on request, and fills in who signed up', async () => {
    fixtures.bookings = { t1: [{ id: 'b1', shift_id: 's1', user_name: 'Mia Berger' }] }
    const w = await mountView()
    const first = () => w.findAll('section')[0]!

    await checkbox(w, 'print-toggle-paper-lines').trigger('click')
    expect(first().findAll('[data-testid="print-shift-line"]')).toHaveLength(1)
    expect(first().text()).not.toContain('Mia Berger')

    await checkbox(w, 'print-toggle-names').trigger('click')
    await flushPromises()
    expect(first().text()).toContain('Mia Berger')
    expect(w.text()).toContain('Names of those signed up')
  })

  it('prints once the QR code has drawn', async () => {
    const print = vi.fn()
    vi.stubGlobal('print', print)
    const w = await mountView()

    expect(byTestId(w, 'print-list-status').exists()).toBe(false)
    await printButton(w).trigger('click')
    await vi.waitFor(() => expect(print).toHaveBeenCalledOnce())
  })

  it('says a paused list leads nowhere and resumes it instead of printing', async () => {
    fixtures.detail = { ...twoTasks, status: 'paused', effective_status: 'paused' }
    fixtures.preview = { ...preview([]), status: 'paused' }
    const w = await mountView()

    expect(byTestId(w, 'print-list-status').text()).toContain('The list is paused.')
    expect(byTestId(w, 'print-qr').exists()).toBe(false)
    expect(printButton(w).attributes('disabled')).toBeDefined()
    expect(w.text()).toContain("While the list isn't open, there's nothing to print here.")

    api.post.mockImplementation(() => {
      fixtures.detail = twoTasks
      fixtures.preview = preview([{ id: 's1', taskId: 't1', free: 2 }])
      return Promise.resolve({ data: twoTasks })
    })
    await byTestId(w, 'print-list-fix').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith({ url: '/shared-lists/l1/resume' })
    expect(byTestId(w, 'print-qr').exists()).toBe(true)
    expect(printButton(w).attributes('disabled')).toBeUndefined()
    // The fix went with the status; focus moves on to printing.
    expect(document.activeElement).toBe(printButton(w).element)
  })

  it('offers to extend a list that closes within days', async () => {
    fixtures.detail = { ...twoTasks, ends_mode: 'date', ends_on: DAY, expires_soon: true }
    const w = await mountView()

    expect(byTestId(w, 'print-list-status').text()).toContain('The QR code only takes sign-ups')
    expect(byTestId(w, 'print-list-fix').text()).toBe('Extend')
    expect(printButton(w).attributes('disabled')).toBeUndefined()
  })

  it('keeps the names and the viewer’s choices through a fix', async () => {
    fixtures.detail = { ...twoTasks, ends_mode: 'date', ends_on: DAY, expires_soon: true }
    fixtures.bookings = { t1: [{ id: 'b1', shift_id: 's1', user_name: 'Mia Berger' }] }
    api.patch.mockResolvedValue({ data: twoTasks })
    const w = await mountView()
    const titleBox = () =>
      w
        .findAll('label')
        .find((l) => l.text() === 'Show title column')!
        .find('[role="checkbox"]')

    await checkbox(w, 'print-toggle-names').trigger('click')
    await titleBox().trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Mia Berger')
    expect(titleBox().attributes('data-state')).toBe('checked')

    await byTestId(w, 'print-list-fix').trigger('click')
    await flushPromises()

    expect(api.patch).toHaveBeenCalledOnce()
    expect(checkbox(w, 'print-toggle-names').attributes('data-state')).toBe('checked')
    expect(w.text()).toContain('Mia Berger')
    expect(titleBox().attributes('data-state')).toBe('checked')
  })

  it('offers an ended list to be shared again', async () => {
    fixtures.detail = { ...twoTasks, status: 'ended', effective_status: 'ended' }
    fixtures.preview = { ...preview([]), status: 'closed' }
    const w = await mountView()

    await byTestId(w, 'print-list-fix').trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: 'shared-list-create',
      params: { eventId: 'e1' },
      query: { from: 'l1' },
    })
  })

  it('gives a viewer and a locked person in charge the reason without a fix', async () => {
    fixtures.detail = { ...twoTasks, effective_status: 'expired', access: 'viewer' }
    fixtures.preview = { ...preview([]), status: 'closed' }
    const viewer = await mountView()
    expect(byTestId(viewer, 'print-list-status').text()).toContain(
      'Only the organisers can change that.',
    )
    expect(byTestId(viewer, 'print-list-fix').exists()).toBe(false)
    viewer.unmount()

    fixtures.detail = { ...twoTasks, effective_status: 'expired', access: 'manager' }
    fixtures.event = { ...event, managers_share_lists: false }
    const locked = await mountView()
    expect(byTestId(locked, 'print-list-status').text()).toContain('turned sharing off')
    expect(byTestId(locked, 'print-list-fix').exists()).toBe(false)
  })

  it('says so when the list cannot be read', async () => {
    api.get.mockRejectedValue(new Error('404'))
    const w = mount(PrintListView, { global: { plugins: [i18n], stubs: { QrCode: QrCodeStub } } })
    await flushPromises()
    expect(byTestId(w, 'print-list-missing').text()).toBe(
      "This list doesn't exist, or you can't see it.",
    )
  })
})
