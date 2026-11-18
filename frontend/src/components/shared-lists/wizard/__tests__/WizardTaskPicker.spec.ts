// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import WizardTaskPicker from '@/components/shared-lists/wizard/WizardTaskPicker.vue'

import type { SharedListCandidate } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * "Which tasks?" in the wizard: a task that gives vouchers says that people
 * signing up through the list earn them too, and screen readers hear it with
 * the task. A task only a team may book says nothing of the sort.
 */

const api = vi.hoisted(() => ({ fetchCandidates: vi.fn() }))
vi.mock('@/composables/useSharedListWizardApi', () => ({
  useSharedListWizardApi: () => ({ fetchCandidates: api.fetchCandidates }),
}))

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: null }) }))

function candidate(overrides: Partial<SharedListCandidate> = {}): SharedListCandidate {
  return {
    id: 'task-1',
    name: 'Bar',
    location: null,
    manager_names: [],
    shift_count: 2,
    dates: ['2026-11-20'],
    capacity: 4,
    free: 4,
    team: null,
    earns_vouchers: false,
    ...overrides,
  }
}

async function mountPicker(items: SharedListCandidate[]) {
  api.fetchCandidates.mockResolvedValue({
    items,
    total: items.length,
    skip: 0,
    limit: 25,
    locked_count: 0,
    locked_names: [],
  })
  const w = mount(WizardTaskPicker, {
    props: { eventId: 'e1', picked: [], shiftsByTask: new Map(), excluded: new Set<string>() },
    global: { plugins: [i18n], stubs: { WizardTaskShifts: true } },
  })
  await flushPromises()
  return w
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
  api.fetchCandidates.mockReset()
})

describe('WizardTaskPicker: vouchers', () => {
  it('says a task with vouchers gives them to people without an account too', async () => {
    const w = await mountPicker([
      candidate({ earns_vouchers: true }),
      candidate({ id: 'task-2', name: 'Kitchen' }),
      candidate({
        id: 'task-3',
        name: 'Stage',
        earns_vouchers: true,
        team: { id: 'team-1', name: 'Crew' },
      }),
    ])
    const hint = w.find('[data-testid="wizard-task-vouchers-task-1"]')
    expect(hint.text()).toBe('Earns vouchers, also for people without an account.')
    expect(w.find('[data-testid="wizard-task-check-task-1"]').attributes('aria-describedby')).toBe(
      'wizard-task-meta-task-1 wizard-task-vouchers-task-1',
    )
    expect(w.find('[data-testid="wizard-task-vouchers-task-2"]').exists()).toBe(false)
    expect(w.find('[data-testid="wizard-task-check-task-2"]').attributes('aria-describedby')).toBe(
      'wizard-task-meta-task-2',
    )
    // A team's task never goes on a list, so it promises nothing.
    expect(w.find('[data-testid="wizard-task-vouchers-task-3"]').exists()).toBe(false)
  })

  it('reads in German', async () => {
    i18n.global.locale.value = 'de'
    const w = await mountPicker([candidate({ earns_vouchers: true })])
    expect(w.find('[data-testid="wizard-task-vouchers-task-1"]').text()).toBe(
      'Gibt Marken, auch für alle ohne Konto.',
    )
  })
})
