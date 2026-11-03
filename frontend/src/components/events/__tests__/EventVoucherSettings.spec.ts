// @vitest-environment jsdom
import { RouterLinkStub, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import EventVoucherSettings from '@/components/events/EventVoucherSettings.vue'

import type { EventRead, TaskRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The event's voucher rules: who may redeem without a code (the on-shift
 * option first and chosen by default, with its warning while chosen) and
 * whether people in charge may change the shifts of voucher tasks (off by
 * default, the hint saying what each state means). "Save" sends only those
 * two fields and is idle until something changed.
 */

const api = vi.hoisted(() => ({ patch: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ patch: api.patch }),
}))

const auth = vi.hoisted(() => ({ refreshSelectedEvent: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock('vue-sonner', () => ({ toast }))

const toastApiError = vi.fn()
vi.mock('@/lib/api-errors', () => ({ toastApiError: (e: unknown) => toastApiError(e) }))

function event(overrides: Partial<EventRead> = {}): EventRead {
  return {
    id: 'e1',
    name: 'Sommerfest',
    start_date: '2026-07-17',
    end_date: '2026-07-19',
    status: 'published',
    visibility: 'private',
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
    ...overrides,
  } as EventRead
}

function task(overrides: Partial<TaskRead>): TaskRead {
  return {
    id: 't1',
    name: 'Cafétheke',
    status: 'published',
    start_date: '2026-07-17',
    end_date: '2026-07-19',
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
    ...overrides,
  } as TaskRead
}

function mountCard(ev: EventRead = event(), tasks: TaskRead[] = []) {
  return mount(EventVoucherSettings, {
    props: { event: ev, tasks },
    global: { plugins: [i18n], stubs: { RouterLink: RouterLinkStub } },
    attachTo: document.body,
  })
}

const radio = (w: ReturnType<typeof mountCard>, value: string) =>
  w.find(`[data-testid="voucher-manual-${value}"]`)
const switchEl = (w: ReturnType<typeof mountCard>) =>
  w.find('[data-testid="switch-managers-edit-voucher-shifts"]')
const saveButton = (w: ReturnType<typeof mountCard>) =>
  w.find<HTMLButtonElement>('[data-testid="btn-save-voucher-rules"]')

const flush = () => new Promise((r) => setTimeout(r, 0))

beforeEach(() => {
  i18n.global.locale.value = 'en'
  vi.clearAllMocks()
  document.body.innerHTML = ''
})

describe('EventVoucherSettings', () => {
  it('lists the on-shift option first and chooses it for an event left at the defaults', () => {
    const w = mountCard()
    const options = w.findAll('[data-testid^="voucher-manual-"][role="radio"]')
    expect(options.map((o) => o.attributes('data-testid'))).toEqual([
      'voucher-manual-on_shift',
      'voucher-manual-in_charge',
    ])
    expect(radio(w, 'on_shift').attributes('data-state')).toBe('checked')
    expect(w.find('[data-testid="voucher-manual-on-shift-warning"]').text()).toContain(
      'let only a team book those shifts',
    )

    expect(switchEl(w).attributes('aria-checked')).toBe('false')
    expect(w.find('[data-testid="voucher-managers-edit-shifts-hint"]').text()).toMatch(/^Off:/)
    expect(saveButton(w).element.disabled).toBe(true)
  })

  it('shows what the event has saved', () => {
    const w = mountCard(
      event({ voucher_manual_redeem: 'in_charge', managers_edit_voucher_shifts: true }),
    )
    expect(radio(w, 'in_charge').attributes('data-state')).toBe('checked')
    expect(w.find('[data-testid="voucher-manual-on-shift-warning"]').exists()).toBe(false)
    expect(switchEl(w).attributes('aria-checked')).toBe('true')
    expect(w.find('[data-testid="voucher-managers-edit-shifts-hint"]').text()).toMatch(/^On:/)
  })

  it('saves just the two rules, says so and refreshes the selected event', async () => {
    const updated = event({ voucher_manual_redeem: 'in_charge', managers_edit_voucher_shifts: true })
    api.patch.mockResolvedValue({ data: updated })
    const w = mountCard()

    await radio(w, 'in_charge').trigger('click')
    await switchEl(w).trigger('click')
    expect(w.find('[data-testid="voucher-manual-on-shift-warning"]').exists()).toBe(false)
    expect(w.find('[data-testid="voucher-managers-edit-shifts-hint"]').text()).toMatch(/^On:/)
    expect(saveButton(w).element.disabled).toBe(false)

    await saveButton(w).trigger('click')
    await flush()

    expect(api.patch).toHaveBeenCalledWith({
      url: '/events/e1',
      body: { voucher_manual_redeem: 'in_charge', managers_edit_voucher_shifts: true },
    })
    expect(toast.success).toHaveBeenCalledWith('Voucher rules saved.')
    expect(w.emitted('updated')?.[0]).toEqual([updated])
    expect(auth.refreshSelectedEvent).toHaveBeenCalledWith('e1')
  })

  it('goes idle again once a change is taken back', async () => {
    const w = mountCard()
    await switchEl(w).trigger('click')
    expect(saveButton(w).element.disabled).toBe(false)
    await switchEl(w).trigger('click')
    expect(saveButton(w).element.disabled).toBe(true)
  })

  it('hands a refusal to the error toast and keeps the choice', async () => {
    const error = new Error('nope')
    api.patch.mockRejectedValue(error)
    const w = mountCard()
    await radio(w, 'in_charge').trigger('click')
    await saveButton(w).trigger('click')
    await flush()

    expect(toastApiError).toHaveBeenCalledWith(error)
    expect(toast.success).not.toHaveBeenCalled()
    expect(radio(w, 'in_charge').attributes('data-state')).toBe('checked')
  })

  it('names the places that take vouchers, leaving archived ones out', () => {
    const w = mountCard(event(), [
      task({ id: 't1', name: 'Cafétheke', is_voucher_point: true }),
      task({ id: 't2', name: 'Grillstand', is_voucher_point: true, status: 'draft' }),
      task({ id: 't3', name: 'Aufbau', vouchers_per_shift: 2 }),
      task({ id: 't4', name: 'Alte Theke', is_voucher_point: true, status: 'archived' }),
    ])
    const links = w.findAllComponents(RouterLinkStub)
    expect(links.map((l) => l.text())).toEqual(['Cafétheke', 'Grillstand'])
    expect(links[0]!.props('to')).toEqual({ name: 'task-detail', params: { eventId: 't1' } })
  })

  it('says when no place takes vouchers yet', () => {
    const w = mountCard(event(), [task({ vouchers_per_shift: 2 })])
    expect(w.find('[data-testid="voucher-points"]').text()).toContain('none yet')
  })
})
