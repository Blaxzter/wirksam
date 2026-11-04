// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import TaskInChargeCard from '@/components/tasks/detail/TaskInChargeCard.vue'

import type { TaskManagerInvitationRead, TaskRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * "In charge" on the task page. Everyone sees who runs the task; organisers
 * also see the invitations still open and a way to manage them, and a person
 * in charge finds stepping down here, with why the shifts aren't theirs when
 * the event keeps voucher shifts with the organisers.
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
    managers: [
      { user_id: 'u-mira', name: 'Mira Lindqvist' },
      { user_id: 'u-pia', name: 'Pia Incharge' },
    ],
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
    ...overrides,
  } as TaskRead
}

function invitation(overrides: Partial<TaskManagerInvitationRead> = {}): TaskManagerInvitationRead {
  return {
    id: 'i1',
    email: 'jonas.weber@example.org',
    created_at: '2026-07-02T10:00:00',
    expires_at: '2026-07-16T10:00:00',
    expired: false,
    is_member_now: false,
    ...overrides,
  }
}

async function mountCard(props: Record<string, unknown> = {}) {
  const w = mount(TaskInChargeCard, {
    props: { task: task(), ...props },
    global: { plugins: [i18n] },
  })
  await flushPromises()
  return w
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
  vi.clearAllMocks()
  api.get.mockResolvedValue({ data: [invitation()] })
})

describe('TaskInChargeCard', () => {
  it('lists who is in charge and marks your own row', async () => {
    const w = await mountCard({ myId: 'u-pia', inCharge: true })
    const list = w.find('[data-testid="task-managers"]')
    expect(list.text()).toContain('Mira Lindqvist')
    expect(list.text()).toContain('Pia Incharge')
    const you = w.find('[data-testid="task-you-are-in-charge"]')
    expect(you.text()).toBe('You')
    expect(you.element.closest('li')?.textContent).toContain('Pia Incharge')
  })

  it("doesn't fetch invitations for anyone but an organiser", async () => {
    const w = await mountCard({ myId: 'u-pia', inCharge: true })
    expect(api.get).not.toHaveBeenCalled()
    expect(w.text()).not.toContain('jonas.weber@example.org')
    expect(w.find('[data-testid="btn-task-managers-card"]').exists()).toBe(false)
  })

  it('shows an organiser the invitations still waiting for an answer', async () => {
    const w = await mountCard({ canAdmin: true })
    expect(api.get).toHaveBeenCalledWith({ url: '/tasks/t1/managers/invitations' })
    const row = w.find('[data-testid="task-in-charge-invitation-jonas.weber@example.org"]')
    expect(row.text()).toContain('Waiting for them to accept')
    expect(row.text()).toContain('Invited')
    expect(w.text()).toContain('They can edit the task and see who booked.')
  })

  it('says how an invitation stands once it has expired or its address has joined', async () => {
    api.get.mockResolvedValue({
      data: [
        invitation({ id: 'a', email: 'old@example.org', expired: true }),
        invitation({ id: 'b', email: 'joined@example.org', is_member_now: true }),
      ],
    })
    const w = await mountCard({ canAdmin: true })
    const old = w.find('[data-testid="task-in-charge-invitation-old@example.org"]')
    expect(old.text()).toContain('The invitation has expired')
    expect(old.text()).toContain('Expired')
    const joined = w.find('[data-testid="task-in-charge-invitation-joined@example.org"]')
    expect(joined.text()).toContain('Already in the event now')
    expect(joined.text()).toContain('Invited')
  })

  it('leaves the line under the address out on a phone', async () => {
    const w = await mountCard({ canAdmin: true, compact: true })
    expect(w.text()).toContain('jonas.weber@example.org')
    expect(w.text()).not.toContain('Waiting for them to accept')
  })

  it('fetches the invitations again when asked to', async () => {
    const w = await mountCard({ canAdmin: true })
    api.get.mockResolvedValue({ data: [] })
    await (w.vm as unknown as { reloadInvitations: () => Promise<void> }).reloadInvitations()
    await flushPromises()
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(w.text()).not.toContain('jonas.weber@example.org')
  })

  it('keeps quiet when the invitations cannot be fetched', async () => {
    api.get.mockRejectedValue(new Error('offline'))
    const w = await mountCard({ canAdmin: true })
    expect(w.find('[data-testid="task-managers"]').text()).toContain('Mira Lindqvist')
  })

  it('says so when nobody runs the task yet', async () => {
    api.get.mockResolvedValue({ data: [] })
    const w = await mountCard({ canAdmin: true, task: task({ managers: [] }) })
    expect(w.find('[data-testid="task-in-charge-empty"]').exists()).toBe(true)
  })

  it('opens the dialog from "Manage", on a desktop and on a phone', async () => {
    for (const compact of [false, true]) {
      const w = await mountCard({ canAdmin: true, compact })
      await w.find('[data-testid="btn-task-managers-card"]').trigger('click')
      expect(w.emitted('manage')).toHaveLength(1)
    }
  })

  it('lets a person in charge step down, and says why the shifts are not theirs', async () => {
    const w = await mountCard({ myId: 'u-pia', inCharge: true, shiftsLocked: true })
    expect(w.find('[data-testid="task-voucher-shifts-locked"]').text()).toContain(
      'You can change the description and details.',
    )
    await w.find('[data-testid="btn-task-step-down"]').trigger('click')
    expect(w.emitted('stepDown')).toHaveLength(1)
  })

  it('uses the short note on a phone and none while the shifts are theirs', async () => {
    const phone = await mountCard({
      myId: 'u-pia',
      inCharge: true,
      shiftsLocked: true,
      compact: true,
    })
    expect(phone.find('[data-testid="task-voucher-shifts-locked"]').text()).toBe(
      'Shifts here earn vouchers, so the organisers set them up.',
    )
    const open = await mountCard({ myId: 'u-pia', inCharge: true })
    expect(open.find('[data-testid="task-voucher-shifts-locked"]').exists()).toBe(false)
    expect(open.find('[data-testid="btn-task-step-down"]').exists()).toBe(true)
  })

  it('offers no stepping down to someone who is not in charge', async () => {
    const w = await mountCard({ canAdmin: true })
    expect(w.find('[data-testid="btn-task-step-down"]').exists()).toBe(false)
  })
})
