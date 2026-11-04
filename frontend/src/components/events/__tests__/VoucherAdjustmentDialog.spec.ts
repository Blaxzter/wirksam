// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import VoucherAdjustmentDialog from '@/components/events/VoucherAdjustmentDialog.vue'

import type { VoucherBalance, VoucherEntryRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * A correction may take away at most what the person can still redeem
 * (earned vouchers stay earned, so a balance never goes below zero). The
 * dialog caps "Take away" there and says why; an edit gets its own amount back
 * first, and lowering an addition already spent is held to the same limit.
 */

const api = vi.hoisted(() => ({ post: vi.fn(), patch: vi.fn() }))
vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ post: api.post, patch: api.patch }),
}))

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock('vue-sonner', () => ({ toast }))

const toastApiError = vi.fn()
vi.mock('@/lib/api-errors', () => ({ toastApiError: (e: unknown) => toastApiError(e) }))

const passthrough = { template: '<div><slot /></div>' }
const dialogStub = {
  props: ['open'],
  template: '<div v-if="open" data-stub="dialog"><slot /></div>',
}

function balance(available: number): VoucherBalance {
  return {
    user_id: 'u1',
    name: 'Sina',
    email: 'sina@example.com',
    earned: available,
    upcoming: 0,
    redeemed: 0,
    adjusted: 0,
    available,
  }
}

const correction = (amount: number): VoucherEntryRead => ({
  id: 'c1',
  kind: 'adjustment',
  amount,
  note: 'Papiermarken',
  created_at: '2026-07-17T21:30:00',
  updated_at: '2026-07-17T21:30:00',
})

