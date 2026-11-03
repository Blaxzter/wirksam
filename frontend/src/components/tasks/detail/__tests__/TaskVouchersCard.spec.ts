// @vitest-environment jsdom
import { RouterLinkStub, flushPromises, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import TaskVouchersCard from '@/components/tasks/detail/TaskVouchersCard.vue'

import type { TaskRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * "Vouchers" on the task page: what a shift here earns, whether vouchers are
 * taken here (with today's count for those who run the task), and the way to
 * the redeem page for whoever may take them now.
 */

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: api.get }),
}))

function task(overrides: Partial<TaskRead> = {}): TaskRead {
  return {
    id: 't1',
    name: 'Cafétheke',
    status: 'published',
    event_id: 'e1',
    start_date: '2026-07-17',
    end_date: '2026-07-19',
    vouchers_per_shift: 2,
    is_voucher_point: true,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
    ...overrides,
  } as TaskRead
}

const redeemTo = { name: 'voucher-redeem', params: { eventId: 'e1' }, query: { task: 't1' } }

async function mountCard(props: Record<string, unknown> = {}) {
  const w = mount(TaskVouchersCard, {
    props: { task: task(), redeemTo, ...props },
    global: { plugins: [i18n], stubs: { RouterLink: RouterLinkStub } },
  })
  await flushPromises()
  return w
}

const find = (w: Awaited<ReturnType<typeof mountCard>>, id: string) =>
  w.find(`[data-testid="${id}"]`)

beforeEach(() => {
  i18n.global.locale.value = 'en'
  vi.clearAllMocks()
  api.get.mockResolvedValue({ data: { items: [], today_count: 5, today_amount: 9 } })
})

describe('TaskVouchersCard', () => {
  it('says how many vouchers a shift earns, and when', async () => {
    const w = await mountCard()
    expect(find(w, 'task-vouchers-per-shift').text()).toBe("2 per shift, once it's over")
  })

  it('keeps it short on a phone and adds when they arrive underneath', async () => {
    const w = await mountCard({ compact: true })
    expect(find(w, 'task-vouchers-per-shift').text()).toBe('2 per shift')
    expect(w.text()).toContain('Volunteers get them once their shift is over.')
  })

  it('says when shifts here earn none', async () => {
    const w = await mountCard({ task: task({ vouchers_per_shift: 0 }) })
    expect(find(w, 'task-vouchers-per-shift').exists()).toBe(false)
    expect(w.text()).toContain('Shifts here earn no vouchers.')
  })

  it('counts what was redeemed here today for whoever runs the task', async () => {
    const w = await mountCard({ canManage: true, canRedeem: true })
    expect(api.get).toHaveBeenCalledWith({
      url: '/events/e1/vouchers/points/t1/entries',
      query: { limit: 1 },
    })
    expect(find(w, 'task-vouchers-redeemed-today').text()).toBe('9')
    expect(find(w, 'task-voucher-point').text()).toContain('redeemed here today')
  })

  it('only says that vouchers are taken here to everyone else', async () => {
    const w = await mountCard({ canRedeem: true })
    expect(api.get).not.toHaveBeenCalled()
    expect(find(w, 'task-voucher-point').text()).toBe('Takes vouchers')
  })

  it('falls back to "Takes vouchers" when the count cannot be fetched', async () => {
    api.get.mockRejectedValue(new Error('offline'))
    const w = await mountCard({ canManage: true, canRedeem: true })
    expect(find(w, 'task-voucher-point').text()).toBe('Takes vouchers')
  })

  it("says when vouchers aren't taken here", async () => {
    const desktop = await mountCard({ task: task({ is_voucher_point: false }), canManage: true })
    expect(find(desktop, 'task-voucher-point').exists()).toBe(false)
    expect(desktop.text()).toContain("Vouchers aren't taken here.")
    const phone = await mountCard({ task: task({ is_voucher_point: false }), compact: true })
    expect(phone.text()).toContain('Not a place to redeem')
  })

  it('links to the redeem page only for whoever may redeem here now', async () => {
    const w = await mountCard({ canRedeem: true })
    const link = w.findComponent(RouterLinkStub)
    expect(link.props('to')).toEqual(redeemTo)
    expect(link.text()).toBe('Redeem vouchers')

    const other = await mountCard()
    expect(find(other, 'btn-redeem-vouchers').exists()).toBe(false)
  })

  it('offers the settings to organisers only', async () => {
    const member = await mountCard()
    expect(find(member, 'btn-task-vouchers-card').exists()).toBe(false)

    for (const compact of [false, true]) {
      const w = await mountCard({ canAdmin: true, compact })
      await find(w, 'btn-task-vouchers-card').trigger('click')
      expect(w.emitted('settings')).toHaveLength(1)
    }
  })
})
