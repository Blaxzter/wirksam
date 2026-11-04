// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { EventMemberRead, VoucherPointRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'
import RedeemVouchersView from '@/views/vouchers/RedeemVouchersView.vue'

/**
 * Picking the person at a stand: whoever may redeem without a code sees how
 * many vouchers each member has, from the point's own read, and cannot pick
 * someone who has none. Organisers, people in charge and staff on shift alike.
 */

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({ useAuthenticatedClient: () => api }))

const auth = vi.hoisted(() => ({ admin: false }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    selectedEventId: 'e1',
    profile: { id: 'me', time_format: 'h24' },
    canManageEvent: () => auth.admin,
  }),
}))
vi.mock('@/lib/api-errors', () => ({
  toastApiError: vi.fn(),
  getApiErrorMessage: () => 'error',
}))
// A phone, so the picker is the full-screen list straight away.
vi.mock('@vueuse/core', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@vueuse/core')>()),
  useMediaQuery: () => ref(true),
}))

/** The member picker, reduced to its rows: who, whether they can be picked, the slot. */
const PickerStub = defineComponent({
  name: 'EventMemberPicker',
  props: {
    members: { type: Array as () => EventMemberRead[], default: () => [] },
    unavailable: { type: Object as () => Record<string, string> | undefined, default: undefined },
    sheetContext: { type: String, default: '' },
  },
  emits: ['pick', 'update:sheetOpen'],
  setup(props, { slots }) {
    return () =>
      h('ul', { 'data-testid': 'picker', 'data-context': props.sheetContext }, [
        ...props.members.map((m) =>
          h(
            'li',
            {
              'data-testid': `row-${m.user_id}`,
              'data-unavailable': props.unavailable?.[m.user_id] ?? '',
            },
            slots.trailing?.({ member: m }),
          ),
        ),
      ])
  },
})

function point(overrides: Partial<VoucherPointRead> = {}): VoucherPointRead {
  return {
    task_id: 't1',
    name: 'Cafétheke',
    location: null,
    can_redeem: true,
    can_redeem_manually: true,
    managers: [],
    ...overrides,
  }
}

const members = [
  { user_id: 'u1', name: 'Tomas Neruda', role: 'member' },
  { user_id: 'u2', name: 'Adaeze Okafor', role: 'member' },
  { user_id: 'u3', name: 'Joined Just Now', role: 'member' },
] as unknown as EventMemberRead[]

let points: VoucherPointRead[]
let people: () => Promise<unknown>

beforeEach(() => {
  i18n.global.locale.value = 'en'
  auth.admin = false
  localStorage.clear()
  points = [point()]
  people = () =>
    Promise.resolve({
      data: [
        { user_id: 'u1', available: 3 },
        { user_id: 'u2', available: 0 },
      ],
    })
  api.get.mockReset()
  api.get.mockImplementation(({ url }: { url: string }) => {
    if (url === '/events/e1/vouchers/points') return Promise.resolve({ data: points })
    if (url === '/events/e1/members') return Promise.resolve({ data: members })
    if (url === '/events/e1/vouchers/points/t1/people') return people()
    if (url.endsWith('/entries')) {
      return Promise.resolve({
        data: { items: [], today_count: 0, today_amount: 0, total_count: 0, total_amount: 0 },
      })
    }
    return Promise.reject(new Error(`unexpected ${url}`))
  })
})

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ name: 'voucher-redeem', path: '/redeem/:eventId', component: RedeemVouchersView }],
  })
  await router.push('/redeem/e1?task=t1')
  await router.isReady()
  const w = mount(RedeemVouchersView, {
    global: {
      plugins: [i18n, router],
      stubs: {
        EventMemberPicker: PickerStub,
        VoucherScanner: true,
        VoucherRedeemConfirm: true,
        ResponsiveDialog: true,
      },
    },
  })
  await flushPromises()
  return w
}

async function openPicker(w: Awaited<ReturnType<typeof mountView>>) {
  await w.find('[data-testid="btn-voucher-pick-person"]').trigger('click')
  await flushPromises()
}

const row = (w: Awaited<ReturnType<typeof mountView>>, id: string) =>
  w.find(`[data-testid="row-${id}"]`)

describe('RedeemVouchersView: picking the person', () => {
  it.each([
    ['an organiser', true],
    ['someone in charge or on shift', false],
  ])('shows %s what each person has, from the point', async (_who, admin) => {
    auth.admin = admin
    const w = await mountView()
    await openPicker(w)

    const urls = api.get.mock.calls.map(([arg]) => (arg as { url: string }).url)
    expect(urls).toContain('/events/e1/vouchers/points/t1/people')
    // Never the organisers' overview, which carries far more than a count.
    expect(urls).not.toContain('/events/e1/vouchers/people')

    expect(row(w, 'u1').find('[data-testid="voucher-pick-count-u1"]').text()).toContain('3')
    expect(row(w, 'u1').attributes('data-unavailable')).toBe('')
    expect(row(w, 'u2').attributes('data-unavailable')).toBe('No vouchers left')
    // Not in the numbers: joined after they were read, so nothing to redeem yet.
    expect(row(w, 'u3').attributes('data-unavailable')).toBe('No vouchers left')
    expect(w.find('[data-testid="picker"]').attributes('data-context')).toContain(
      'The number shows how many vouchers each person has.',
    )
  })

  it('reads the numbers again on every opening', async () => {
    const w = await mountView()
    await openPicker(w)
    await openPicker(w)
    const reads = api.get.mock.calls.filter(
      ([arg]) => (arg as { url: string }).url === '/events/e1/vouchers/points/t1/people',
    )
    expect(reads).toHaveLength(2)
  })

  it('still lists the names when the numbers are refused', async () => {
    people = () => Promise.reject(Object.assign(new Error('403'), { status: 403 }))
    const w = await mountView()
    await openPicker(w)

    expect(row(w, 'u1').exists()).toBe(true)
    expect(w.find('[data-testid="voucher-pick-count-u1"]').exists()).toBe(false)
    expect(row(w, 'u2').attributes('data-unavailable')).toBe('')
    expect(w.find('[data-testid="picker"]').attributes('data-context')).not.toContain('number')
  })

  it('offers no picking where only a code will do', async () => {
    points = [point({ can_redeem_manually: false })]
    const w = await mountView()
    expect(w.find('[data-testid="btn-voucher-pick-person"]').exists()).toBe(false)
  })
})
