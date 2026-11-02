import { effectScope, nextTick, reactive } from 'vue'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useMyVoucherAccount } from '@/composables/useMyVoucherAccount'

import type { VoucherAccount } from '@/client/types.gen'

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: api.get }),
}))

interface FakeEvent {
  id: string
  is_expired?: boolean
  voucher_task_count?: number
  voucher_point_count?: number
}

const auth = vi.hoisted(() => ({
  store: null as unknown as { selectedEventId: string | null; selectedEvent: FakeEvent | null },
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth.store }))

function account(summary: Partial<VoucherAccount['summary']> = {}, entries = 0): VoucherAccount {
  return {
    summary: {
      user_id: 'u1',
      earned: 0,
      upcoming: 0,
      redeemed: 0,
      adjusted: 0,
      balance: 0,
      available: 0,
      ...summary,
    },
    shifts: [],
    entries: Array.from({ length: entries }, (_, i) => ({ id: `v${i}` })) as never,
  }
}

/** Let the queued promise callbacks run. */
const flush = () => new Promise((r) => setTimeout(r, 0))

const scopes: ReturnType<typeof effectScope>[] = []
function setup() {
  const scope = effectScope()
  scopes.push(scope)
  return scope.run(() => useMyVoucherAccount())!
}

beforeEach(() => {
  vi.resetAllMocks()
  auth.store = reactive({ selectedEventId: 'e1', selectedEvent: { id: 'e1' } as FakeEvent | null })
})

afterEach(() => {
  scopes.splice(0).forEach((s) => s.stop())
})

describe('useMyVoucherAccount', () => {
  it('loads the selected event’s account', async () => {
    api.get.mockResolvedValue({ data: account({ earned: 2, available: 2 }) })
    const { account: acc, settled } = setup()

    expect(settled.value).toBe(false)
    await flush()

    expect(api.get).toHaveBeenCalledWith({ url: '/events/e1/vouchers/me' })
    expect(acc.value?.summary.earned).toBe(2)
    expect(settled.value).toBe(true)
  })

  it('has nothing to load without a selected event', async () => {
    auth.store.selectedEventId = null
    auth.store.selectedEvent = null
    const { account: acc, settled, visible } = setup()
    await flush()

    expect(api.get).not.toHaveBeenCalled()
    expect(acc.value).toBeNull()
    expect(settled.value).toBe(true)
    expect(visible.value).toBe(false)
  })

  it('treats a failed read as no account', async () => {
    api.get.mockRejectedValue(new Error('403'))
    const { account: acc, settled } = setup()
    await flush()

    expect(acc.value).toBeNull()
    expect(settled.value).toBe(true)
  })

  it.each([
    ['earned', account({ earned: 1 })],
    ['upcoming', account({ upcoming: 2 })],
    ['entries', account({}, 1)],
  ])('is visible once there is something to show (%s)', async (_, data) => {
    api.get.mockResolvedValue({ data })
    const { visible } = setup()
    await flush()
    expect(visible.value).toBe(true)
  })

  it('is visible for an event that uses vouchers, even with an empty account', async () => {
    api.get.mockResolvedValue({ data: account() })
    const { visible } = setup()
    await flush()
    expect(visible.value).toBe(false)

    auth.store.selectedEvent = { id: 'e1', voucher_task_count: 1 }
    expect(visible.value).toBe(true)
    auth.store.selectedEvent = { id: 'e1', voucher_point_count: 1 }
    expect(visible.value).toBe(true)
  })

  it('does not trust the counts of an event that is not the selected one', async () => {
    api.get.mockResolvedValue({ data: account() })
    const { visible } = setup()
    await flush()

    auth.store.selectedEvent = { id: 'e2', voucher_task_count: 3, voucher_point_count: 1 }
    expect(visible.value).toBe(false)
  })

  it('offers the code only with something available, and not after the event', async () => {
    api.get.mockResolvedValue({ data: account({ available: 0, earned: 1 }) })
    const { canShowCode, isExpired, reload } = setup()
    await flush()
    expect(canShowCode.value).toBe(false)

    api.get.mockResolvedValue({ data: account({ available: 2, earned: 2 }) })
    await reload()
    expect(canShowCode.value).toBe(true)
    expect(isExpired.value).toBe(false)

    auth.store.selectedEvent = { id: 'e1', is_expired: true }
    expect(isExpired.value).toBe(true)
    expect(canShowCode.value).toBe(false)
  })

  it('clears the old account at once when the event changes', async () => {
    api.get.mockResolvedValueOnce({ data: account({ earned: 1 }) })
    const { account: acc, settled } = setup()
    await flush()
    expect(acc.value).not.toBeNull()

    api.get.mockImplementation(() => new Promise(() => {}))
    auth.store.selectedEventId = 'e2'
    await nextTick()
    expect(acc.value).toBeNull()
    expect(settled.value).toBe(false)
  })

  it('ignores a late answer for the event that was selected before', async () => {
    const pending: ((value: unknown) => void)[] = []
    api.get.mockImplementation(() => new Promise((resolve) => pending.push(resolve)))
    const { account: acc, settled } = setup()

    auth.store.selectedEventId = 'e2'
    auth.store.selectedEvent = { id: 'e2' }
    await nextTick()
    expect(api.get).toHaveBeenLastCalledWith({ url: '/events/e2/vouchers/me' })

    pending[1]!({ data: account({ earned: 5 }) })
    await flush()
    expect(acc.value?.summary.earned).toBe(5)
    expect(settled.value).toBe(true)

    pending[0]!({ data: account({ earned: 1 }) })
    await flush()
    expect(acc.value?.summary.earned).toBe(5)
  })

  it('re-reads on reload', async () => {
    api.get.mockResolvedValue({ data: account({ earned: 1 }) })
    const { account: acc, reload } = setup()
    await flush()

    api.get.mockResolvedValue({ data: account({ earned: 3 }) })
    await reload()
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(acc.value?.summary.earned).toBe(3)
  })
})