async function openDialog(available: number, entry: VoucherEntryRead | null = null) {
  const w = mount(VoucherAdjustmentDialog, {
    props: {
      open: false,
      eventId: 'e1',
      members: [],
      userId: 'u1',
      userName: 'Sina',
      entry,
      balances: [balance(available)],
    },
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

const input = (w: ReturnType<typeof mount>) =>
  w.find<HTMLInputElement>('[data-testid="voucher-adjustment-amount"] input')

const flush = () => new Promise((r) => setTimeout(r, 0))

beforeEach(() => {
  i18n.global.locale.value = 'en'
  vi.clearAllMocks()
})

describe('VoucherAdjustmentDialog', () => {
  it('shows what the person has and caps taking away at that', async () => {
    const w = await openDialog(3)
    expect(w.find('[data-testid="voucher-adjustment-current"]').text()).toBe('3 vouchers available')
    expect(w.find('[data-testid="voucher-adjustment-max"]').exists()).toBe(false)

    await w.find('[data-testid="voucher-adjustment-take"]').trigger('click')

    expect(w.find('[data-testid="voucher-adjustment-max"]').text()).toBe(
      "At most 3: that's what Sina can still redeem.",
    )
    expect(input(w).attributes('aria-valuemax')).toBe('3')
  })

  it('draws the person row and the chosen direction as the voucher screens do', async () => {
    const w = await openDialog(3)
    const row = w.find('[data-testid="voucher-adjustment-person-row"]')
    expect(row.text()).toContain('SI')
    expect(w.find('[data-testid="voucher-adjustment-current"]').classes()).toContain('bg-hero-chip')
    const take = w.find('[data-testid="voucher-adjustment-take"]')
    expect(take.classes()).toContain('data-[state=on]:bg-primary/12')
    expect(take.classes()).not.toContain('data-[state=on]:bg-accent')
  })

  it('takes exactly what is left and says nothing remains', async () => {
    api.post.mockResolvedValue({ data: {} })
    const w = await openDialog(3)
    await w.find('[data-testid="voucher-adjustment-take"]').trigger('click')
    await input(w).setValue('3')
    await input(w).trigger('blur')
    await w.find('[data-testid="voucher-adjustment-note"]').setValue('Papiermarken')

    expect(w.find('[data-testid="voucher-adjustment-after"]').text()).toBe('Available afterwards 0')
    await w.find('[data-testid="btn-save-voucher-adjustment"]').trigger('click')
    await flush()

    expect(api.post).toHaveBeenCalledWith({
      url: '/events/e1/vouchers/adjustments',
      body: { user_id: 'u1', amount: -3, note: 'Papiermarken' },
    })
  })

  it('gives an edited correction its own amount back first', async () => {
    // A −1 with 2 left: up to 3 can be taken, and the hint says why that is
    // more than the 2 on the badge.
    const w = await openDialog(2, correction(-1))
    expect(w.find('[data-testid="voucher-adjustment-current"]').text()).toBe('2 vouchers available')
    expect(w.find('[data-testid="voucher-adjustment-max"]').text()).toBe(
      'At most 3: Sina can still redeem 2, with this correction already counted.',
    )
    expect(input(w).attributes('aria-valuemax')).toBe('3')
  })

  it('keeps an edited addition from being lowered past what is left', async () => {
    // A +5 with 2 left (3 already spent): lowering it to +1 would take 4, so
    // +3 is the least it can keep.
    api.patch.mockResolvedValue({ data: {} })
    const w = await openDialog(2, correction(5))
    const hint = w.find('[data-testid="voucher-adjustment-max"]')
    expect(hint.text()).toBe('At least 3: less would take away more than Sina can still redeem.')
    expect(hint.classes()).toContain('text-muted-foreground')
    expect(input(w).attributes('aria-valuemin')).toBe('3')

    await input(w).setValue('1')
    await input(w).trigger('blur')

    expect(input(w).element.value).toBe('3')
    expect(w.find('[data-testid="voucher-adjustment-after"]').text()).toBe('Available afterwards 0')
    await w.find('[data-testid="btn-save-voucher-adjustment"]').trigger('click')
    await flush()
    expect(api.patch).toHaveBeenCalledWith({
      url: '/events/e1/vouchers/adjustments/c1',
      body: { amount: 3, note: 'Papiermarken' },
    })
  })

  it('takes nothing from an addition already spent', async () => {
    // Turning that +5 into a take-away would take at least 6.
    const w = await openDialog(2, correction(5))
    await w.find('[data-testid="voucher-adjustment-take"]').trigger('click')
    await input(w).setValue('1')
    await input(w).trigger('blur')

    const max = w.find('[data-testid="voucher-adjustment-max"]')
    expect(max.text()).toBe(
      'At most 0: Sina can still redeem 2, with this correction already counted.',
    )
    expect(max.classes()).toContain('text-destructive')
    expect(w.find('[data-testid="voucher-adjustment-after"]').exists()).toBe(false)

    await w.find('[data-testid="btn-save-voucher-adjustment"]').trigger('click')
    await flush()
    expect(api.patch).not.toHaveBeenCalled()

    // Back to adding, the amount comes up to the least it can keep.
    await w.find('[data-testid="voucher-adjustment-add"]').trigger('click')
    expect(input(w).element.value).toBe('3')
    expect(w.find('[data-testid="voucher-adjustment-after"]').text()).toBe('Available afterwards 0')
  })

  it('refuses to take anything from someone with nothing left', async () => {
    const w = await openDialog(0)
    await w.find('[data-testid="voucher-adjustment-take"]').trigger('click')
    await w.find('[data-testid="voucher-adjustment-note"]').setValue('Papiermarken')

    const max = w.find('[data-testid="voucher-adjustment-max"]')
    expect(max.text()).toBe("At most 0: that's what Sina can still redeem.")
    expect(max.classes()).toContain('text-destructive')
    expect(w.find('[data-testid="voucher-adjustment-after"]').exists()).toBe(false)

    await w.find('[data-testid="btn-save-voucher-adjustment"]').trigger('click')
    await flush()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('never caps adding', async () => {
    api.post.mockResolvedValue({ data: {} })
    const w = await openDialog(0)
    await input(w).setValue('5')
    await input(w).trigger('blur')
    await w.find('[data-testid="voucher-adjustment-note"]').setValue('Abbau')

    expect(w.find('[data-testid="voucher-adjustment-after"]').text()).toBe('Available afterwards 5')
    await w.find('[data-testid="btn-save-voucher-adjustment"]').trigger('click')
    await flush()
    expect(api.post).toHaveBeenCalledWith({
      url: '/events/e1/vouchers/adjustments',
      body: { user_id: 'u1', amount: 5, note: 'Abbau' },
    })
  })
})
