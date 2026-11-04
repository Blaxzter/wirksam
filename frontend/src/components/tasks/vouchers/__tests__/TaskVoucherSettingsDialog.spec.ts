// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import TaskVoucherSettingsDialog from '@/components/tasks/vouchers/TaskVoucherSettingsDialog.vue'

import type { TaskRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The task's voucher dialog warns that a rate above 0 takes the shifts away
 * from the task's people in charge, but only when that is what happens: the
 * task has people in charge and its event (the selected one) keeps the shifts
 * of voucher tasks with the organisers.
 */

const api = vi.hoisted(() => ({ patch: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ patch: api.patch }),
}))

const auth = vi.hoisted(() => ({
  selectedEvent: null as { id: string; managers_edit_voucher_shifts?: boolean } | null,
  refreshSelectedEvent: vi.fn(),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock('vue-sonner', () => ({ toast }))

vi.mock('@/lib/api-errors', () => ({ toastApiError: vi.fn() }))

const passthrough = { template: '<div><slot /></div>' }
const dialogStub = {
  props: ['open'],
  template: '<div v-if="open" data-stub="dialog"><slot /></div>',
}

function task(overrides: Partial<TaskRead> = {}): TaskRead {
  return {
    id: 't1',
    name: 'Cafétheke',
    status: 'published',
    event_id: 'e1',
    start_date: '2026-07-17',
    end_date: '2026-07-19',
    vouchers_per_shift: 2,
    is_voucher_point: false,
    managers: [{ user_id: 'u2', name: 'Mira' }],
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
    ...overrides,
  } as TaskRead
}

async function openDialog(t: TaskRead = task()) {
  const w = mount(TaskVoucherSettingsDialog, {
    props: { open: false, task: t },
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
      },
    },
  })
  await w.setProps({ open: true })
  return w
}

const hint = (w: Awaited<ReturnType<typeof openDialog>>) =>
  w.find('[data-testid="task-vouchers-managers-locked"]')

beforeEach(() => {
  i18n.global.locale.value = 'en'
  vi.clearAllMocks()
  auth.selectedEvent = { id: 'e1', managers_edit_voucher_shifts: false }
})

describe('TaskVoucherSettingsDialog', () => {
  it('warns that the people in charge lose the shifts while the event keeps them', async () => {
    const w = await openDialog()
    expect(hint(w).text()).toBe(
      'The people in charge of this task can then no longer add, move or delete its shifts.',
    )
  })

  it('warns only once the rate goes above 0', async () => {
    const w = await openDialog(task({ vouchers_per_shift: 0 }))
    expect(hint(w).exists()).toBe(false)

    const input = w.find<HTMLInputElement>('[data-testid="voucher-per-shift"] input')
    await input.setValue('2')
    await input.trigger('blur')

    expect(hint(w).exists()).toBe(true)
  })

  it('says nothing when the event lets people in charge change those shifts', async () => {
    auth.selectedEvent = { id: 'e1', managers_edit_voucher_shifts: true }
    const w = await openDialog()
    expect(hint(w).exists()).toBe(false)
  })

  it('says nothing when the task has no people in charge', async () => {
    const w = await openDialog(task({ managers: [] }))
    expect(hint(w).exists()).toBe(false)
  })

  it("says nothing when the task's event is not the one loaded", async () => {
    auth.selectedEvent = { id: 'other', managers_edit_voucher_shifts: false }
    const w = await openDialog()
    expect(hint(w).exists()).toBe(false)

    auth.selectedEvent = null
    const w2 = await openDialog()
    expect(hint(w2).exists()).toBe(false)
  })
})
